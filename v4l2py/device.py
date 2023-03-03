#
# This file is part of the v4l2py project
#
# Copyright (c) 2021 Tiago Coutinho
# Distributed under the GPLv3 license. See LICENSE for more info.

import asyncio
import collections
import copy
import ctypes
import enum
import errno
import fcntl
import fractions
import logging
import mmap
import os
import pathlib
import typing

from . import raw
from .io import IO, fopen


log = logging.getLogger(__name__)
log_ioctl = log.getChild("ioctl")
log_mmap = log.getChild("mmap")


class V4L2Error(Exception):
    pass


def _enum(name, prefix, klass=enum.IntEnum):
    return klass(
        name,
        (
            (name.replace(prefix, ""), getattr(raw, name))
            for name in dir(raw)
            if name.startswith(prefix)
        ),
    )


Capability = _enum("Capability", "V4L2_CAP_", klass=enum.IntFlag)
PixelFormat = _enum("PixelFormat", "V4L2_PIX_FMT_")
BufferType = _enum("BufferType", "V4L2_BUF_TYPE_")
BufferFlag = _enum("BufferFlag", "V4L2_BUF_FLAG_", klass=enum.IntFlag)
Memory = _enum("Memory", "V4L2_MEMORY_")
ImageFormatFlag = _enum("ImageFormatFlag", "V4L2_FMT_FLAG_", klass=enum.IntFlag)
Field = _enum("Field", "V4L2_FIELD_")
FrameSizeType = _enum("FrameSizeType", "V4L2_FRMSIZE_TYPE_")
FrameIntervalType = _enum("FrameIntervalType", "V4L2_FRMIVAL_TYPE_")
IOC = _enum("IOC", "VIDIOC_", klass=enum.Enum)
InputStatus = _enum("InputStatus", "V4L2_IN_ST_", klass=enum.IntFlag)
InputType = _enum("InputType", "V4L2_INPUT_TYPE_")
InputCapabilities = _enum("InputCapabilities", "V4L2_IN_CAP_", klass=enum.IntFlag)
ControlClass = _enum("ControlClass", "V4L2_CTRL_CLASS_")
ControlType = _enum("ControlType", "V4L2_CTRL_TYPE_")
ControlID = _enum("ControlID", "V4L2_CID_")
SelectionTarget = _enum("SelectionTarget", "V4L2_SEL_TGT_")
Priority = _enum("Priority", "V4L2_PRIORITY_")
TimeCode = _enum("TimeCode", "V4L2_TC_TYPE_")
TimeFlag = _enum("TimeFlag", "V4L2_TC_FLAG_", klass=enum.IntFlag)


def human_pixel_format(ifmt):
    return "".join(map(chr, ((ifmt >> i) & 0xFF for i in range(0, 4 * 8, 8))))


PixelFormat.human_str = lambda self: human_pixel_format(self.value)


Info = collections.namedtuple(
    "Info",
    "driver card bus_info version capabilities device_capabilities crop_capabilities buffers formats frame_sizes inputs controls",
)

ImageFormat = collections.namedtuple(
    "ImageFormat", "type description flags pixel_format"
)

Format = collections.namedtuple("Format", "width height pixel_format")

CropCapability = collections.namedtuple(
    "CropCapability", "type bounds defrect pixel_aspect"
)

Rect = collections.namedtuple("Rect", "left top width height")

Size = collections.namedtuple("Size", "width height")

FrameType = collections.namedtuple(
    "FrameType", "type pixel_format width height min_fps max_fps step_fps"
)

Input = collections.namedtuple(
    "InputType", "index name type audioset tuner std status capabilities"
)


INFO_REPR = """\
driver = {info.driver}
card = {info.card}
bus = {info.bus_info}
version = {info.version}
capabilities = {capabilities}
device_capabilities = {device_capabilities}
buffers = {buffers}
"""


def ioctl(fd, request, arg):
    log_ioctl.debug("%d, request=%s, arg=%s", fd, request.name, arg)
    return fcntl.ioctl(fd, request.value, arg)


def mem_map(fd, length, offset):
    log_mmap.debug("%d, length=%d, offset=%d", fd, length, offset)
    return mmap.mmap(fd, length, offset=offset)


def flag_items(flag):
    return [item for item in type(flag) if item in flag]


