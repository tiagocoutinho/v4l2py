# run from this directory with: FLASK_APP=web flask run

import flask
from v4l2py import Device

app = flask.Flask('basic-web-cam')

def gen_frames():
    with Device.from_id(0) as cam:
        cam.video_capture.set_format(640, 480, 'MJPG')
        for frame in cam:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"

@app.route("/")
def index():
    return '<html><img src="/stream" /></html>'

@app.route("/stream")
def stream():
    return flask.Response(
        gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
