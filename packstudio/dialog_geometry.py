"""Screen-bounded dialogs; compact forms size from translated content."""
from PySide6.QtCore import QObject,QEvent,QTimer
from PySide6.QtWidgets import QApplication,QDialog,QFileDialog,QInputDialog
from shiboken6 import isValid


def bounded_size(width,height,available_width,available_height):
    return min(width,max(1,available_width-24)),min(height,max(1,available_height-64))


class DialogGeometry(QObject):
    def __init__(self,window):
        super().__init__(window);self.window=window;QApplication.instance().installEventFilter(self)
    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.Show and isinstance(obj,QDialog) and not isinstance(obj,QFileDialog) and obj.isWindow():
            parent=obj
            while parent is not None and parent is not self.window:parent=parent.parent()
            if parent is self.window:QTimer.singleShot(0,lambda:self.fit(obj))
        return False
    def fit(self,dialog):
        if not isValid(dialog) or not dialog.isVisible():return
        area=dialog.screen().availableGeometry()
        if isinstance(dialog,QInputDialog):
            dialog.layout().activate();hint=dialog.sizeHint().expandedTo(dialog.minimumSizeHint())
            dialog.setFixedSize(hint)
        width,height=bounded_size(dialog.width(),dialog.height(),area.width(),area.height())
        dialog.resize(width,height)
        dialog.move(max(area.left()+12,min(dialog.x(),area.right()-dialog.width()-12)),
                    max(area.top()+12,min(dialog.y(),area.bottom()-dialog.height()-40)))