def Info_repr(info):
    dcaps = "|".join(cap.name for cap in flag_items(info.device_capabilities))
    caps = "|".join(cap.name for cap in flag_items(info.capabilities))
    buffers = "|".join(buff.name for buff in info.buffers)
    return INFO_REPR.format(
        info=info, capabilities=caps, device_capabilities=dcaps, buffers=buffers
    )


Info.__repr__ = Info_repr


def raw_crop_caps_to_crop_caps(stream_type, crop):
    return CropCapability(
        type=stream_type,
        bounds=Rect(
            crop.bounds.left,
            crop.bounds.top,
            crop.bounds.width,
            crop.bounds.height,
        ),
        defrect=Rect(
            crop.defrect.left,
            crop.defrect.top,
            crop.defrect.width,
            crop.defrect.height,
        ),
        pixel_aspect=crop.pixelaspect.numerator / crop.pixelaspect.denominator,
    )


CropCapability.from_raw = raw_crop_caps_to_crop_caps


def iter_read(fd, ioc, indexed_struct, start=0, stop=128, step=1, ignore_einval=False):
    for index in range(start, stop, step):
        indexed_struct.index = index
        try:
            ioctl(fd, ioc, indexed_struct)
            yield indexed_struct
        except OSError as error:
            if error.errno == errno.EINVAL:
                if ignore_einval:
                    continue
                else:
                    break
            else:
                raise


def frame_sizes(fd, pixel_formats):
    def get_frame_intervals(fmt, w, h):
        val = raw.v4l2_frmivalenum()
        val.pixel_format = fmt
        val.width = w
        val.height = h
        res = []
        for val in iter_read(fd, IOC.ENUM_FRAMEINTERVALS, val):
            # values come in frame interval (fps = 1/interval)
            try:
                ftype = FrameIntervalType(val.type)
            except ValueError:
                break
            if ftype == FrameIntervalType.DISCRETE:
                min_fps = max_fps = step_fps = fractions.Fraction(
                    val.discrete.denominator / val.discrete.numerator
                )
            else:
                if val.stepwise.min.numerator == 0:
                    min_fps = 0
                else:
                    min_fps = fractions.Fraction(
                        val.stepwise.min.denominator, val.stepwise.min.numerator
                    )
                if val.stepwise.max.numerator == 0:
                    max_fps = 0
                else:
                    max_fps = fractions.Fraction(
                        val.stepwise.max.denominator, val.stepwise.max.numerator
                    )
                if val.stepwise.step.numerator == 0:
                    step_fps = 0
                else:
                    step_fps = fractions.Fraction(
                        val.stepwise.step.denominator, val.stepwise.step.numerator
                    )
            res.append(
                FrameType(
                    type=ftype,
                    pixel_format=fmt,
                    width=w,
                    height=h,
                    min_fps=min_fps,
                    max_fps=max_fps,
                    step_fps=step_fps,
                )
            )
        return res

    size = raw.v4l2_frmsizeenum()
    sizes = []
    for pixel_format in pixel_formats:
        size.pixel_format = pixel_format
        size.index = 0
        while True:
            try:
                ioctl(fd, IOC.ENUM_FRAMESIZES, size)
            except OSError:
                break
            if size.type == FrameSizeType.DISCRETE:
                sizes += get_frame_intervals(
                    pixel_format, size.discrete.width, size.discrete.height
                )
            size.index += 1
    return sizes


def read_capabilities(fd):
    caps = raw.v4l2_capability()
    ioctl(fd, IOC.QUERYCAP, caps)
    return caps


def iter_read_formats(fd, type):
    fmt = raw.v4l2_fmtdesc()
    fmt.type = type
    pixel_formats = set(PixelFormat)
    for fmt in iter_read(fd, IOC.ENUM_FMT, fmt):
        pixel_fmt = fmt.pixelformat
        if pixel_fmt not in pixel_formats:
            log.warning(
                "ignored unknown pixel format %s (%d)",
                human_pixel_format(pixel_fmt),
                pixel_fmt,
            )
            continue
        image_format = ImageFormat(
            type=type,
            flags=ImageFormatFlag(fmt.flags),
            description=fmt.description.decode(),
            pixel_format=PixelFormat(pixel_fmt),
        )
        yield image_format


