#
# This file is part of the v4l2py project
#
# Copyright (c) 2023 Tiago Coutinho
# Distributed under the GPLv3 license. See LICENSE for more info.

# run from this directory with: 
# gunicorn --bind=0.0.0.0:8000 --log-level=debug --worker-class=gevent app:app

import logging

import flask
import gevent
import gevent.event
import gevent.monkey
import gevent.queue
import gevent.time

gevent.monkey.patch_all()

from v4l2py import Device, iter_video_capture_devices

app = flask.Flask("basic-web-cam")
app.jinja_env.line_statement_prefix = "#"

logging.basicConfig(
    level="INFO",
    format="%(threadName)-10s %(asctime)-15s %(levelname)-5s %(name)s: %(message)s",
)


BOUNDARY = "frame"
PREFIX = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
SUFFIX = b"\r\n"

HEADER = (
    "--{boundary}\r\nContent-Type: image/{type}\r\nContent-Length: {length}\r\n\r\n"
)

CAMERAS = None


class StreamResponse(flask.Response):
    default_mimetype = "multipart/x-mixed-replace;boundary={boundary}"

    def __init__(self, *args, **kwargs):
        boundary = kwargs.pop("boundary", BOUNDARY)
        mimetype = kwargs.pop("mimetype", self.default_mimetype)
        kwargs["mimetype"] = mimetype.format(boundary=boundary)
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
    def __init__(self, device: Device) -> None:
        self.device: Device = device
        self.runner: gevent.Greenlet | None = None
        self.last_frame: bytes | None = None
        self.last_request: float = 0.0
        self.trigger: Trigger = Trigger()

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
                if not i % 100:
                    self.device.log.info(f"frame {i:04d}")
                self.last_frame = frame
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


def jpeg_frame(frame, boundary=BOUNDARY):
    header = HEADER.format(type="jpeg", boundary=boundary, length=len(frame)).encode()
    return b"".join((header, frame, SUFFIX))


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
    return flask.render_template("device.html", camera=camera)


@app.get("/camera/<int:device_id>/stream")
def stream(device_id):
    camera = cameras()[device_id]

    def send_frames():
        while True:
            yield jpeg_frame(camera.next_frame(), boundary=BOUNDARY)

    return StreamResponse(send_frames(), boundary=BOUNDARY)


if __name__ == "__main__":
    app.run(host="0.0.0.0")
