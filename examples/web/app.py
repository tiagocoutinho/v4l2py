#
# This file is part of the v4l2py project
#
# Copyright (c) 2023 Tiago Coutinho
# Distributed under the GPLv3 license. See LICENSE for more info.

# Extra dependencies required to run this example:

# pip install pillow cv2 flask gunicorn gevent

# run from this directory with:
# gunicorn --bind=0.0.0.0:8000 --log-level=debug --worker-class=gevent app:app

import io
import logging

import cv2
import flask
import gevent
import gevent.event
import gevent.fileobject
import gevent.monkey
import gevent.queue
import gevent.time
import PIL.Image

from v4l2py.device import (
    ControlType,
    Device,
    PixelFormat,
    VideoCapture,
    iter_video_capture_devices,
)
from v4l2py.io import GeventIO


gevent.monkey.patch_all()

app = flask.Flask("basic-web-cam")
app.jinja_env.line_statement_prefix = "#"

logging.basicConfig(
    level="INFO",
    format="%(threadName)-10s %(asctime)-15s %(levelname)-5s %(name)s: %(message)s",
)

log = logging.getLogger(__name__)


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
                    log.info("Removing inactive client...")
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
    def __init__(self, device: Device, frame_type="jpeg") -> None:
        self.device: Device = device
        self.capture = VideoCapture(self.device)
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
            self.last_request = gevent.time.monotonic()
            for i, frame in enumerate(self.device):
                self.last_frame = frame_to_image(frame)
                self.trigger.set()
                if gevent.time.monotonic() - self.last_request > 10:
                    log.info("Stopping camera task due to inactivity")
                    break


def cameras() -> list[Camera]:
    global CAMERAS
    if CAMERAS is None:
        cameras = {}
        for device in iter_video_capture_devices(io=GeventIO):
            with device:
                # pass just to make it read camera info
                pass
            cameras[device.index] = Camera(device)
        CAMERAS = cameras
    return CAMERAS


def frame_to_image(frame, output="jpeg"):
    match frame.pixel_format:
        case PixelFormat.JPEG | PixelFormat.MJPEG:
            if output == "jpeg":
                return to_image_send(frame.data, type=output)
            else:
                buff = io.BytesIO()
                image = PIL.Image.open(io.BytesIO(frame.data))
        case PixelFormat.GREY:
            data = frame.array
            data.shape = frame.height, frame.width, -1
            image = PIL.Image.frombuffer("L", (format.width, format.height), data)
        case PixelFormat.YUYV:
            data = frame.array
            data.shape = frame.height, frame.width, -1
            rgb = cv2.cvtColor(data, cv2.COLOR_YUV2RGB_YUYV)
            image = PIL.Image.fromarray(rgb)

    buff = io.BytesIO()
    image.save(buff, output)
    return to_image_send(buff.getvalue(), type=output)


def to_image_send(data, type="jpeg", boundary=BOUNDARY):
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
        return flask.render_template(
            "device.html", camera=camera, ControlType=ControlType
        )


@app.get("/camera/<int:device_id>/stream")
def stream(device_id):
    camera = cameras()[device_id]
    return StreamResponse(iter(camera))


@app.post("/camera/<int:device_id>/format")
def set_format(device_id):
    width, height, fmt = map(int, flask.request.form["value"].split())
    camera = cameras()[device_id]
    with camera.device:
        camera.capture.set_format(width, height, fmt)
    return "", 204


@app.post("/camera/<int:device_id>/control/<int:control_id>")
def set_control(device_id, control_id):
    camera = cameras()[device_id]
    with camera.device:
        control = camera.device.controls[control_id]
        control.value = int(flask.request.form["value"])
    return "", 204


@app.post("/camera/<int:device_id>/control/<int:control_id>/<int:value>")
def set_control_value(device_id, control_id, value):
    camera = cameras()[device_id]
    with camera.device:
        control = camera.device.controls[control_id]
        control.value = value
    return "", 204


@app.post("/camera/<int:device_id>/control/<int:control_id>/reset")
def reset_control(device_id, control_id):
    camera = cameras()[device_id]
    with camera.device:
        control = camera.device.controls[control_id]
        control.value = control.info.default_value
    return flask.render_template(
        "control.html", control=control, ControlType=ControlType
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0")
