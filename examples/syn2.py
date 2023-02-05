import logging
import time

from v4l2py.device import Device, VideoCapture


fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
logging.basicConfig(level="DEBUG", format=fmt)

with Device.from_id(5) as device:
    capture = VideoCapture(device)
    capture.set_format(640, 480, "MJPG")
    with capture as stream:
        last = time.monotonic()
        last_update = 0
        for i, frame in enumerate(stream):
            new = time.monotonic()
            fps, last = 1 / (new - last), new
            if new - last_update > .1:
                print(f"frame {i:04d} {len(frame)/1000:.1f} Kb at {fps:.1f} fps", end='\r')
                last_update = new