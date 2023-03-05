#
# This file is part of the v4l2py project
#
# Copyright (c) 2021 Tiago Coutinho
# Distributed under the GPLv3 license. See LICENSE for more info.

import logging
from io import BytesIO
from tkinter import READABLE, Canvas, Tk

from PIL import Image, ImageTk

from v4l2py import Device, VideoCapture


fmt = "%(threadName)-10s %(asctime)-15s %(levelname)-5s %(name)s: %(message)s"
logging.basicConfig(level="INFO", format=fmt)


def frame():
    frame = next(stream)
    buff = BytesIO(bytes(frame))
    image = Image.open(buff, formats=["JPEG"])
    return ImageTk.PhotoImage(image)


def update(cam, mask=None):
    cam.image = frame()  # don't loose reference
    canvas.itemconfig(container, image=cam.image)


with Device.from_id(0) as cam:
    video_capture = VideoCapture(cam)
    fmt = video_capture.get_format()
    video_capture.set_format(fmt.width, fmt.height, "MJPG")
    with video_capture as buffers:
        stream = iter(buffers)
        window = Tk()
        window.title("Join")
        window.geometry(f"{fmt.width}x{fmt.height}")
        window.configure(background="grey")
        canvas = Canvas(window, width=fmt.width, height=fmt.height)
        canvas.pack(side="bottom", fill="both", expand="yes")
        container = canvas.create_image(0, 0, anchor="nw")
        window.tk.createfilehandler(cam, READABLE, update)
        window.mainloop()
