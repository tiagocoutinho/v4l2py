import logging

from v4l2py.device import (
    BufferType,
    Memory,
    create_mmap_buffer,
    fopen,
    query_buffer,
    set_format,
)

VideoCapture = BufferType.VideoCapture
MMAP = Memory.MMAP

fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
logging.basicConfig(level="DEBUG", format=fmt)

device = fopen("/dev/video5")
set_format(device, VideoCapture, 640, 480, "MJPG")
memory = create_mmap_buffer(device, VideoCapture, MMAP)
