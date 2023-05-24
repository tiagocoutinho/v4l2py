import argparse
import time
import datetime
import sys

from v4l2py.device import Device, VideoCapture, PixelFormat
from v4l2py.device import iter_video_capture_devices, Capability


def list_devices() -> None:
    print("Listing all video capture devices ...\n")
    for dev in iter_video_capture_devices():
        with dev as cam:
            print(f"{cam.index:>2}: {cam.info.card}")
            print(f"\tdriver  : {cam.info.driver}")
            print(f"\tversion : {cam.info.version}")
            print(f"\tbus     : {cam.info.bus_info}")
            caps = [
                cap.name.lower()
                for cap in Capability
                if ((cam.info.device_capabilities & cap) == cap)
            ]
            if caps:
                print("\tcaps    :", ", ".join(caps))
            else:
                print("\tcaps    : none")
            print("\tframesizes:")
            frame_sizes = supported_frame_sizes(cam.info.frame_sizes)
            for i in range(len(frame_sizes)):
                s = frame_sizes[i]
                print(f"\t  {i+1:2}: {s[0]:4} x {s[1]:4}")
        print()


def supported_frame_sizes(frame_sizes, pixel_format=PixelFormat.MJPEG):
    sfs = [(f.width, f.height) for f in frame_sizes if f.pixel_format == pixel_format]
    sfs.sort()
    return sfs


def take_snapshot(args):
    with Device(args.device) as cam:
        capture = VideoCapture(cam)
        if args.framesize == 0:
            (width, height, _) = capture.get_format()
        else:
            framesizes = supported_frame_sizes(cam.info.frame_sizes)
            try:
                fmt = framesizes[args.framesize - 1]
            except IndexError:
                print(f"ERROR: framesize index {args.framesize} not available")
                sys.exit(1)
            else:
                (width, height) = fmt
        print(f"Framesize is {width}x{height} pixels")
        capture.set_format(width, height, "MJPG")

        print(f"Camera warmup for {args.warmup}ms ...")
        warmup_ = args.warmup * 1000000
        start = time.monotonic_ns()
        for frame in cam:
            if time.monotonic_ns() - start >= warmup_:
                break
        print("Camera is ready")

    print("Snapshot taken")
    return frame


def save_snapshot(frame, args):
    now = datetime.datetime.now()
    fname = now.strftime(args.filename)
    print(f"Saving as {fname} ...")
    with open(fname, "wb") as f:
        f.write(frame.data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="v4l2py-snapshot",
        description="Example utility to get a picture from a capturing device and save it to disk.",
    )
    parser.add_argument(
        "-d",
        "--device",
        type=str,
        default="0",
        metavar="<dev>",
        help="use device <dev> instead of /dev/video0; if <dev> starts with a digit, then /dev/video<dev> is used",
    )
    parser.add_argument(
        "-f",
        "--framesize",
        type=int,
        default=0,
        metavar="<size>",
        help="set framesize, check --list-devices for supported sizes (default: 0 = whatever is currently set)",
    )
    parser.add_argument(
        "-w",
        "--warmup",
        type=int,
        default=3000,
        metavar="<msec>",
        help="time (in miliseconds) to wait before snapshot is taken, to let camera adjust to environment (default: %(default)s)",
    )
    parser.add_argument(
        "-F",
        "--filename",
        type=str,
        default="DSC-%Y%m%d-%H%M%S.jpg",
        metavar="<filename>",
        help="name of the file to save the captured frame to (supports datetime.strftime variables) (default: %(default)s)",
    )

    actions = parser.add_argument_group("Actions")
    actions.add_argument(
        "--list-devices",
        default=False,
        action="store_true",
        help="list all video capture devices",
    )

    args = parser.parse_args()

    if args.device.isdigit():
        args.device = f"/dev/video{args.device}"

    if args.list_devices:
        list_devices()
    else:
        frame = take_snapshot(args)
        save_snapshot(frame, args)

    print("Done.")
