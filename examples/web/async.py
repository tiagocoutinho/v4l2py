#
# This file is part of the v4l2py project
#
# Copyright (c) 2023 Tiago Coutinho
# Distributed under the GPLv3 license. See LICENSE for more info.

# Extra dependencies required to run this example:
# python3 -m pip install fastapi jinja2 python-multipart opencv-python \
# pillow uvicorn

# run from this directory with:
# uvicorn async:app

"""FastAPI example for v4l2py"""

import asyncio
import logging
from typing import Annotated

from common import BOUNDARY, BaseCamera, frame_to_image
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from v4l2py.device import ControlType, Device, iter_video_capture_devices

logging.basicConfig(
    level="INFO",
    format="%(threadName)-10s %(asctime)-15s %(levelname)-5s %(name)s: %(message)s",
)

log = logging.getLogger(__name__)


class Camera(BaseCamera):
    def __init__(self, device: Device) -> None:
        super().__init__(device)
        self.clients: asyncio.Queue = asyncio.Queue()
        self.runner: None | asyncio.Task = None

    async def get_clients(self, timeout=None) -> None | list[asyncio.Queue]:
        first_client = self.clients.get()
        if timeout is None:
            clients = [await first_client]
        else:
            try:
                clients = [await asyncio.wait_for(first_client, timeout)]
            except asyncio.TimeoutError:
                return
        while not self.clients.empty():
            clients.append(self.clients.get_nowait())
        return clients

    def start(self) -> None:
        if not self.is_running:
            name = f"Run {self.device.filename}"
            self.device.log.info("Start")
            self.runner = asyncio.create_task(self.run(), name=name)

    def stop(self) -> None:
        if self.runner:
            self.device.log.info("Stop")
            self.runner.cancel()
            self.runner = None

    @property
    def is_running(self):
        return not (self.runner is None or self.runner.done())

    async def run(self):
        with self.device:
            self.capture.set_format(640, 480, "MJPG")
            with self.capture as frames:
                async for frame in frames:
                    if clients := await self.get_clients(timeout=3):
                        data = frame_to_image(frame)
                        for client in clients:
                            await client.put(data)
                    else:
                        self.device.log.info("Stopping camera task due to inactivity")
                        break


CAMERAS = None


def cameras() -> list[Camera]:
    global CAMERAS
    if CAMERAS is None:
        cameras = {}
        for device in iter_video_capture_devices(legacy_controls=True):
            cameras[device.index] = Camera(device)
        CAMERAS = cameras
    return CAMERAS


app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates", line_statement_prefix="#")


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(
        "index.html", {"request": request, "cameras": cameras()}
    )


@app.get("/camera/{device_id}")
def device(request: Request, device_id: int):
    camera = cameras()[device_id]
    with camera.device:
        ctx = {"request": request, "camera": camera, "ControlType": ControlType}
        return templates.TemplateResponse("device.html", ctx)


@app.post("/camera/{device_id}/start")
async def start(device_id: int):
    camera = cameras()[device_id]
    camera.start()
    return HTMLResponse(
        f'<img src="/camera/{device_id}/stream" width="640" alt="{camera.info.card}"/>'
    )


@app.post("/camera/{device_id}/stop")
async def stop(device_id: int):
    camera = cameras()[device_id]
    camera.stop()
    return HTMLResponse('<img src="/static/cross.png" width="640" alt="no video"/>')


@app.get("/camera/{device_id}/stream")
async def stream(device_id: int):
    camera = cameras()[device_id]

    async def gen_frames():
        queue = asyncio.Queue()
        while True:
            await camera.clients.put(queue)
            yield await queue.get()

    return StreamingResponse(
        gen_frames(), media_type=f"multipart/x-mixed-replace; boundary={BOUNDARY}"
    )


@app.post("/camera/{device_id}/format")
def set_format(device_id: int, value: Annotated[str, Form()]):
    width, height, fmt = map(int, value.split())
    camera = cameras()[device_id]
    with camera.device:
        camera.capture.set_format(width, height, fmt)
    return "", 204


@app.post("/camera/{device_id}/control/{control_id}")
def set_control(device_id: int, control_id: int, value: str = Form(default="0")):
    camera = cameras()[device_id]
    with camera.device:
        control = camera.device.controls[control_id]
        camera.device.log.info("setting %s to %s", control.name, value)
        if value == "on":
            value = 1
        elif value == "off":
            value = 0
        else:
            value = int(value)
        control.value = value
    return "", 204


@app.post("/camera/{device_id}/control/{control_id}/reset")
def reset_control(request: Request, device_id: int, control_id: int):
    camera = cameras()[device_id]
    with camera.device:
        control = camera.device.controls[control_id]
        control.value = control.info.default_value
    ctx = {"request": request, "control": control, "ControlType": ControlType}
    return templates.TemplateResponse("control.html", ctx)
