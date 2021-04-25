from io import BytesIO
from v4l2py import Device
from PIL import ImageTk, Image
from tkinter import Tk, Canvas, READABLE

def frame():
    return ImageTk.PhotoImage(Image.open(BytesIO(next(stream)), formats=["JPEG"]))

def update(cam, mask=None):
    cam.image = frame()  # don't loose reference
    canvas.itemconfig(container, image=cam.image)

with Device.from_id(0) as cam:
    fmt = cam.video_capture.get_format()
    cam.video_capture.set_format(fmt.width, fmt.height, "MJPG")
    stream = iter(cam)
    window = Tk()
    window.title("Join")
    window.geometry(f"{fmt.width}x{fmt.height}")
    window.configure(background='grey')
    canvas = Canvas(window, width=fmt.width, height=fmt.height)
    canvas.pack(side = "bottom", fill = "both", expand = "yes")
    container = canvas.create_image(0, 0, anchor="nw")
    window.tk.createfilehandler(cam, READABLE, update)
    window.mainloop()
