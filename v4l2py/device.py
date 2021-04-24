import os
import mmap
import errno
import fcntl
import select
import contextlib
from enum import IntFlag, IntEnum

from . import raw


class Capability(IntFlag):

    VIDEO_CAPTURE = raw.V4L2_CAP_VIDEO_CAPTURE
    VIDEO_OUTPUT = raw.V4L2_CAP_VIDEO_OUTPUT
    VIDEO_OVERLAY = raw.V4L2_CAP_VIDEO_OVERLAY
    VBI_CAPTURE = raw.V4L2_CAP_VBI_CAPTURE
    VBI_OUTPUT = raw.V4L2_CAP_VBI_OUTPUT
    SLICED_VBI_CAPTURE = raw.V4L2_CAP_SLICED_VBI_CAPTURE
    SLICED_VBI_OUTPUT = raw.V4L2_CAP_SLICED_VBI_OUTPUT
    RDS_CAPTURE = raw.V4L2_CAP_RDS_CAPTURE
    VIDEO_OUTPUT_OVERLAY = raw.V4L2_CAP_VIDEO_OUTPUT_OVERLAY
    HW_FREQ_SEEK = raw.V4L2_CAP_HW_FREQ_SEEK
    RDS_OUTPUT = raw.V4L2_CAP_RDS_OUTPUT
    VIDEO_CAPTURE_MPLANE = raw.V4L2_CAP_VIDEO_CAPTURE_MPLANE
    VIDEO_OUTPUT_MPLANE = raw.V4L2_CAP_VIDEO_OUTPUT_MPLANE
    VIDEO_M2M_MPLANE = raw.V4L2_CAP_VIDEO_M2M_MPLANE
    VIDEO_M2M = raw.V4L2_CAP_VIDEO_M2M
    TUNER = raw.V4L2_CAP_TUNER
    AUDIO = raw.V4L2_CAP_AUDIO
    RADIO = raw.V4L2_CAP_RADIO
    MODULATOR = raw.V4L2_CAP_MODULATOR
    SDR_CAPTURE = raw.V4L2_CAP_SDR_CAPTURE
    EXT_PIX_FORMAT = raw.V4L2_CAP_EXT_PIX_FORMAT
    SDR_OUTPUT = raw.V4L2_CAP_SDR_OUTPUT
    META_CAPTURE = raw.V4L2_CAP_META_CAPTURE
    READWRITE = raw.V4L2_CAP_READWRITE
    ASYNCIO = raw.V4L2_CAP_ASYNCIO
    STREAMING = raw.V4L2_CAP_STREAMING
    TOUCH = raw.V4L2_CAP_TOUCH
    DEVICE_CAPS = raw.V4L2_CAP_DEVICE_CAPS


class ImageFormatFlag(IntFlag):
    COMPRESSED = raw.V4L2_FMT_FLAG_COMPRESSED
    EMULATED = raw.V4L2_FMT_FLAG_EMULATED


class BufferType(IntEnum):

    VIDEO_CAPTURE = raw.V4L2_BUF_TYPE_VIDEO_CAPTURE
    VIDEO_OUTPUT = raw.V4L2_BUF_TYPE_VIDEO_OUTPUT
    VIDEO_OVERLAY = raw.V4L2_BUF_TYPE_VIDEO_OVERLAY
    VBI_CAPTURE = raw.V4L2_BUF_TYPE_VBI_CAPTURE
    VBI_OUTPUT = raw.V4L2_BUF_TYPE_VBI_OUTPUT
    SLICED_VBI_CAPTURE = raw.V4L2_BUF_TYPE_SLICED_VBI_CAPTURE
    SLICED_VBI_OUTPUT = raw.V4L2_BUF_TYPE_SLICED_VBI_OUTPUT
    VIDEO_OUTPUT_OVERLAY = raw.V4L2_BUF_TYPE_VIDEO_OUTPUT_OVERLAY
    VIDEO_CAPTURE_MPLANE = raw.V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE
    VIDEO_OUTPUT_MPLANE = raw.V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE
    SDR_CAPTURE = raw.V4L2_BUF_TYPE_SDR_CAPTURE
    SDR_OUTPUT = raw.V4L2_BUF_TYPE_SDR_OUTPUT
    META_CAPTURE = raw.V4L2_BUF_TYPE_META_CAPTURE
    PRIVATE = raw.V4L2_BUF_TYPE_PRIVATE


class Memory(IntEnum):
    MMAP = raw.V4L2_MEMORY_MMAP
    USERPTR = raw.V4L2_MEMORY_USERPTR
    OVERLAY = raw.V4L2_MEMORY_OVERLAY
    DMABUF = raw.V4L2_MEMORY_DMABUF


def _structure_to_dict(structure):
    return dict((field, getattr(structure, field)) for field, _ in structure._fields_)


