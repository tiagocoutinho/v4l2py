import os
import enum
import mmap
import errno
import fcntl
import select
import collections

from . import raw


def _enum(name, prefix, klass=enum.IntEnum):
    return klass(name,
        ((name.replace(prefix, ""), getattr(raw, name))
        for name in dir(raw) if name.startswith(prefix)))


Capability = _enum("Capability", "V4L2_CAP_", klass=enum.IntFlag)
PixelFormat = _enum("PixelFormat", "V4L2_PIX_FMT_")
BufferType = _enum("BufferType", "V4L2_BUF_TYPE_")
Memory = _enum("Memory", "V4L2_MEMORY_")
ImageFormatFlag = _enum("ImageFormatFlag", "V4L2_FMT_FLAG_", klass=enum.IntFlag)
Field = _enum("Field", "V4L2_FIELD_")
IOC = _enum("IOC", "VIDIOC_", klass=enum.Enum)


Info = collections.namedtuple(
    "Info", "driver card bus_info version physical_capabilities capabilities buffers formats")


ImageFormat = collections.namedtuple(
    "ImageFormat", "type description flags pixelformat")


def read_info(fd):
    caps = raw.v4l2_capability()
    fcntl.ioctl(fd, IOC.QUERYCAP.value, caps)
    version_tuple = (
        (caps.version & 0xFF0000) >> 16,
        (caps.version & 0x00FF00) >> 8,
        (caps.version & 0x0000FF),
    )
    version_str = ".".join(map(str, version_tuple))
    device_capabilities=Capability(caps.device_caps)
    buffers = [
        typ for typ in BufferType
        if Capability[typ.name] in device_capabilities
    ]

    fmt = raw.v4l2_fmtdesc()
    img_fmt_stream_types = {
        BufferType.VIDEO_CAPTURE, BufferType.VIDEO_CAPTURE_MPLANE,
        BufferType.VIDEO_OUTPUT, BufferType.VIDEO_OUTPUT_MPLANE,
        BufferType.VIDEO_OVERLAY
    } & set(buffers)

    formats = []
    for stream_type in img_fmt_stream_types:
        fmt.type = stream_type
        for index in range(128):
            fmt.index = index
            try:
                fcntl.ioctl(fd, IOC.ENUM_FMT.value, fmt)
            except OSError as error:
                if error.errno == errno.EINVAL:
                    break
                else:
                    raise
            formats.append(ImageFormat(
                type=stream_type,
                flags=ImageFormatFlag(fmt.flags),
                description=fmt.description,
                pixelformat=PixelFormat(fmt.pixelformat)))

    return Info(
        driver=caps.driver.decode(),
        card=caps.card.decode(),
        bus_info=caps.bus_info.decode(),
        version=version_str,
        physical_capabilities=Capability(caps.capabilities),
        capabilities=device_capabilities,
        buffers=buffers,
        formats=formats
    )


class Device:

    def __init__(self, filename):
        self._fd = None
        self._info = None
        self._context_level = 0
        self.filename = filename
        self.video_capture = VideoCapture(self)

    def __enter__(self):
        if not self._context_level:
            self.open()
        self._context_level += 1
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self._context_level -= 1
        if not self._context_level:
            self.close()

    def __iter__(self):
        with self:
            for frame in self.video_capture:
                yield frame

    def _ioctl(self, request, arg=0):
        return fcntl.ioctl(self, request, arg)

    @classmethod
    def from_id(self, did):
        return Device("/dev/video{}".format(did))

    def open(self):
        if self._fd is not None:
            raise IOError("Device already opened!")
        self._fd = os.open(self.filename, os.O_RDWR | os.O_NONBLOCK)

    def close(self):
        self.video_capture.close()
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def fileno(self):
        return self._fd

    @property
    def closed(self):
        return self._fd is None

    @property
    def info(self):
        if self._info is None:
            with self:
                self._info = read_info(self)
        return self._info


class BaseBuffer:

    def __init__(self, device, index=0, buffer_type=BufferType.VIDEO_CAPTURE, queue=True):
        self.device = device
        self.index = index
        self.buffer_type = buffer_type
        self.queue = queue
        self._context_level = 0

    def _buffer(self):
        buff = raw.v4l2_buffer()
        buff.index = self.index
        buff.type = self.buffer_type
        return buff

    def __enter__(self):
        if not self._context_level:
            self.open()
        self._context_level += 1
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self._context_level -= 1
        if not self._context_level:
            self.close()

    def _ioctl(self, request, arg=0):
        return self.device._ioctl(request.value, arg=arg)

    def open(self):
        pass

    def close(self):
        pass


class BufferMMAP(BaseBuffer):

    mmap = None

    def _buffer(self):
        buff = super()._buffer()
        buff.memory = Memory.MMAP
        return buff

    def open(self):
        if self.mmap is not None:
            raise ValueError("Buffer are already created")
        buff = self._buffer()
        self._ioctl(IOC.QUERYBUF, buff)
        self.mmap = mmap.mmap(self.device.fileno(), buff.length, offset=buff.m.offset)
        self.length = buff.length
        if self.queue:
            self._ioctl(IOC.QBUF, buff)

    def close(self):
        if self.mmap is not None:
            self.mmap.close()
            self.mmap = None

    def raw_read(self, buff):
        if self.mmap is None:
            raise ValueError("Buffer has not been created")
        result = self.mmap[:buff.bytesused]
        if self.queue:
            self._ioctl(IOC.QBUF, buff)
        return result

    def read(self, buff):
        select.select((self.device,), (), ())
        return self.raw_read(buff)


