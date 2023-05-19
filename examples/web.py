#
# This file is part of the v4l2py project
#
# Copyright (c) 2021 Tiago Coutinho
# Distributed under the GPLv3 license. See LICENSE for more info.

# Extra dependency required to run this example:
# python3 -m pip install flask

# run from this directory with: FLASK_APP=web flask run -h 0.0.0.0

import flask

from v4l2py import Device, VideoCapture

app = flask.Flask("basic-web-cam")


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


def gen_frames():
    with Device.from_id(0) as device:
        capture = VideoCapture(device)
        capture.set_format(640, 480, "MJPG")
        for frame in device:
            yield b"".join((PREFIX, bytes(frame), SUFFIX))


@app.get("/")
def index():
    return INDEX


@app.get("/stream")
def stream():
    return flask.Response(
        gen_frames(), mimetype="multipart/x-mixed-replace; boundary=frame"
    )
