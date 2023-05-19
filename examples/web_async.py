#
# This file is part of the v4l2py project
#
# Copyright (c) 2023 Tiago Coutinho
# Distributed under the GPLv3 license. See LICENSE for more info.

# install dependencies with:
# python3 -m pip install uvicorn fastapi
#
# run from this directory with:
# uvicorn web_async:app

"""A simple ASGI web server showing camera output"""

import logging

import fastapi.responses

from v4l2py import Device, VideoCapture

PREFIX = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
SUFFIX = b"\r\n"
INDEX = """\
<!doctype html>
<html lang="en">
<head>
  <link rel="icon" href="data:;base64,iVBORw0KGgo=">
</head>
<body><img src="/stream" /></body>
</html>
"""

app = fastapi.FastAPI()

logging.basicConfig(
    level="INFO",
    format="%(threadName)-10s %(asctime)-15s %(levelname)-5s %(name)s: %(message)s",
)


async def gen_frames():
    with Device.from_id(0) as device:
        capture = VideoCapture(device)
        capture.set_format(640, 480, "MJPG")
        with capture as stream:
            async for frame in stream:
                yield b"".join((PREFIX, bytes(frame), SUFFIX))


@app.get("/")
def index():
    return fastapi.responses.HTMLResponse(INDEX)


@app.get("/stream")
def stream():
    return fastapi.responses.StreamingResponse(
        gen_frames(), media_type="multipart/x-mixed-replace; boundary=frame"
    )