def iter_read_inputs(fd):
    inp = raw.v4l2_input()
    for inp in iter_read(fd, IOC.ENUMINPUT, inp):
        input_type = Input(
            index=inp.index,
            name=inp.name.decode(),
            type=InputType(inp.type),
            audioset=inp.audioset,
            tuner=inp.tuner,
            std=inp.std,
            status=InputStatus(inp.status),
            capabilities=InputCapabilities(inp.capabilities),
        )
        yield input_type


def iter_read_controls(fd):
    ctrl_ext = raw.v4l2_query_ext_ctrl()
    nxt = raw.V4L2_CTRL_FLAG_NEXT_CTRL | raw.V4L2_CTRL_FLAG_NEXT_COMPOUND
    ctrl_ext.id = nxt
    for ctrl_ext in iter_read(fd, IOC.QUERY_EXT_CTRL, ctrl_ext):
        if not (ctrl_ext.flags & raw.V4L2_CTRL_FLAG_DISABLED) and not (
            ctrl_ext.type == raw.V4L2_CTRL_TYPE_CTRL_CLASS
        ):
            yield copy.deepcopy(ctrl_ext)
        ctrl_ext.id |= nxt


def iter_read_menu(fd, ctrl):
    menu = raw.v4l2_querymenu()
    menu.id = ctrl.id
    for menu in iter_read(
        fd,
        IOC.QUERYMENU,
        menu,
        start=ctrl.info.minimum,
        stop=ctrl.info.maximum + 1,
        step=ctrl.info.step,
        ignore_einval=True,
    ):
        yield copy.deepcopy(menu)


def read_info(fd):
    caps = read_capabilities(fd)
    version_tuple = (
        (caps.version & 0xFF0000) >> 16,
        (caps.version & 0x00FF00) >> 8,
        (caps.version & 0x0000FF),
    )
    version_str = ".".join(map(str, version_tuple))
    device_capabilities = Capability(caps.device_caps)
    buffers = [typ for typ in BufferType if Capability[typ.name] in device_capabilities]

    img_fmt_stream_types = {
        BufferType.VIDEO_CAPTURE,
        BufferType.VIDEO_CAPTURE_MPLANE,
        BufferType.VIDEO_OUTPUT,
        BufferType.VIDEO_OUTPUT_MPLANE,
        BufferType.VIDEO_OVERLAY,
    } & set(buffers)

    image_formats = []
    pixel_formats = set()
    for stream_type in img_fmt_stream_types:
        for image_format in iter_read_formats(fd, stream_type):
            image_formats.append(image_format)
            pixel_formats.add(image_format.pixel_format)

    crop = raw.v4l2_cropcap()
    crop_stream_types = {
        BufferType.VIDEO_CAPTURE,
        BufferType.VIDEO_OUTPUT,
        BufferType.VIDEO_OVERLAY,
    } & set(buffers)
    crop_caps = []
    for stream_type in crop_stream_types:
        crop.type = stream_type
        try:
            ioctl(fd, IOC.CROPCAP, crop)
        except OSError:
            continue
        crop_cap = CropCapability.from_raw(stream_type, crop)
        crop_caps.append(crop_cap)

    return Info(
        driver=caps.driver.decode(),
        card=caps.card.decode(),
        bus_info=caps.bus_info.decode(),
        version=version_str,
        capabilities=Capability(caps.capabilities),
        device_capabilities=device_capabilities,
        crop_capabilities=crop_caps,
        buffers=buffers,
        formats=image_formats,
        frame_sizes=frame_sizes(fd, pixel_formats),
        inputs=list(iter_read_inputs(fd)),
        controls=list(iter_read_controls(fd)),
    )


def query_buffer(
    fd, buffer_type: BufferType, memory: Memory, index: int
) -> raw.v4l2_buffer:
    buff = raw.v4l2_buffer()
    buff.type = buffer_type
    buff.memory = memory
    buff.index = index
    buff.reserved = 0
    ioctl(fd, IOC.QUERYBUF, buff)
    return buff


def enqueue_buffer(
    fd, buffer_type: BufferType, memory: Memory, index: int
) -> raw.v4l2_buffer:
    buff = raw.v4l2_buffer()
    buff.type = buffer_type
    buff.memory = memory
    buff.index = index
    buff.reserved = 0
    ioctl(fd, IOC.QBUF, buff)
    return buff


def dequeue_buffer(fd, buffer_type: BufferType, memory: Memory) -> raw.v4l2_buffer:
    buff = raw.v4l2_buffer()
    buff.type = buffer_type
    buff.memory = memory
    buff.index = 0
    buff.reserved = 0
    ioctl(fd, IOC.DQBUF, buff)
    return buff


