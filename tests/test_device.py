from errno import EINVAL
from inspect import isgenerator
from pathlib import Path
from random import randint
from unittest import mock

import pytest

from v4l2py import raw
from v4l2py.device import Device, iter_devices, iter_video_files


class Hardware:
    def __init__(self, filename):
        self.filename = filename
        self.fd = None
        self.fobj = None
        self.input0_name = b"my camera"
        self.driver = b"mock"
        self.card = b"mock camera"
        self.bus_info = b"mock:usb"
        self.version = 5 << 16 | 4 << 8 | 12
        self.version_str = "5.4.12"

    def open(self, filename, mode, buffering=-1):
        self.fd = randint(10, 100)
        self.fobj = mock.Mock()
        self.fobj.fileno.return_value = self.fd
        self.fobj.closed = False
        return self.fobj

    @property
    def closed(self):
        return self.fd is not None

    def ioctl(self, fd, ioc, arg):
        assert self.fd == fd
        if isinstance(arg, raw.v4l2_input):
            if arg.index > 0:
                raise OSError(EINVAL, "ups!")
            arg.name = self.input0_name
            arg.type = raw.V4L2_INPUT_TYPE_CAMERA
        elif isinstance(arg, raw.v4l2_query_ext_ctrl):
            if arg.index > 0:
                raise OSError(EINVAL, "ups!")
            arg.name = b"brightness"
            arg.type = raw.V4L2_CTRL_TYPE_INTEGER
        elif isinstance(arg, raw.v4l2_capability):
            arg.driver = self.driver
            arg.card = self.card
            arg.bus_info = self.bus_info
            arg.version = self.version
        return 0


def test_video_files():
    with mock.patch("v4l2py.device.pathlib.Path.glob") as glob:
        expected_files = ["/dev/video0", "/dev/video55"]
        glob.return_value = expected_files

        assert list(iter_video_files()) == expected_files


def test_device_list():
    assert isgenerator(iter_devices())

    with mock.patch("v4l2py.device.pathlib.Path.glob") as glob:
        expected_files = ["/dev/video0", "/dev/video55"]
        glob.return_value = expected_files
        devices = list(iter_devices())
        assert len(devices) == 2
        for device in devices:
            assert isinstance(device, Device)
        assert {device.filename for device in devices} == {
            Path(filename) for filename in expected_files
        }


def test_device_creation():
    # This should not raise an error until open() is called
    Device("/unknown")

    for name in (1, 1.1, True, [], {}, (), set()):
        with pytest.raises(TypeError):
            Device(name)


def test_device_open():
    filename = "/dev/myvideo"
    hw = Hardware(filename)

    with mock.patch("v4l2py.device.fcntl.ioctl", hw.ioctl):
        device = Device(filename)
        device.opener = hw.open
        device.open()
        assert not device.closed


def test_device_info():
    filename = "/dev/myvideo"
    hw = Hardware(filename)

    with mock.patch("v4l2py.device.fcntl.ioctl", hw.ioctl):
        device = Device(filename)
        device.opener = hw.open
        assert device.info is None
        device.open()
        assert device.info.driver == hw.driver.decode()
        assert device.info.bus_info == hw.bus_info.decode()
        assert device.info.bus_info == hw.bus_info.decode()
        assert device.info.version == hw.version_str
