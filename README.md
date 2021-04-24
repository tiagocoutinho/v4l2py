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
>>> cam.open()

>>> cam.capabilities
{'driver': b'uvcvideo',
 'card': b'Integrated_Webcam_HD: Integrate',
 'bus_info': b'usb-0000:00:14.0-6',
 'version': 328798,
 'capabilities': <STREAMING|META_CAPTURE|EXT_PIX_FORMAT|VIDEO_CAPTURE: 2225078273>}

>>> cam.supported_formats
 [{'type': <BufferType.VIDEO_CAPTURE: 1>,
  'flags': <ImageFormatFlag.COMPRESSED: 1>,
  'description': b'Motion-JPEG',
  'pixelformat': 1196444237},
 {'type': <BufferType.VIDEO_CAPTURE: 1>,
  'flags': <ImageFormatFlag.0: 0>,
  'description': b'YUYV 4:2:2',
  'pixelformat': 1448695129}]

>>> cam.get_format()
{'width': 640, 'height': 480, 'pixelformat': 'MJPG'}
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
        cam.set_format(640, 480, 'MJPG')
        for frame in cam:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"

@app.route("/")
def index():
    return '<!DOCTYPE html><html><body><img src="/stream" /></body></html>'

@app.route("/stream")
def stream():
    return flask.Response(
        gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

app.run(host="0.0.0.0")
```

run with:

```bash
$ python web.py
```

Point your browser to [127.0.0.1:5000](http://127.0.0.1:5000) and you should see
your camera rolling!


See the ``linux/videodev2.h`` header file for details.

* `Video for Linux Two Specification <http://linuxtv.org/downloads/v4l-dvb-apis/ch07s02.html>`_
* `Reporting bugs <http://bugs.launchpad.net/python-v4l2>`_