def request_buffers(
    fd, buffer_type: BufferType, memory: Memory, count: int
) -> raw.v4l2_requestbuffers:
    req = raw.v4l2_requestbuffers()
    req.type = buffer_type
    req.memory = memory
    req.count = count
    ioctl(fd, IOC.REQBUFS, req)
    if not req.count:
        raise IOError("Not enough buffer memory")
    return req


def free_buffers(
    fd, buffer_type: BufferType, memory: Memory
) -> raw.v4l2_requestbuffers:
    req = raw.v4l2_requestbuffers()
    req.type = buffer_type
    req.memory = memory
    req.count = 0
    ioctl(fd, IOC.REQBUFS, req)
    return req


def set_format(fd, buffer_type, width, height, pixel_format="MJPG"):
    f = raw.v4l2_format()
    if isinstance(pixel_format, str):
        pixel_format = raw.v4l2_fourcc(*pixel_format.upper())
    f.type = buffer_type
    f.fmt.pix.pixelformat = pixel_format
    f.fmt.pix.field = Field.ANY
    f.fmt.pix.width = width
    f.fmt.pix.height = height
    f.fmt.pix.bytesperline = 0
    f.fmt.pix.sizeimage = 0
    return ioctl(fd, IOC.S_FMT, f)


def get_raw_format(fd, buffer_type):
    fmt = raw.v4l2_format()
    fmt.type = buffer_type
    ioctl(fd, IOC.G_FMT, fmt)
    return fmt


def get_format(fd, buffer_type):
    f = get_raw_format(fd, buffer_type)
    return Format(
        width=f.fmt.pix.width,
        height=f.fmt.pix.height,
        pixel_format=PixelFormat(f.fmt.pix.pixelformat),
    )


def get_parm(fd, buffer_type):
    p = raw.v4l2_streamparm()
    p.type = buffer_type
    ioctl(fd, IOC.G_PARM, p)
    return p


def set_fps(fd, buffer_type, fps):
    # v4l2 fraction is u32
    max_denominator = int(min(2**32, 2**32 / fps))
    p = raw.v4l2_streamparm()
    p.type = buffer_type
    fps = fractions.Fraction(fps).limit_denominator(max_denominator)
    if buffer_type == BufferType.VIDEO_CAPTURE:
        p.parm.capture.timeperframe.numerator = fps.denominator
        p.parm.capture.timeperframe.denominator = fps.numerator
    elif buffer_type == BufferType.VIDEO_OUTPUT:
        p.parm.output.timeperframe.numerator = fps.denominator
        p.parm.output.timeperframe.denominator = fps.numerator
    else:
        raise ValueError(f"Unsupported buffer type {buffer_type!r}")
    return ioctl(fd, IOC.S_PARM, p)


def get_fps(fd, buffer_type):
    p = get_parm(fd, buffer_type)
    if buffer_type == BufferType.VIDEO_CAPTURE:
        parm = p.parm.capture
    elif buffer_type == BufferType.VIDEO_OUTPUT:
        parm = p.parm.output
    else:
        raise ValueError(f"Unsupported buffer type {buffer_type!r}")
    return fractions.Fraction(
        parm.timeperframe.denominator, parm.timeperframe.numerator
    )


def stream_on(fd, buffer_type):
    btype = raw.v4l2_buf_type(buffer_type)
    return ioctl(fd, IOC.STREAMON, btype)


def stream_off(fd, buffer_type):
    btype = raw.v4l2_buf_type(buffer_type)
    return ioctl(fd, IOC.STREAMOFF, btype)


def set_selection(fd, buffer_type, rectangles):
    sel = raw.v4l2_selection()
    sel.type = buffer_type
    sel.target = raw.V4L2_SEL_TGT_CROP
    sel.rectangles = len(rectangles)
    rects = (raw.v4l2_ext_rect * sel.rectangles)()

    for i in range(sel.rectangles):
        rects[i].r.left = rectangles[i].left
        rects[i].r.top = rectangles[i].top
        rects[i].r.width = rectangles[i].width
        rects[i].r.height = rectangles[i].height

    sel.pr = ctypes.cast(ctypes.pointer(rects), ctypes.POINTER(raw.v4l2_ext_rect))
    ioctl(fd, IOC.S_SELECTION, sel)


