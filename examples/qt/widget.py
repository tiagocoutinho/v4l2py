#
# This file is part of the v4l2py project
#
# Copyright (c) 2021 Tiago Coutinho
# Distributed under the GPLv3 license. See LICENSE for more info.

# install extra requirements:
# python3 -m pip install opencv-python qtpy pyqt6

# run from this directory with:
# QT_API=pyqt6 python widget.py

import cv2
from qtpy import QtCore, QtGui, QtWidgets

from v4l2py import Device, PixelFormat, VideoCapture


class QVideo(QtWidgets.QWidget):
    def setFrame(self, frame):
        self.frame = frame
        self.image = None
        self.update()

    def paintEvent(self, _):
        frame = self.frame
        if frame is None:
            return
        if self.image is None:
            if frame.pixel_format == PixelFormat.MJPEG:
                bgr = cv2.imdecode(frame.array, cv2.IMREAD_UNCHANGED)
            elif frame.pixel_format == PixelFormat.YUYV:
                data = frame.array
                data.shape = frame.height, frame.width, -1
                bgr = cv2.cvtColor(data, cv2.COLOR_YUV2BGR_YUYV)
            self.image = QtGui.QImage(
                bgr, frame.width, frame.height, QtGui.QImage.Format.Format_BGR888
            )
        painter = QtGui.QPainter(self)
        painter.drawImage(QtCore.QPointF(), self.image)


def main():
    def update():
        frame = next(stream)
        window.setFrame(frame)

    app = QtWidgets.QApplication([])
    window = QVideo()
    window.show()

    timer = QtCore.QTimer()
    timer.timeout.connect(update)

    with Device.from_id(0) as cam:
        capture = VideoCapture(cam)

        capture.set_format(640, 480, "YUYV")
        print(capture.get_format())
        stream = iter(cam)
        timer.start(0)
        app.exec()


if __name__ == "__main__":
    main()
