#
# This file is part of the v4l2py project
#
# Copyright (c) 2023 Tiago Coutinho
# Distributed under the GPLv3 license. See LICENSE for more info.

# Extra dependencies required to run this example:
# python3 -m pip install pillow opencv-python flask gunicorn gevent

# run from this directory with:
# gunicorn --bind=0.0.0.0:8000 --log-level=debug --worker-class=gevent sync:app

"""Flask example for v4l2py"""

import logging

import flask
import gevent
import gevent.event
import gevent.fileobject
import gevent.monkey
import gevent.queue
import gevent.time
from common import BOUNDARY, BaseCamera, frame_to_image

from v4l2py.device import ControlType, Device, iter_video_capture_devices
from v4l2py.io import GeventIO

gevent.monkey.patch_all()

app = flask.Flask("basic-web-cam")
app.jinja_env.line_statement_prefix = "#"

logging.basicConfig(
    level="INFO",
    format="%(threadName)-10s %(asctime)-15s %(levelname)-5s %(name)s: %(message)s",
)

log = logging.getLogger(__name__)


CAMERAS = None


class StreamResponse(flask.Response):
    default_mimetype = "multipart/x-mixed-replace;boundary={boundary}"

    def __init__(self, *args, boundary=BOUNDARY, **kwargs):
        self.boundary = boundary
        mimetype = kwargs.pop("mimetype", self.default_mimetype)
        kwargs["mimetype"] = mimetype.format(boundary=self.boundary)
        super().__init__(*args, **kwargs)


class Camera(BaseCamera):
    def __init__(self, device: Device) -> None:
        super().__init__(device)
        self.clients: gevent.queue.Queue = gevent.queue.Queue()
        self.runner: gevent.Greenlet | None = None

    def get_clients(self, timeout=None) -> None | list[gevent.queue.Queue]:
        try:
            with gevent.Timeout(timeout):
                clients = [self.clients.get()]
        except gevent.Timeout:
            return
        while not self.clients.empty():
            clients.append(self.clients.get_nowait())
        return clients

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
            for frame in self.device:
                if clients := self.get_clients(timeout=3):
                    data = frame_to_image(frame)
                    for client in clients:
                        client.put(data)
                else:
                    self.device.log.info("Stopping camera task due to inactivity")
                    break


def cameras() -> list[Camera]:
    global CAMERAS
    if CAMERAS is None:
        cameras = {}
        for device in iter_video_capture_devices(io=GeventIO):
            cameras[device.index] = Camera(device)
        CAMERAS = cameras
    return CAMERAS


@app.get("/")
def index():
    return flask.render_template("index.html", cameras=cameras())


@app.post("/camera/<int:device_id>/start")
def start(device_id):
    camera = cameras()[device_id]
    camera.start()
    return (
        f'<img src="/camera/{device_id}/stream" width="640" alt="{camera.info.card}"/>',
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

    def gen_frames():
        client = gevent.queue.Queue()
        while True:
            camera.clients.put(client)
            yield client.get()

    return StreamResponse(gen_frames())


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
        value = flask.request.form.get("value", 0)
        camera.device.log.info("setting %s to %s", control.name, value)
        if value == "on":
            value = 1
        elif value == "off":
            value = 0
        else:
            value = int(value)
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