def get_selection(
    fd,
    buffer_type: BufferType,
    target: SelectionTarget = SelectionTarget.CROP_DEFAULT,
    max_nb: int = 128,
):
    sel = raw.v4l2_selection()
    sel.type = buffer_type
    sel.target = target
    sel.rectangles = max_nb
    rects = (raw.v4l2_ext_rect * sel.rectangles)()
    sel.pr = ctypes.cast(ctypes.pointer(rects), ctypes.POINTER(raw.v4l2_ext_rect))
    ioctl(fd, IOC.G_SELECTION, sel)
    if sel.rectangles == 0:
        return Rect(
            left=sel.r.left, top=sel.r.top, width=sel.r.width, height=sel.r.height
        )
    else:
        return [
            Rect(
                left=rects[i].r.left,
                top=rects[i].r.top,
                width=rects[i].r.width,
                height=rects[i].r.height,
            )
            for i in range(sel.rectangles)
        ]


def get_control(fd, id):
    control = raw.v4l2_control(id)
    ioctl(fd, IOC.G_CTRL, control)
    return control.value


def set_control(fd, id, value):
    control = raw.v4l2_control(id, value)
    ioctl(fd, IOC.S_CTRL, control)


def get_priority(fd) -> Priority:
    priority = raw.enum()
    ioctl(fd, IOC.G_PRIORITY, priority)
    return Priority(priority.value)


def set_priority(fd, priority: Priority):
    priority = raw.enum(priority.value)
    ioctl(fd, IOC.S_PRIORITY, priority)


# Helpers


def create_buffer(fd, buffer_type: BufferType, memory: Memory) -> raw.v4l2_buffer:
    """request + query buffers"""
    return create_buffer(fd, buffer_type, memory, 1)


def create_buffers(
    fd, buffer_type: BufferType, memory: Memory, count: int
) -> typing.List[raw.v4l2_buffer]:
    """request + query buffers"""
    request_buffers(fd, buffer_type, memory, count)
    return [query_buffer(fd, buffer_type, memory, index) for index in range(count)]


def mmap_from_buffer(fd, buff: raw.v4l2_buffer) -> mmap.mmap:
    return mem_map(fd, buff.length, offset=buff.m.offset)


def create_mmap_buffers(
    fd, buffer_type: BufferType, memory: Memory, count: int
) -> typing.List[mmap.mmap]:
    """create buffers + mmap_from_buffer"""
    return [
        mmap_from_buffer(fd, buff)
        for buff in create_buffers(fd, buffer_type, memory, count)
    ]


def create_mmap_buffer(fd, buffer_type: BufferType, memory: Memory) -> mmap.mmap:
    return create_mmap_buffers(fd, buffer_type, memory, 1)


def enqueue_buffers(
    fd, buffer_type: BufferType, memory: Memory, count: int
) -> typing.List[raw.v4l2_buffer]:
    return [enqueue_buffer(fd, buffer_type, memory, index) for index in range(count)]


class ReentrantContextManager:
    def __init__(self):
        self._context_level = 0

    def __enter__(self):
        if not self._context_level:
            self.open()
        self._context_level += 1
        return self

    def __exit__(self, *exc):
        self._context_level -= 1
        if not self._context_level:
            self.close()


