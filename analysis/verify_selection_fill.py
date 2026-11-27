"""Fill tool checks without GUI construction."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from threading import Event
from types import SimpleNamespace as NS
from PySide6.QtGui import QImage,QColor,QRegion
from PySide6.QtCore import Qt
from packstudio.pixel_tasks import fill_selection
from packstudio.canvas import Canvas
im=QImage(6,4,QImage.Format.Format_RGBA8888);im.fill(QColor(20,40,60,255));im.setPixelColor(1,1,QColor(0,0,0,0));original=im.copy()
area=QRegion(1,1,2,2).united(QRegion(5,0,1,1));target=QColor(200,10,30,128)
out=fill_selection(im,area,target)
assert out.pixelColor(1,1)==target and out.pixelColor(5,0)==target
assert out.pixelColor(0,0)==im.pixelColor(0,0) and im==original
assert fill_selection(im,QRegion(im.rect()),target).pixelColor(0,3)==target
soft=fill_selection(im,area,target,{(2,1):128})
assert soft.pixelColor(2,1).alpha()==191
cancel=Event();cancel.set()
try:fill_selection(im,area,target,cancel=cancel)
except InterruptedError:pass
else:raise AssertionError('cancel ignored')
for read_only,result_kind in ((False,'changed'),(False,'same'),(False,'cancel'),(True,'changed')):
    edits=[]
    c=NS(task_running=False,show_rulers=False,tool='fill',read_only=read_only,gradient_drag=None,selection_region=area,selection_weights={},color=target,
         setFocus=lambda:None,pos=lambda e:(0,0),valid=lambda p:True,view_image=lambda:im,view_region=lambda:QRegion(im.rect()),
         checkpoint=lambda:edits.append('checkpoint'),replace_view=lambda r:edits.append('replace'),changed=NS(emit=lambda:edits.append('signal')),update=lambda:None)
    c.pixel_task=lambda title,image,work:work(None,None) if result_kind=='changed' else im if result_kind=='same' else None
    event=NS(position=lambda:None,button=lambda:Qt.MouseButton.LeftButton)
    Canvas.mousePressEvent(c,event)
    assert edits==(['checkpoint','replace','signal'] if not read_only and result_kind=='changed' else [])
print('PASS islands, transparent pixels, color alpha, soft edges, full image, cancel, read-only, one history commit, click outside selection')
