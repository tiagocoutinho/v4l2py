import asyncio
import logging
import time

from v4l2py.device import Device, VideoCapture


async def loop(variable):
    while True:
        await asyncio.sleep(0.1)
        variable[0] += 1


async def main():
    fmt = "%(threadName)-10s %(asctime)-15s %(levelname)-5s %(name)s: %(message)s"
    logging.basicConfig(level="INFO", format=fmt)

    data = [0]
    asyncio.create_task(loop(data))

    with Device.from_id(0) as device:
        capture = VideoCapture(device)
        capture.set_format(640, 480, "MJPG")
        with capture as stream:
            start = last = time.monotonic()
            last_update = 0
            async for frame in stream:
                new = time.monotonic()
                fps, last = 1 / (new - last), new
                if new - last_update > 0.1:
                    elapsed = new - start
                    print(
                        f"frame {frame.frame_nb:04d} {len(frame)/1000:.1f} Kb at {fps:.1f} fps ; data={data[0]}; {elapsed=:.2f} s;",
                        end="\r",
                    )
                    last_update = new


try:
    asyncio.run(main())
except KeyboardInterrupt:
    logging.info("Ctrl-C pressed. Bailing out")