class Device(ReentrantContextManager):
    def __init__(self, name_or_file, read_write=True, io=IO):
        super().__init__()
        self.info = None
        self.controls = {}
        self.io = io
        if isinstance(name_or_file, (str, pathlib.Path)):
            filename = pathlib.Path(name_or_file)
            self._read_write = read_write
            self._fobj = None
        elif isinstance(name_or_file, str):
            filename = pathlib.Path(name_or_file.name)
            self._read_write = "+" in name_or_file.mode
            self._fobj = name_or_file
            # this object context manager won't close the file anymore
            self._context_level += 1
            self._init()
        else:
            raise TypeError("name_or_file must be str or a file object")
        self.log = log.getChild(filename.stem)
        self.filename = filename
        self.index = device_number(filename)

    def __repr__(self):
        return f"<{type(self).__name__} name={self.filename}, closed={self.closed}>"

    def __iter__(self):
        with VideoCapture(self) as stream:
            yield from stream

    async def __aiter__(self):
        with VideoCapture(self) as stream:
            async for frame in stream:
                yield frame

    @classmethod
    def from_id(cls, did: int, **kwargs):
        return cls("/dev/video{}".format(did), **kwargs)

    def _init(self):
        self.info = read_info(self.fileno())
        self.controls = {ctrl.id: Control(self, ctrl) for ctrl in self.info.controls}

    def open(self):
        if not self._fobj:
            self.log.info("opening %s", self.filename)
            self._fobj = self.io.open(self.filename, self._read_write)
            self._init()
            self.log.info("opened %s (%s)", self.filename, self.info.card)

    def close(self):
        if not self.closed:
            self.log.info("closing %s (%s)", self.filename, self.info.card)
            self._fobj.close()
            self._fobj = None
            self.log.info("closed %s (%s)", self.filename, self.info.card)

    def fileno(self):
        return self._fobj.fileno()

    @property
    def closed(self):
        return self._fobj is None or self._fobj.closed

    @property
    def is_blocking(self):
        return os.get_blocking(self.fileno())

    def query_buffer(self, buffer_type, memory, index):
        return query_buffer(self.fileno(), buffer_type, memory, index)

    def enqueue_buffer(
        self, buffer_type: BufferType, memory: Memory, index: int
    ) -> raw.v4l2_buffer:
        return enqueue_buffer(self.fileno(), buffer_type, memory, index)

    def dequeue_buffer(
        self, buffer_type: BufferType, memory: Memory
    ) -> raw.v4l2_buffer:
        return dequeue_buffer(self.fileno(), buffer_type, memory)

    def request_buffers(self, buffer_type, memory, size):
        return request_buffers(self.fileno(), buffer_type, memory, size)

    def create_buffers(
        self, buffer_type: BufferType, memory: Memory, count: int
    ) -> typing.List[raw.v4l2_buffer]:
        return create_buffers(self.fileno(), buffer_type, memory, count)

    def free_buffers(self, buffer_type, memory):
        return free_buffers(self.fileno(), buffer_type, memory)

    def enqueue_buffers(
        self, buffer_type: BufferType, memory: Memory, count: int
    ) -> typing.List[raw.v4l2_buffer]:
        return enqueue_buffers(self.fileno(), buffer_type, memory, count)

    def set_format(self, buffer_type, width, height, pixel_format="MJPG"):
        return set_format(
            self.fileno(), buffer_type, width, height, pixel_format=pixel_format
        )

    def get_format(self, buffer_type):
        return get_format(self.fileno(), buffer_type)

    def set_fps(self, buffer_type, fps):
        return set_fps(self.fileno(), buffer_type, fps)

    def get_fps(self, buffer_type):
        return get_fps(self.fileno(), buffer_type)

    def set_selection(self, buffer_type, rectangles):
        return set_selection(self.fileno(), buffer_type, rectangles)

    def get_selection(self, buffer_type, target):
        return get_selection(self.fileno(), buffer_type, target)

    def get_priority(self) -> Priority:
        return get_priority(self.fileno())

    def set_priority(self, priority: Priority):
        set_priority(self.fileno(), priority)

    def stream_on(self, buffer_type):
        self.log.info("Starting %r stream...", buffer_type.name)
        stream_on(self.fileno(), buffer_type)
        self.log.info("%r stream ON", buffer_type.name)

    def stream_off(self, buffer_type):
        self.log.info("Stoping %r stream...", buffer_type.name)
        stream_off(self.fileno(), buffer_type)
        self.log.info("%r stream OFF", buffer_type.name)

    def write(self, data: bytes) -> None:
        self._fobj.write(data)


class MenuItem:
    def __init__(self, item):
        self.item = item
        self.index = item.index
        self.name = item.name.decode()

    def __repr__(self):
        return f"<{type(self).__name__} index={self.index} name={self.name}>"


class Control:
    def __init__(self, device, info):
        self.device = device
        self.info = info
        self.id = self.info.id
        self.name = info.name.decode()
        self.type = ControlType(self.info.type)
        try:
            self.standard = ControlID(self.id)
        except ValueError:
            self.standard = None
        if self.type == ControlType.MENU:
            self.menu = {
                menu.index: MenuItem(menu)
                for menu in iter_read_menu(self.device._fobj, self)
            }
        else:
            self.menu = {}

    def __repr__(self):
        return f"<{type(self).__name__} name={self.name}, type={self.type.name}, min={self.info.minimum}, max={self.info.maximum}, step={self.info.step}>"

    @property
    def value(self):
        return get_control(self.device, self.id)

    @value.setter
    def value(self, value):
        return set_control(self.device, self.id, value)