class Device:

    def __init__(self, filename):
        self.filename = filename
        self._fd = None
        self._buffers = None

    def __del__(self):
        self.close()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.close()

    def __iter__(self):
        with self if self.closed else contextlib.nullcontext():
            if not self._buffers:
                self.create_buffers(1)
                self.queue_all_buffers()
            self.start()
            try:
                while True:
                    yield self.read()
            finally:
                self.stop()

    def _ioctl(self, request, arg=0):
        return fcntl.ioctl(self.fileno(), request, arg)

    @classmethod
    def from_id(self, did):
        return Device("/dev/video{}".format(did))

    def open(self):
        if self._fd is not None:
            raise IOError("Device already opened!")
        self._fd = os.open(self.filename, os.O_RDWR | os.O_NONBLOCK)

    def close(self):
        if self._buffers:
            self.stop()
            for buff in self._buffers:
                buff["mmap"].close()
            self._buffers = None
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def fileno(self):
        return self._fd

    @property
    def closed(self):
        return self._fd is None

    @property
    def capabilities(self):
        cp = raw.v4l2_capability()
        fcntl.ioctl(self, raw.VIDIOC_QUERYCAP, cp)
        result = _structure_to_dict(cp)
        result["capabilities"] = Capability(cp.capabilities)
        return result

    @property
    def supported_formats(self):
        fmt = raw.v4l2_fmtdesc()
        result = []
        for stream_type in (BufferType.VIDEO_CAPTURE, BufferType.VIDEO_CAPTURE_MPLANE,
                            BufferType.VIDEO_OUTPUT, BufferType.VIDEO_OUTPUT_MPLANE,
                            BufferType.VIDEO_OVERLAY):
            fmt.type = stream_type
            for index in range(128):
                fmt.index = index
                try:
                    self._ioctl(raw.VIDIOC_ENUM_FMT, fmt)
                except OSError as error:
                    if error.errno == errno.EINVAL:
                        break
                    else:
                        raise
                result.append(dict(
                    type=stream_type,
                    flags=ImageFormatFlag(fmt.flags),
                    description=fmt.description,
                    pixelformat=fmt.pixelformat))
        return result

    def set_format(self, width, height, pixelformat="MJPG"):
        f = raw.v4l2_format()
        if isinstance(pixelformat, str):
            pixelformat = raw.v4l2_fourcc(*pixelformat.upper())
        f.type = BufferType.VIDEO_CAPTURE
        f.fmt.pix.pixelformat = pixelformat
        f.fmt.pix.field = raw.V4L2_FIELD_ANY
        f.fmt.pix.width = width
        f.fmt.pix.height = height
        f.fmt.pix.bytesperline = 0
        return self._ioctl(raw.VIDIOC_S_FMT, f)

    def get_format(self):
        f = raw.v4l2_format()
        f.type = BufferType.VIDEO_CAPTURE
        self._ioctl(raw.VIDIOC_G_FMT, f)
        return dict(
            width=f.fmt.pix.width,
            height=f.fmt.pix.height,
            pixelformat=raw.v4l2_fourcc2str(f.fmt.pix.pixelformat)
        )

    def set_fps(self, fps):
        p = raw.v4l2_streamparm()
        p.type = BufferType.VIDEO_CAPTURE
        p.parm.capture.timeperframe.numerator = 1
        p.parm.capture.timeperframe.denominator = fps
        return self._ioctl(raw.VIDIOC_S_PARM, p)

    def get_fps(self):
        p = raw.v4l2_streamparm()
        p.type = BufferType.VIDEO_CAPTURE
        self._ioctl(raw.VIDIOC_G_PARM, p)
        return p.parm.capture.timeperframe.denominator

    def create_buffers(self, n):
        if self._buffers:
            raise ValueError("Buffers are already created")
        r = raw.v4l2_requestbuffers()
        r.count = n
        r.type = BufferType.VIDEO_CAPTURE
        r.memory = Memory.MMAP
        self._ioctl(raw.VIDIOC_REQBUFS, r)
        if not r.count:
            raise IOError("Not enough buffer memory")
        buffers = []
        for idx in range(r.count):
            buff = raw.v4l2_buffer()
            buff.index = idx
            buff.type = r.type
            buff.memory = r.memory
            self._ioctl(raw.VIDIOC_QUERYBUF, buff)
            mem = mmap.mmap(self.fileno(), buff.length, offset=buff.m.offset)
            b = dict(length=buff.length, mmap=mem)
            buffers.append(b)
        self._buffers = buffers

    def queue_all_buffers(self):
        if not self._buffers:
            raise ValueError("Buffers have not been created")
        for idx, b in enumerate(self._buffers):
            buff = raw.v4l2_buffer()
            buff.index = idx
            buff.type =  BufferType.VIDEO_CAPTURE
            buff.memory = Memory.MMAP
            self._ioctl(raw.VIDIOC_QBUF, buff)

    def start(self):
        btype = raw.v4l2_buf_type(BufferType.VIDEO_CAPTURE)
        self._ioctl(raw.VIDIOC_STREAMON, btype)

    def stop(self):
        btype = raw.v4l2_buf_type(BufferType.VIDEO_CAPTURE)
        self._ioctl(raw.VIDIOC_STREAMOFF, btype)

    def raw_read(self, queue=True):
        if not self._buffers:
            raise ValueError("Buffers have not been created")
        buff = raw.v4l2_buffer()
        buff.type =  BufferType.VIDEO_CAPTURE
        buff.memory = Memory.MMAP
        self._ioctl(raw.VIDIOC_DQBUF, buff)
        result = self._buffers[buff.index]["mmap"][:buff.bytesused]
        if queue:
            self._ioctl(raw.VIDIOC_QBUF, buff)
        return result

    def read(self, queue=True):
        select.select((self,), (), ())
        return self.raw_read(queue=queue)
