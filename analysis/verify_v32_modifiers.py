"""Full-window modifier routing and opaque-rectangle regression."""
import os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt,QPointF,QPoint,QEvent
from PySide6.QtGui import QImage,QColor,QMouseEvent,QWheelEvent,QKeyEvent
from PySide6.QtWidgets import QApplication
from packstudio.studio import StudioWindow
from packstudio.pointer_input import modifiers
app=QApplication([]);none=Qt.KeyboardModifier.NoModifier;left=Qt.MouseButton.LeftButton
def key(widget,kind,key):
    QApplication.sendEvent(widget,QKeyEvent(kind,key,none))
def mouse(widget,kind,x,y):
    button=Qt.MouseButton.NoButton if kind==QEvent.Type.MouseMove else left
    buttons=Qt.MouseButton.NoButton if kind==QEvent.Type.MouseButtonRelease else left
    QApplication.sendEvent(widget,QMouseEvent(kind,QPointF(x,y),QPointF(x,y),button,buttons,none))
def drag(widget,a,b):
    mouse(widget,QEvent.Type.MouseButtonPress,*a);mouse(widget,QEvent.Type.MouseMove,*b);mouse(widget,QEvent.Type.MouseButtonRelease,*b)
def wheel(widget):
    QApplication.sendEvent(widget,QWheelEvent(QPointF(40,40),QPointF(40,40),QPoint(),QPoint(0,120),Qt.MouseButton.NoButton,none,Qt.ScrollPhase.NoScrollPhase,False))

with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='modifier-check-') as tmp:
    os.environ['PACKSTUDIO_SETTINGS_FILE']=tmp+'/settings.ini';os.environ['PACKSTUDIO_NAMING_FILE']=tmp+'/names.json'
    w=StudioWindow(Path(tmp)/'library',drafts=False);w.show();app.processEvents()
    try:
        c=w.canvas;im=QImage(8,4,QImage.Format.Format_ARGB32);im.fill(Qt.GlobalColor.transparent)
        for x,y,a in [(0,0,255),(1,0,1),(1,1,128),(4,0,255),(5,1,255)]:im.setPixelColor(x,y,QColor(200,100,50,a))
        c.set_image(im);c.zoom=10;c.offset=QPointF();c.setFocus();app.processEvents()
        # The pointer events intentionally carry NO modifiers. Press/release events
        # and platform queries must supply held modifiers independently.
        with patch('packstudio.pointer_input.QGuiApplication.queryKeyboardModifiers',return_value=none):
            override=QKeyEvent(QEvent.Type.ShortcutOverride,Qt.Key.Key_Alt,none)
            QApplication.sendEvent(c,override);assert override.isAccepted()
            key(c,QEvent.Type.KeyPress,Qt.Key.Key_Alt);before=c.zoom;wheel(c);assert c.zoom>before
            before=w.preview.zoom;wheel(w.preview);assert w.preview.zoom>before
            key(c,QEvent.Type.KeyRelease,Qt.Key.Key_Alt);before=c.zoom;wheel(c);assert c.zoom==before
            c.zoom=10;c.offset=QPointF()
            menu=w.rectangle_menu();assert len(menu.actions())==2
            menu.actions()[1].trigger();assert c.rectangle_mode=='opaque' and c.tool=='select';menu.deleteLater()
            drag(c,(5,5),(25,25))
            assert c.selection_region.contains(QPoint(1,0)) and c.selection_region.contains(QPoint(1,1))
            assert not c.selection_region.contains(QPoint(0,1))
            key(c,QEvent.Type.KeyPress,Qt.Key.Key_Shift);drag(c,(45,5),(65,25));key(c,QEvent.Type.KeyRelease,Qt.Key.Key_Shift)
            assert c.selection_region.contains(QPoint(0,0)) and c.selection_region.contains(QPoint(5,1))
            key(c,QEvent.Type.KeyPress,Qt.Key.Key_Alt);drag(c,(5,5),(5,5));key(c,QEvent.Type.KeyRelease,Qt.Key.Key_Alt)
            assert not c.selection_region.contains(QPoint(0,0)) and c.selection_region.contains(QPoint(5,1))
            w.set_rectangle_mode('normal');assert c.selection_region.contains(QPoint(5,1))
            drag(c,(25,5),(35,15));assert c.selection_region.contains(QPoint(2,0)) and not c.selection_region.contains(QPoint(5,1))
            # The gesture keeps the mode captured at mouse-down.
            mouse(c,QEvent.Type.MouseButtonPress,45,5);key(c,QEvent.Type.KeyPress,Qt.Key.Key_Shift)
            mouse(c,QEvent.Type.MouseMove,55,15);mouse(c,QEvent.Type.MouseButtonRelease,55,15);key(c,QEvent.Type.KeyRelease,Qt.Key.Key_Shift)
            assert not c.selection_region.contains(QPoint(2,0)) and c.selection_region.contains(QPoint(5,1))
            key(c,QEvent.Type.KeyPress,Qt.Key.Key_Alt);QApplication.sendEvent(w,QEvent(QEvent.Type.WindowDeactivate))
            assert app.editor_pointer_input.held==none
            key(c,QEvent.Type.KeyRelease,Qt.Key.Key_Alt)
        # Native keyboard query fallback works even without a delivered key event.
        w.set_tool('mouse')
        with patch('packstudio.pointer_input.QGuiApplication.queryKeyboardModifiers',return_value=Qt.KeyboardModifier.AltModifier):
            before=c.zoom;wheel(c);assert c.zoom>before
        assert c.image==im
        w.set_rectangle_mode('opaque');w.language_changed(1);assert 'Magic rectangle' in w.tool_buttons['select'].toolTip()
        w.language_changed(0);assert '魔法矩形' in w.tool_buttons['select'].toolTip()
        c.set_atlas(im,[(0,0,2,2),(4,0,1,1)],'fixture');c.zoom=10;c.offset=QPointF()
        with patch('packstudio.pointer_input.QGuiApplication.queryKeyboardModifiers',return_value=none):
            drag(c,(5,5),(15,25))
        assert c.selection_region.contains(QPoint(0,2)) and not c.selection_region.contains(QPoint(1,2))
        print('PASS full-window Alt zoom, Alt subtraction, Shift addition, live modifiers, deactivation reset, opaque rectangle/alpha/atlas/menu/language')
    finally:w.dirty=False;w.close();app.processEvents()
