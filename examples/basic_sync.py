import logging
from v4l2py.device import Device


def main():
    fmt = "%(threadName)-10s %(asctime)-15s %(levelname)-5s %(name)s: %(message)s"
    logging.basicConfig(level="INFO", format=fmt)

    with Device.from_id(0) as stream:
        for i, frame in enumerate(stream):
            logging.info(f"frame {i:04d} {len(frame)/1000:.1f} Kb")


try:
    main()
except KeyboardInterrupt:
    logging.info("Ctrl-C pressed. Bailing out")
