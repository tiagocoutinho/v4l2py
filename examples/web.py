#
# This file is part of the v4l2py project
#
# Copyright (c) 2021 Tiago Coutinho
# Distributed under the GPLv3 license. See LICENSE for more info.

# run from this directory with: FLASK_APP=web flask run -h 0.0.0.0

import flask

from v4l2py import Device, VideoCapture, VideoStream

app = flask.Flask("basic-web-cam")


PREFIX = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
SUFFIX = b"\r\n"


def gen_frames():
    with Device.from_id(5) as dev:
        capture = VideoCapture(dev)
        capture.set_format(640, 480, "MJPG")
        for frame in capture:
            yield b"".join((PREFIX, frame, SUFFIX))


@app.route("/")
def index():
    return '<html><img src="/stream" /></html>'


@app.route("/stream")
def stream():
    return flask.Response(
        gen_frames(), mimetype="multipart/x-mixed-replace; boundary=frame"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0")