class DeviceHelper:
    def __init__(self, device: Device):
        super().__init__()
        self.device = device


class BufferManager(DeviceHelper):
    def __init__(self, device: Device, buffer_type: BufferType, size: int = 2):
        super().__init__(device)
        self.type = buffer_type
        self.size = size
        self.buffers = None
        self.name = type(self).__name__

    def formats(self):
        formats = self.device.info.formats
        return [fmt for fmt in formats if fmt.type == self.type]

    def crop_capabilities(self):
        crop_capabilities = self.device.info.crop_capabilities
        return [crop for crop in crop_capabilities if crop.type == self.type]

    def query_buffer(self, memory, index):
        return self.device.query_buffer(self.type, memory, index)

    def enqueue_buffer(self, memory: Memory, index: int) -> raw.v4l2_buffer:
        return self.device.enqueue_buffer(self.type, memory, index)

    def dequeue_buffer(self, memory: Memory) -> raw.v4l2_buffer:
        return self.device.dequeue_buffer(self.type, memory)

    def enqueue_buffers(self, memory: Memory) -> typing.List[raw.v4l2_buffer]:
        return self.device.enqueue_buffers(self.type, memory, self.size)

    def free_buffers(self, memory: Memory):
        result = self.device.free_buffers(self.type, memory)
        self.buffers = None
        return result

    def create_buffers(self, memory: Memory):
        if self.buffers:
            raise V4L2Error("buffers already requested. free first")
        self.buffers = self.device.create_buffers(self.type, memory, self.size)
        return self.buffers

    def set_format(self, width, height, pixel_format="MJPG"):
        return self.device.set_format(self.type, width, height, pixel_format)

    def get_format(self):
        return self.device.get_format(self.type)

    def set_fps(self, fps):
        return self.device.set_fps(self.type, fps)

    def get_fps(self):
        return self.device.get_fps(self.type)

    def set_selection(self, rectangles):
        return self.device.set_selection(self.type, rectangles)

    def get_selection(self):
        return self.device.get_selection(self.type)

    def stream_on(self):
        self.device.stream_on(self.type)

    def stream_off(self):
        self.device.stream_off(self.type)

    start = stream_on
    stop = stream_off

    def write(self, data: bytes) -> None:
        self.device.write(data)


class Frame:
    __slots__ = ["format", "buff", "data"]

    def __init__(self, data: bytes, buff: raw.v4l2_buffer, format: Format):
        self.format = format
        self.buff = buff
        self.data = data

    def __bytes__(self):
        return self.data

    def __len__(self):
        return len(self.data)

    def __getitem__(self, index):
        return self.data[index]

    def __repr__(self) -> str:
        return f"<{type(self).__name__} width={self.width}, height={self.height}, format={self.pixel_format.name}, frame={self.frame}, timestamp={self.timestamp}>"

    @property
    def width(self):
        return self.format.width

    @property
    def height(self):
        return self.format.height

    @property
    def nbytes(self):
        return self.buff.bytesused

    @property
    def pixel_format(self):
        return PixelFormat(self.format.pixel_format)

    @property
    def index(self):
        return self.buff.index

    @property
    def type(self):
        return BufferType(self.buff.type)

    @property
    def flags(self):
        return BufferFlag(self.buff.flags)

    @property
    def timestamp(self):
        return self.buff.timestamp.secs + self.buff.timestamp.usecs * 1e-3

    @property
    def frame_nb(self):
        return self.buff.sequence

    @property
    def memory(self):
        return Memory(self.buff.memory)

    @property
    def time_type(self):
        if BufferFlag.TIMECODE in self.flags:
            return TimeCode(self.buff.timecode.type)

    @property
    def time_flags(self):
        if BufferFlag.TIMECODE in self.flags:
            return TimeFlag(self.buff.timecode.flags)

    @property
    def time_frame(self):
        if BufferFlag.TIMECODE in self.flags:
            return self.buff.timecode.frames

    @property
    def array(self):
        import numpy

        return numpy.frombuffer(bytes(self), dtype="u1")


