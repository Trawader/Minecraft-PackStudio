"""Exercise actual canvas drag handlers without GUI windows."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from types import SimpleNamespace as NS
from unittest.mock import patch
from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QImage,QColor,QRegion
from packstudio.canvas import Canvas
from packstudio.part_derivation import region_mask
class Harness:
    pass
for name in ('mousePressEvent','mouseMoveEvent','mouseReleaseEvent','select_rect','combine_selection','view_image','view_size','view_region','pixel_task','snapshot','finish_selection'):
    setattr(Harness,name,getattr(Canvas,name))
def event(x,y,modifier=Qt.KeyboardModifier.NoModifier):
    return NS(position=lambda:QPointF(x,y),button=lambda:Qt.MouseButton.LeftButton,buttons=lambda:Qt.MouseButton.LeftButton,modifiers=lambda:modifier,accept=lambda:None)
for mode in ('normal','opaque'):
    c=Harness();c.image=QImage(16,16,QImage.Format.Format_RGBA8888);c.image.fill(Qt.GlobalColor.transparent)
    for y in range(4,12):
        for x in range(4,12):c.image.setPixelColor(x,y,QColor('red'))
    original=c.image.copy()
    c.task_running=False;c.show_rulers=False;c.tool='select';c.read_only=True;c.regions=None;c.gradient_drag=None;c.move_origin=None;c.moving=False
    c.selection_region=QRegion();c.selection_weights={};c.rectangle_mode=mode;c.history=[]
    c.pos=lambda e:(int(e.position().x()),int(e.position().y()))
    c.valid=lambda p:0<=p[0]<16 and 0<=p[1]<16
    c.setFocus=lambda:None;c.cancel_move=lambda:None;c.sync_selection=lambda:None;c.set_hover=lambda p:None;c.checkpoint=lambda s:c.history.append(s)
    with patch('packstudio.canvas.QApplication',NS(startDragDistance=lambda:2)):
        c.mousePressEvent(event(2,2));c.mouseMoveEvent(event(8,8));c.mouseReleaseEvent(event(8,8))
        assert sum(region_mask(c.image,c.selection_region))==25
        if mode=='opaque':assert c.selection_region==QRegion(4,4,5,5)
        c.mousePressEvent(event(9,9,Qt.KeyboardModifier.ShiftModifier));c.mouseMoveEvent(event(13,13));c.mouseReleaseEvent(event(13,13))
        assert sum(region_mask(c.image,c.selection_region))==34
        c.mousePressEvent(event(4,4,Qt.KeyboardModifier.AltModifier));c.mouseMoveEvent(event(5,5));c.mouseReleaseEvent(event(5,5))
        assert sum(region_mask(c.image,c.selection_region))==30
    assert c.image==original and len(c.history)==3
print('PASS normal/magic rectangle press-drag-release, Shift add, Alt subtract, mask extraction, source unchanged')
