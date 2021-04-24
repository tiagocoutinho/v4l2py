# v4l2py

Forked from [aspotton/python-v4l2](https://github.com/aspotton/python-v4l2).

A two purpose API:

* raw python binding for the v4l2 (video4linux2) userspace API, using ctypes (don't even
  bother wasting your time here. You probably won't use it)
* high level Device API for humans to play with :-)

Only works on python 3 (probably >=3.6).


## Installation

From within your favorite python environment:

```
pip install v4l2py
```

## Usage

```python

from v4l2py import Device

with Device.from_id(0) as camera:
    

    >>> import v4l2
    >>> import fcntl
    >>> vd = open('/dev/video0', 'w')
    >>> cp = v4l2.v4l2_capability()
    >>> fcntl.ioctl(vd, v4l2.VIDIOC_QUERYCAP, cp)
    0
    >>> cp.driver
    'uvcvideo'
    >>> cp.card
    'USB 2.0 Camera'

See the ``linux/videodev2.h`` header file for details.

* `Video for Linux Two Specification <http://linuxtv.org/downloads/v4l-dvb-apis/ch07s02.html>`_
* `Reporting bugs <http://bugs.launchpad.net/python-v4l2>`_
