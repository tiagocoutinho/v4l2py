# v4l2py

Forked from [aspotton/python-v4l2](https://github.com/aspotton/python-v4l2).

A two purpose API:

* raw python binding for the v4l2 (video4linux2) userspace API, using ctypes (don't even
  bother wasting your time here. You probably won't use it)
* high level Device API for humans to play with :-)

Only works on python 3 (probably >=3.6).


## Installation

From within your favorite python environment:

```bash
$ pip install v4l2py
```

## Usage

Without further ado:

```python
>>> from v4l2py import Device
>>> cam = Device.from_id(0)
>>> for i, frame in enumerate(cam):
...     print(f"frame #{i}: {len(frame)} bytes")
...     if i > 9:
...         break
...
frame #0: 54630 bytes
frame #1: 50184 bytes
frame #2: 44054 bytes
frame #3: 42822 bytes
frame #4: 42116 bytes
frame #5: 41868 bytes
frame #6: 41322 bytes
frame #7: 40896 bytes
frame #8: 40844 bytes
frame #9: 40714 bytes
frame #10: 40662 bytes
```

Getting information about the device:

```python
>>> from v4l2py import Device

>>> cam = Device.from_id(0)

>>> cam.info.card
'Integrated_Webcam_HD: Integrate'

>>> cam.info.capabilities
<Capability.STREAMING|EXT_PIX_FORMAT|VIDEO_CAPTURE: 69206017>

>>> cam.info.formats
[ImageFormat(type=<BufferType.VIDEO_CAPTURE: 1>, description=b'Motion-JPEG',
             flags=<ImageFormatFlag.COMPRESSED: 1>, pixelformat=<PixelFormat.MJPEG: 1196444237>),
 ImageFormat(type=<BufferType.VIDEO_CAPTURE: 1>, description=b'YUYV 4:2:2',
             flags=<ImageFormatFlag.0: 0>, pixelformat=<PixelFormat.YUYV: 1448695129>)]

>>> cam.video_capture.get_format()
Format(width=640, height=480, pixelformat=<PixelFormat.MJPEG: 1196444237>}
```


## Bonus track

You've been patient enough to read until here so, just for you,
a 20 line gem: a flask web server displaying your device on the web:

```bash
$ pip install flask
```

```python
# web.py

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
```

run with:

```bash
$ FLASK_APP=web flask run
```

Point your browser to [127.0.0.1:5000](http://127.0.0.1:5000) and you should see
your camera rolling!


See the ``linux/videodev2.h`` header file for details.

* `Video for Linux Two Specification <http://linuxtv.org/downloads/v4l-dvb-apis/ch07s02.html>`_
* `Reporting bugs <http://bugs.launchpad.net/python-v4l2>`_
