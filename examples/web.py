#
# This file is part of the v4l2py project
#
# Copyright (c) 2021 Tiago Coutinho
# Distributed under the GPLv3 license. See LICENSE for more info.

# run from this directory with: FLASK_APP=web flask run -h 0.0.0.0

import flask

from v4l2py import Device

app = flask.Flask("basic-web-cam")


PREFIX = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
SUFFIX = b"\r\n"


def gen_frames():
    with Device.from_id(0) as device:
        for frame in device:
            yield b"".join((PREFIX, frame, SUFFIX))


@app.get("/")
def index():
    return '<html><img src="/stream" /></html>'


@app.get("/stream")
def stream():
    return flask.Response(
        gen_frames(), mimetype="multipart/x-mixed-replace; boundary=frame"
    )


app.run(host="0.0.0.0")
