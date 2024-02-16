#
# This file is part of the v4l2py project
#
# Copyright (c) 2021 Tiago Coutinho
# Distributed under the GPLv3 license. See LICENSE for more info.

# ruff: noqa: F401

import warnings

from .device import (
    Device,
    Frame,
    MemoryMap,
    PixelFormat,
    VideoCapture,
    iter_devices,
    iter_video_capture_devices,
    iter_video_capture_files,
    iter_video_files,
)
from .io import IO, GeventIO

__version__ = "3.0.0"

warnings.warn(
    "v4l2py is no longer being maintained. Please consider using linuxpy.video instead"
)