class VideoCapture(BufferManager):
    def __init__(self, device: Device, size: int = 2):
        super().__init__(device, BufferType.VIDEO_CAPTURE, size)
        self.buffer = None

    def __enter__(self):
        self.open()
        return self.buffer

    def __exit__(self, *exc):
        self.close()

    def __iter__(self):
        yield from self.buffer

    async def __aiter__(self):
        async for frame in self.buffer:
            yield frame

    def open(self):
        if self.buffer is None:
            self.device.log.info("Preparing for video capture...")
            self.buffer = MemoryMap(self)
            self.buffer.open()
            self.stream_on()
            self.device.log.info("Video capture started!")

    def close(self):
        if self.buffer:
            self.device.log.info("Closing video capture...")
            self.stream_off()
            self.buffer.close()
            self.device.log.info("Video capture closed")


class MemoryMap(ReentrantContextManager):
    def __init__(self, buffer_manager: BufferManager):
        super().__init__()
        self.buffer_manager = buffer_manager
        self.buffers = None
        self.reader = QueueReader(buffer_manager, Memory.MMAP)

    def __iter__(self):
        while True:
            yield self.read()

    async def __aiter__(self):
        device = self.buffer_manager.device
        loop = asyncio.get_event_loop()
        event = asyncio.Event()
        loop.add_reader(device.fileno(), event.set)
        try:
            while True:
                await event.wait()
                event.clear()
                yield self.read()
        finally:
            loop.remove_reader(device.fileno())

    def open(self):
        if self.buffers is None:
            self.buffer_manager.device.log.info("Reserving buffers...")
            fd = self.buffer_manager.device.fileno()
            buffers = self.buffer_manager.create_buffers(Memory.MMAP)
            self.buffers = [mmap_from_buffer(fd, buff) for buff in buffers]
            self.buffer_manager.enqueue_buffers(Memory.MMAP)
            self.format = self.buffer_manager.get_format()
            self.buffer_manager.device.log.info("Buffers reserved")

    def close(self):
        if self.buffers:
            self.buffer_manager.device.log.info("Freeing buffers...")
            for mem in self.buffers:
                mem.close()
            self.buffer_manager.free_buffers(Memory.MMAP)
            self.buffers = None
            self.format = None
            self.buffer_manager.device.log.info("Buffers freed")

    def raw_grab(self):
        with self.reader as buff:
            return self.buffers[buff.index][: buff.bytesused], buff

    def raw_read(self):
        data, buff = self.raw_grab()
        return Frame(data, buff, self.format)

    def wait_read(self):
        device = self.buffer_manager.device
        device.io.select((device,), (), ())
        return self.raw_read()

    def read(self):
        # first time we check what mode device was opened (blocking vs non-blocking)
        # if file was opened with O_NONBLOCK: DQBUF will not block until a buffer
        # is available for read. So we need to do it here
        if self.buffer_manager.device.is_blocking:
            self.read = self.raw_read
        else:
            self.read = self.wait_read
        return self.read()


class QueueReader:
    def __init__(self, buffer_manager: BufferManager, memory: Memory):
        self.buffer_manager = buffer_manager
        self.memory = memory
        self.index = None

    def __enter__(self):
        # get next buffer that has some data in it
        buffer = self.buffer_manager.dequeue_buffer(self.memory)
        self.index = buffer.index
        return buffer

    def __exit__(self, *exc):
        self.buffer_manager.enqueue_buffer(self.memory, self.index)
        self.index = None


class VideoOutput(BufferManager):
    def __init__(self, device: Device, size: int = 2):
        super().__init__(device, BufferType.VIDEO_OUTPUT, size)
        self.buffer = None


def device_number(path):
    num = ""
    for c in str(path)[::-1]:
        if c.isdigit():
            num = c + num
        else:
            break
    return int(num) if num else None


def iter_video_files(path="/dev"):
    path = pathlib.Path(path)
    return sorted(path.glob("video*"))


def iter_devices(path="/dev", **kwargs):
    return (Device(name, **kwargs) for name in iter_video_files(path=path))


def iter_video_capture_files(path="/dev"):
    def filt(filename):
        with fopen(filename) as fobj:
            caps = read_capabilities(fobj.fileno())
            return Capability.VIDEO_CAPTURE in Capability(caps.device_caps)

    return filter(filt, iter_video_files(path))


def iter_video_capture_devices(path="/dev", **kwargs):
    return (Device(name, **kwargs) for name in iter_video_capture_files(path))
