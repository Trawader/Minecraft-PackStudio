"""Keep editor modifiers available across Qt pointer and menu event routing."""
from PySide6.QtCore import QObject,QEvent,Qt
from PySide6.QtGui import QGuiApplication,QCursor
from PySide6.QtWidgets import QApplication

KEYS={Qt.Key.Key_Alt:Qt.KeyboardModifier.AltModifier,
      Qt.Key.Key_Shift:Qt.KeyboardModifier.ShiftModifier}


class PointerInput(QObject):
    def __init__(self,app):
        super().__init__(app);self.held=Qt.KeyboardModifier.NoModifier
    def eventFilter(self,obj,event):
        kind=event.type()
        if kind in (QEvent.Type.ApplicationDeactivate,QEvent.Type.WindowDeactivate):
            self.held=Qt.KeyboardModifier.NoModifier
        if kind not in (QEvent.Type.ShortcutOverride,QEvent.Type.KeyPress,QEvent.Type.KeyRelease):return False
        flag=KEYS.get(event.key())
        if flag is None:return False
        if kind==QEvent.Type.KeyPress:self.held|=flag
        elif kind==QEvent.Type.KeyRelease:self.held&=~flag
        # Alt is an editor modifier while the pointer/focus is on a canvas.
        # Keep menu accelerators available everywhere else (and for Alt+letters).
        surfaces=(obj,QApplication.focusWidget(),QApplication.widgetAt(QCursor.pos()))
        active=any(getattr(widget,'editor_pointer_surface',False) for widget in surfaces)
        if active and event.key()==Qt.Key.Key_Alt and QApplication.activePopupWidget() is None and QApplication.activeModalWidget() is None:
            event.accept();return True
        return False


def install(surface):
    surface.editor_pointer_surface=True
    app=QApplication.instance()
    if not hasattr(app,'editor_pointer_input'):
        app.editor_pointer_input=PointerInput(app);app.installEventFilter(app.editor_pointer_input)


def modifiers(event):
    app=QApplication.instance()
    held=getattr(getattr(app,'editor_pointer_input',None),'held',Qt.KeyboardModifier.NoModifier)
    return event.modifiers() | QGuiApplication.queryKeyboardModifiers() | held


def selection_operation(event):
    keys=modifiers(event)
    return 'subtract' if keys & Qt.KeyboardModifier.AltModifier else 'add' if keys & Qt.KeyboardModifier.ShiftModifier else 'replace'


def zoom_steps(event):
    """Read Alt-wheel on Windows as well as ordinary vertical wheel events.

    QWindowsPointerHandler maps WM_MOUSEWHEEL + Alt to angleDelta.x().
    Do not add both axes: a diagonal device gesture must only zoom once.
    """
    angle=event.angleDelta()
    delta=angle.y() or angle.x()
    if delta:return delta/120.0
    pixel=event.pixelDelta()
    return (pixel.y() or pixel.x())/40.0
