#
# This file is part of the v4l2py project
#
# Copyright (c) 2023 Tiago Coutinho
# Distributed under the GPLv3 license. See LICENSE for more info.

# run from this directory with: 
# gunicorn --bind=0.0.0.0:8000 --log-level=debug --worker-class=gevent app:app

import functools
import io
import logging

import flask
import gevent
import gevent.event
import gevent.monkey
import gevent.queue
import gevent.time

from PIL import Image
import pillow_avif

gevent.monkey.patch_all()

from v4l2py.device import Device, VideoCapture, Format, PixelFormat, iter_video_capture_devices

app = flask.Flask("basic-web-cam")
app.jinja_env.line_statement_prefix = "#"

logging.basicConfig(
    level="INFO",
    format="%(threadName)-10s %(asctime)-15s %(levelname)-5s %(name)s: %(message)s",
)


BOUNDARY = "frame"
HEADER = (
    "--{boundary}\r\nContent-Type: image/{type}\r\nContent-Length: {length}\r\n\r\n"
)
SUFFIX = b"\r\n"

CAMERAS = None


class StreamResponse(flask.Response):
    default_mimetype = "multipart/x-mixed-replace;boundary={boundary}"

    def __init__(self, *args, boundary=BOUNDARY, **kwargs):
        self.boundary = boundary
        mimetype = kwargs.pop("mimetype", self.default_mimetype)
        kwargs["mimetype"] = mimetype.format(boundary=self.boundary)
        super().__init__(*args, **kwargs)


class Trigger:
    def __init__(self):
        self.events = {}

    def wait(self):
        ident = gevent.getcurrent().minimal_ident
        if ident not in self.events:
            self.events[ident] = [gevent.event.Event(), gevent.time.monotonic()]
        return self.events[ident][0].wait()

    def set(self):
        now = gevent.time.monotonic()
        remove = []
        for ident, event in self.events.items():
            if event[0].is_set():
                if now - event[1] > 5:
                    logging.info("Removing inactive client...")
                    remove.append(ident)
            else:
                event[0].set()
                event[1] = now
        for ident in remove:
            del self.events[ident]

    def clear(self):
        ident = gevent.getcurrent().minimal_ident
        self.events[ident][0].clear()


class Camera:
    def __init__(self, device: Device, frame_type='jpeg') -> None:
        self.device: Device = device
        self.runner: gevent.Greenlet | None = None
        self.last_frame: bytes | None = None
        self.last_request: float = 0.0
        self.trigger: Trigger = Trigger()
        self.frame_type = frame_type

    def __iter__(self):
        while True:
            yield self.next_frame()

    def next_frame(self) -> bytes:
        self.last_request = gevent.time.monotonic()
        self.trigger.wait()
        self.trigger.clear()
        return self.last_frame

    def start(self) -> None:
        if not self.is_running:
            self.device.log.info("Start")
            self.runner = gevent.spawn(self.run)

    def stop(self) -> None:
        if self.runner:
            self.device.log.info("Stop")
            self.runner.kill()
            self.runner = None

    @property
    def is_running(self):
        return not (self.runner is None or self.runner.ready())

    def run(self):
        with self.device:
            capture = VideoCapture(self.device)
            capture.set_format(640, 480, "MJPG")
            format = capture.get_format()
            to_frame = buffer_to_frame_maker(format, output=self.frame_type)
            self.last_request = gevent.time.monotonic()
            buff = io.BytesIO()
            for i, data in enumerate(self.device):
                self.last_frame = to_frame(data)
                if not i % 100:
                    self.device.log.info(f"frame {i:04d} (raw={len(data) / 1000:.1f} kb; {self.frame_type}={len(self.last_frame) / 1000:.1f} kb)")
                self.trigger.set()
                if gevent.time.monotonic() - self.last_request > 10:
                    self.device.log.info("Stopping camera task due to inactivity")
                    break


def cameras() -> list[Camera]:
    global CAMERAS
    if CAMERAS is None:
        cameras = {}
        for device in iter_video_capture_devices():
            with device:
                # pass just to make it read camera info
                pass
            cameras[device.index] = Camera(device)
        CAMERAS = cameras
    return CAMERAS


def buffer_to_frame_maker(format: Format, output='avif'):
    match (format.pixel_format, output.lower()):
        case [PixelFormat.JPEG | PixelFormat.MJPEG, 'jpeg']:
            return functools.partial(to_frame, type='jpeg')
        case _:            
            return functools.partial(buffer_to_frame, format=format, output=output)


def buffer_to_frame(data: bytes, format: Format, output='jpeg'):
    from PIL import Image
    match format.pixel_format:
        case PixelFormat.JPEG | PixelFormat.MJPEG:
            image = Image.open(io.BytesIO(data))
        case PixelFormat.GREY:
            image = Image.frombuffer("L", (format.width, format.height), data)
        case _:
            raise ValueError(f"unsupported pixel format {format.pixel_format}")
    buff = io.BytesIO()
    image.save(buff, output)
    return to_frame(buff.getvalue(), type=output)


def to_frame(data, type='avif', boundary=BOUNDARY):
    header = HEADER.format(type=type, boundary=boundary, length=len(data)).encode()
    return b"".join((header, data, SUFFIX))


@app.get("/")
def index():
    return flask.render_template("index.html", cameras=cameras())


@app.post("/camera/<int:device_id>/start")
def start(device_id):
    camera = cameras()[device_id]
    camera.start()
    return (
        f'<img src="/camera/{device_id}/stream" width="640" alt="{camera.device.info.card}"/>',
        200,
    )


@app.post("/camera/<int:device_id>/stop")
def stop(device_id):
    camera = cameras()[device_id]
    camera.stop()
    return '<img src="/static/cross.png" width="640" alt="no video"/>', 200


@app.get("/camera/<int:device_id>")
def device(device_id: int):
    camera = cameras()[device_id]
    with camera.device:
        return flask.render_template("device.html", camera=camera)


@app.get("/camera/<int:device_id>/stream")
def stream(device_id):
    camera = cameras()[device_id]
    return StreamResponse(iter(camera))


@app.post("/camera/<int:device_id>/control/<int:control_id>")
def set_control(device_id, control_id):
    camera = cameras()[device_id]
    with camera.device:
        control = camera.device.controls[control_id]
        control.value = int(flask.request.form["value"])
    return "", 204


@app.post("/camera/<int:device_id>/control/<int:control_id>/reset")
def reset_control(device_id, control_id):
    camera = cameras()[device_id]
    with camera.device:
        control = camera.device.controls[control_id]
        control.value = control.info.default_value
    return flask.render_template("control.html", control=control)

if __name__ == "__main__":
    app.run(host="0.0.0.0")
