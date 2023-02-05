import logging
import time

from v4l2py.device import Device, VideoCapture, MemoryMap


fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
logging.basicConfig(level="DEBUG", format=fmt)

with Device.from_id(5) as device:
    capture = VideoCapture(device)
    capture.set_format(640, 480, "MJPG")
    with MemoryMap(capture, 1) as memory:
        capture.stream_on()
        try:
            while True:
                print(len(memory.read()))
        finally:
            capture.stream_off()
