import asyncio
import logging
import time

from v4l2py.device import Device, VideoCapture

fmt = "%(threadName)-10s %(asctime)-15s %(levelname)-5s %(name)s: %(message)s"
logging.basicConfig(level="WARNING", format=fmt)


async def main():
    with Device.from_id(0) as device:
        capture = VideoCapture(device)
        capture.set_format(640, 480, "MJPG")
        with capture as stream:
            last = time.monotonic()
            last_update = 0
            i = 0
            async for frame in stream:
                new = time.monotonic()
                fps, last = 1 / (new - last), new
                if new - last_update > 0.1:
                    print(
                        f"frame {i:04d} {len(frame)/1000:.1f} Kb at {fps:.1f} fps",
                        end="\r",
                    )
                    last_update = new
                i += 1


asyncio.run(main())
