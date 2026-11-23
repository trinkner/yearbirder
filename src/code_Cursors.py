"""Cursors that are safe to use on every platform.

Use waitCursor() everywhere instead of QCursor(Qt.WaitCursor).

macOS has no native wait cursor, so Qt draws one from a PNG bundled inside
QtGui (:/qt-project.org/mac/cursors/images/spincursor.png).  That PNG embeds
the ICC profile of the monitor its author used ("VP2030 SERIES").  When Qt
converts the image for AppKit, QImage::toCGImage() passes CoreGraphics a
color space built from that profile.  Since macOS 26.7.3 (with Qt 6.11.1),
CGImageCreate faults on it with a pointer-authentication trap (SIGTRAP), and
the whole app dies the first time any window shows a wait cursor.  An image
with ANY color space crashes there, even plain sRGB.  The same spinner image
with its color space removed works, so we build the cursor from that.

Verified with a bare PySide6 script: Qt.WaitCursor crashes and SizeAllCursor
(also PNG-backed) crashes; every other shape, and pixmap cursors without a
color space, are fine.
"""

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColorSpace, QCursor, QImage, QPixmap

_SPINNER = ":/qt-project.org/mac/cursors/images/spincursor.png"
_waitCursor = None


def waitCursor():
    """The busy/wait cursor for setOverrideCursor().  Built once, after the
    QApplication exists (the first call is always from a running window)."""
    global _waitCursor
    if _waitCursor is None:
        _waitCursor = QCursor(Qt.WaitCursor)
        if sys.platform == "darwin":
            img = QImage(_SPINNER)
            if not img.isNull():
                img.setColorSpace(QColorSpace())   # drop the embedded ICC profile
                _waitCursor = QCursor(QPixmap.fromImage(img),
                                      img.width() // 2, img.height() // 2)
    return _waitCursor
