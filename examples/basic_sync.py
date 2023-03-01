import logging
import time

from v4l2py.device import Device


def main():
    fmt = "%(threadName)-10s %(asctime)-15s %(levelname)-5s %(name)s: %(message)s"
    logging.basicConfig(level="INFO", format=fmt)

    with Device.from_id(0) as stream:
        last = time.monotonic()
        last_update = 0
        for i, frame in enumerate(stream):
            new = time.monotonic()
            fps, last = 1 / (new - last), new
            if new - last_update > 0.1:
                print(
                    f"frame {i:04d} {len(frame)/1000:.1f} Kb at {fps:.1f} fps",
                    end="\r",
                )
                last_update = new


try:
    main()
except KeyboardInterrupt:
    logging.info("Ctrl-C pressed. Bailing out")
