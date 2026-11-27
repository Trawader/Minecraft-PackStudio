"""Selection gestures, unified history and merged contour rendering."""
import os,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt,QPoint,QPointF,QEvent
from PySide6.QtGui import QImage,QColor,QMouseEvent,QRegion,QPainter,QPen
from PySide6.QtWidgets import QApplication
from packstudio.canvas import Canvas
app=QApplication([]);none=Qt.KeyboardModifier.NoModifier;alt=Qt.KeyboardModifier.AltModifier;shift=Qt.KeyboardModifier.ShiftModifier
def mouse(c,kind,point,mods=none):
    button=Qt.MouseButton.NoButton if kind==QEvent.Type.MouseMove else Qt.MouseButton.LeftButton
    buttons=Qt.MouseButton.NoButton if kind==QEvent.Type.MouseButtonRelease else Qt.MouseButton.LeftButton
    p=QPointF(point[0]+.5,point[1]+.5)
    QApplication.sendEvent(c,QMouseEvent(kind,p,p,button,buttons,mods))
def drag(c,a,b,mods=none,release=None):
    mouse(c,QEvent.Type.MouseButtonPress,a,mods)
    mouse(c,QEvent.Type.MouseMove,b,mods if release is None else release)
    mouse(c,QEvent.Type.MouseButtonRelease,b,mods if release is None else release)
def canvas():
    c=Canvas();im=QImage(16,16,QImage.Format.Format_ARGB32);im.fill(QColor('#804020'));c.set_image(im);c.zoom=1;c.offset=QPointF();c.set_tool('select');return c

with patch('packstudio.pointer_input.QGuiApplication.queryKeyboardModifiers',return_value=none):
    outside=canvas();drag(outside,(-4,-4),(20,20));assert outside.selection_region==QRegion(0,0,16,16)
    drag(outside,(-4,-4),(5,15),alt,none);assert outside.selection_region==QRegion(6,0,10,16)
    drag(outside,(-4,-4),(5,15),shift,none);assert outside.selection_region==QRegion(0,0,16,16)
    outside.undo();assert outside.selection_region==QRegion(6,0,10,16)
    outside.rectangle_mode='opaque';outside.image.setPixelColor(0,0,QColor(0,0,0,0))
    drag(outside,(20,20),(-4,-4));assert outside.selection_region==QRegion(0,0,16,16).subtracted(QRegion(0,0,1,1))
    c=canvas();changed=[];c.changed.connect(lambda:changed.append(True));original=QImage(c.image)
    drag(c,(0,0),(9,9));base=QRegion(c.selection_region);assert len(c.history)==1
    drag(c,(2,2),(4,4),alt,none);cut=QRegion(c.selection_region)
    assert cut==base.subtracted(QRegion(2,2,3,3)) # release Alt before mouse-up
    assert len(c.history)==2 and not changed
    c.undo();assert c.selection_region==base and c.image==original and not changed
    c.redo();assert c.selection_region==cut and not changed
    drag(c,(12,0),(13,1),shift,none);added=QRegion(c.selection_region)
    assert added==cut.united(QRegion(12,0,2,2)) and len(c.history)==3
    # Each drag records one action; no-op add retains redo.
    c.undo();future=list(c.future);drag(c,(0,0),(0,0),shift)
    assert c.future==future;c.redo();assert c.selection_region==added
    c.set_tool('pencil');c.color=QColor('red');drag(c,(0,0),(0,0));painted=QImage(c.image)
    assert painted!=original and len(changed)==1
    c.set_tool('select');drag(c,(30,30),(30,30));assert c.selection is None and c.image==painted
    c.undo();assert c.selection_region==added and c.image==painted and len(changed)==1
    c.undo();assert c.image==original and c.selection_region==added and len(changed)==2
    c.undo();assert c.selection_region==cut and len(changed)==2
    c.redo();c.redo();c.redo();assert c.selection is None and c.image==painted
    # Actual holes remain outlined, but internal QRegion decomposition edges vanish.
    c.selection_region=QRegion(1,1,8,3).united(QRegion(2,4,6,4));c.sync_selection()
    outline=c.selection_outline();image=QImage(120,100,QImage.Format.Format_ARGB32);image.fill(QColor('black'))
    p=QPainter(image);p.scale(10,10);p.setPen(QPen(QColor('white'),.1));p.drawPath(outline);p.end()
    assert image.pixelColor(40,40)==QColor('black') # former internal seam
    assert image.pixelColor(40,10)!=QColor('black') # exterior
    ROOT.joinpath('.tmp').mkdir(exist_ok=True);image.save(str(ROOT/'.tmp/v32-selection-outline.png'))
    c.selection_region=QRegion(0,0,10,10).subtracted(QRegion(3,3,3,3));c.sync_selection()
    assert c.selection_outline().contains(QPointF(1,1)) and not c.selection_outline().contains(QPointF(4,4))
    # Anti-alias weights participate in selection undo; read-only selection undo is safe.
    c=canvas();c.image.setPixelColor(1,0,QColor('blue'));c.set_tool('wand');c.wand_tolerance=0;c.wand_antialias=True
    drag(c,(0,0),(0,0));weights=dict(c.selection_weights);region=QRegion(c.selection_region);assert weights
    c.clear_selection();c.undo();assert c.selection_weights==weights and c.selection_region==region
    c.read_only=True;c.undo();assert c.selection is None;c.redo();assert c.selection_region==region
    # New document clears history and cannot resurrect the previous mask.
    c.set_image(c.image);assert not c.history and not c.future and c.selection is None
print('PASS latched Alt/Shift, one history entry per gesture, mixed pixel/selection undo-redo, outside clear, contour seams/holes, AA weights and readonly selection')
