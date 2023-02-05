import logging

from v4l2py.device import Device, VideoCapture


fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
logging.basicConfig(level="DEBUG", format=fmt)

with Device.from_id(5) as device:
    capture = VideoCapture(device)
    capture.set_format(640, 480, "MJPG")
    with capture as stream:
        for frame in stream:
            print(len(frame))