class Buffers:

    def __init__(self, device, buffer_type=BufferType.VIDEO_CAPTURE,
                 buffer_size=1, buffer_queue=True, memory=Memory.MMAP):
        self.device = device
        self.buffer_size = buffer_size
        self.buffer_type = buffer_type
        self.buffer_queue = buffer_queue
        self.memory = memory
        self._buffers = None
        self._context_level = 0

    def __enter__(self):
        if not self._context_level:
            self.open()
        self._context_level += 1
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self._context_level -= 1
        if not self._context_level:
            self.close()

    def _ioctl(self, request, arg=0):
        return self.device._ioctl(request.value, arg=arg)

    def _create_buffer(self, index):
        if self.memory != Memory.MMAP:
            raise TypeError(f"Unsupported buffer type {self.memory.name!r}")
        buff = BufferMMAP(self.device, index, self.buffer_type, self.buffer_queue)
        buff.open()
        return buff

    def _create_buffers(self):
        if self._buffers:
            raise ValueError("Buffers are already created")
        r = raw.v4l2_requestbuffers()
        r.count = self.buffer_size
        r.type = self.buffer_type
        r.memory = self.memory
        self._ioctl(IOC.REQBUFS, r)
        if not r.count:
            raise IOError("Not enough buffer memory")
        self._buffers = [self._create_buffer(idx) for idx in range(r.count)]

    def open(self):
        self._create_buffers()

    def close(self):
        if self._buffers:
            for buff in self._buffers:
                buff.close()
            self._buffers = None

    def raw_read(self):
        if not self._buffers:
            raise ValueError("Buffers have not been created")
        buff = raw.v4l2_buffer()
        buff.type = self.buffer_type
        buff.memory = Memory.MMAP
        self._ioctl(IOC.DQBUF, buff)
        return self._buffers[buff.index].raw_read(buff)

    def read(self):
        select.select((self.device,), (), ())
        return self.raw_read()


class VideoCapture:

    def __init__(self, device, buffer_type=BufferType.VIDEO_CAPTURE, buffer_size=1,
                 buffer_queue=True, memory=Memory.MMAP):
        self.device = device
        self.buffer_type = buffer_type
        self._buffers = Buffers(device, buffer_type, buffer_size, buffer_queue, memory)
        self._context_level = 0

    def __enter__(self):
        if not self._context_level:
            self.open()
        self._context_level += 1
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self._context_level -= 1
        if not self._context_level:
            self.close()

    def __iter__(self):
        with self:
            self.start()
            try:
                while True:
                    yield self.read()
            finally:
                self.stop()

    def _ioctl(self, request, arg=0):
        return self.device._ioctl(request.value, arg=arg)

    def open(self):
        self._buffers.open()

    def close(self):
        self._buffers.close()

    @property
    def formats(self):
        return [fmt for fmt in self.device.info.formats if fmt.type == self.buffer_type]

    def set_format(self, width, height, pixelformat="MJPG"):
        f = raw.v4l2_format()
        if isinstance(pixelformat, str):
            pixelformat = raw.v4l2_fourcc(*pixelformat.upper())
        f.type = self.buffer_type
        f.fmt.pix.pixelformat = pixelformat
        f.fmt.pix.field = Field.ANY
        f.fmt.pix.width = width
        f.fmt.pix.height = height
        f.fmt.pix.bytesperline = 0
        return self._ioctl(IOC.S_FMT, f)

    def get_format(self):
        f = raw.v4l2_format()
        f.type = self.buffer_type
        self._ioctl(IOC.G_FMT, f)
        return dict(
            width=f.fmt.pix.width,
            height=f.fmt.pix.height,
            pixelformat=raw.v4l2_fourcc2str(f.fmt.pix.pixelformat)
        )

    def set_fps(self, fps):
        p = raw.v4l2_streamparm()
        p.type = self.buffer_type
        p.parm.capture.timeperframe.numerator = 1
        p.parm.capture.timeperframe.denominator = fps
        return self._ioctl(IOC.S_PARM, p)

    def get_fps(self):
        p = raw.v4l2_streamparm()
        p.type = self.buffer_type
        self._ioctl(IOC.G_PARM, p)
        return p.parm.capture.timeperframe.denominator

    def start(self):
        btype = raw.v4l2_buf_type(self.buffer_type)
        self._ioctl(IOC.STREAMON, btype)

    def stop(self):
        btype = raw.v4l2_buf_type(self.buffer_type)
        self._ioctl(IOC.STREAMOFF, btype)

    def raw_read(self):
        return self._buffers.raw_read()

    def read(self):
        return self._buffers.read()


async def VideoStreamAsync(video_capture):
    import asyncio
    loop = asyncio.get_event_loop()
    event = asyncio.Event()
    fd = video_capture.device.fileno()
    with video_capture:
        loop.add_reader(fd, event.set)
        try:
            video_capture.start()
            while True:
                await event.wait()
                event.clear()
                yield video_capture.raw_read()
        finally:
            video_capture.stop()
            loop.remove_reader(fd)

