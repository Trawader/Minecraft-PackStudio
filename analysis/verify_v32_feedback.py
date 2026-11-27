"""Feedback regression: color isolation and non-writing history previews. No widgets."""
import sys,copy
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QObject,Signal,QRect
from PySide6.QtGui import QImage,QColor,QRegion
from packstudio.recolor import Settings,render
from packstudio.history_window import History
im=QImage(4,1,QImage.Format.Format_ARGB32)
for x,color in enumerate(('#ffff0000','#ff00ff00','#ff808080','#00335577')):im.setPixelColor(x,0,QColor(color))
region=QRegion(im.rect())
identity=render(im,region,Settings(mode='color'))
assert identity==im
balanced=render(im,QRegion(QRect(0,0,1,1)),Settings(mode='color',green=50))
assert balanced.pixelColor(0,0).green()>0
for x in (1,2,3):assert balanced.pixelColor(x,0)==im.pixelColor(x,0)
selective=render(im,region,Settings(mode='color',color_kind='bands',hue_shift=60))
assert selective.pixelColor(0,0).green()>200
for x in (1,2,3):assert selective.pixelColor(x,0)==im.pixelColor(x,0)
weighted=render(im,region,Settings(mode='color',green=100),{(0,0):0})
assert weighted.pixelColor(0,0)==im.pixelColor(0,0)
print('PASS color defaults, hue bands, masks, transparency and feather weights')
class Canvas(QObject):
    changed=Signal()
    def __init__(self):
        super().__init__();self.image=QImage(im);self.selection_region=QRegion();self.selection_weights={};self.regions=None;self.read_only=False;self.color_preview=None;self.drawing=False;self.task_running=False;self.move_origin=None
    def snapshot(self):return dict(image=QImage(self.image),selection=QRegion(self.selection_region),weights={},view=(),pixel_edit=True)
    def restore_snapshot(self,state):self.image=QImage(state['image']);self.selection_region=QRegion(state['selection']);self.changed.emit()
    def update(self):pass
    def view_image(self):return QImage(self.image)
c=Canvas();writes=[];c.changed.connect(lambda:writes.append(1))
preview=NS(image=QImage(im),flat_image=QImage(im),faces=[],textures={},update=lambda:None)
w=NS(canvas=c,preview=preview,current=None,live_texture=lambda:None)
state=c.snapshot();state['image']=balanced
h=NS(window=w,done=[dict(kind='canvas',after=state,key=('source','a'))],future=[],preview_saved=None,rollback_button=NS(setEnabled=lambda x:None),flush=lambda:None,key=lambda w:None)
h.entries=lambda:History.entries(h);h.can_rollback=lambda row:History.can_rollback(h,row);h.clear_preview=lambda:History.clear_preview(h)
History.preview_row(h,0)
assert c.image==balanced and c.read_only and not writes
h.clear_preview()
assert c.image==im and not c.read_only and not writes and preview.image==im
h.done=[dict(kind='canvas'),dict(kind='blocked'),dict(kind='canvas')]
assert not h.can_rollback(0) and h.can_rollback(1) and not h.can_rollback(2)
h.future=[dict(kind='canvas')]
assert h.can_rollback(3)
h.list=NS(currentRow=lambda:1)
def step(redo=False,barriers=False):
    src=h.future if redo else h.done;dst=h.done if redo else h.future
    dst.append(src.pop());return True
h.step=step
History.rollback(h);assert len(h.done)==2
h.list.currentRow=lambda:3;History.rollback(h);assert len(h.done)==4
print('PASS history preview restores without writes; barriers and selected-state rollback/redo')
