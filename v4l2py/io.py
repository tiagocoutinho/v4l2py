#
# This file is part of the v4l2py project
#
# Copyright (c) 2021 Tiago Coutinho
# Distributed under the GPLv3 license. See LICENSE for more info.

import os
import functools
import select


def fopen(path, rw=False, blocking=False):
    kwargs = dict(buffering=0)
    if not blocking:

        def opener(path, flags):
            return os.open(path, flags | os.O_NONBLOCK)

        kwargs["opener"] = opener
    return open(path, "rb+" if rw else "rb", **kwargs)


class IO:
    open = functools.partial(fopen, blocking=False)
    select = select.select


class GeventIO:
    @staticmethod
    def open(path, rw=False):
        mode = "rb+" if rw else "rb"
        import gevent.fileobject

        return gevent.fileobject.FileObject(path, mode, buffering=0)

    @staticmethod
    def select(*args, **kwargs):
        import gevent.select

        return gevent.select.select(*args, **kwargs)
