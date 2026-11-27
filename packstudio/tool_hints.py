"""Short, consistent hover delay for compact editor buttons."""
from PySide6.QtCore import QObject,QEvent,QTimer,Qt,QPoint
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication,QToolTip


class ToolHint(QObject):
    def __init__(self,button):
        super().__init__(button);self.button=button
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(180)
        self.timer.timeout.connect(self.show)
        # Application filters receive input before disabled widgets discard it.
        # Left-click availability stays unchanged; settings remain reachable.
        QApplication.instance().installEventFilter(self)
    def show(self):
        if self.button.isVisible() and self.button.underMouse():
            QToolTip.showText(QCursor.pos(),self.button.toolTip(),self.button)
    def open_context(self,pos):
        # Open only after the originating mouse release has finished dispatching.
        # Otherwise the same release can dismiss a newly opened popup.
        point=QPoint(pos)
        QTimer.singleShot(0,self.button,lambda:self.button.customContextMenuRequested.emit(point))
    def eventFilter(self,obj,event):
        if obj is not self.button:return False
        if self.button.contextMenuPolicy()==Qt.ContextMenuPolicy.CustomContextMenu:
            if event.type() in (QEvent.Type.MouseButtonPress,QEvent.Type.MouseButtonRelease) and event.button()==Qt.MouseButton.RightButton:
                self.timer.stop();QToolTip.hideText()
                if event.type()==QEvent.Type.MouseButtonRelease and self.button.rect().contains(event.position().toPoint()):
                    self.open_context(event.position().toPoint())
                event.accept();return True
            if event.type()==QEvent.Type.ContextMenu:
                # Mouse context events duplicate the explicit release above.
                if event.reason()==event.Reason.Keyboard:self.open_context(self.button.rect().center())
                event.accept();return True
        if event.type()==QEvent.Type.Enter:self.timer.start()
        elif event.type() in (QEvent.Type.Leave,QEvent.Type.Hide,QEvent.Type.MouseButtonPress):
            self.timer.stop();QToolTip.hideText()
        elif event.type()==QEvent.Type.ToolTip:return True
        return False
