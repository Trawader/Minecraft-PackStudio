import os,sys,threading
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen';sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QColor,QRegion
from packstudio.pixel_tasks import fill,opaque,background,execute
from packstudio.wand import select
from packstudio.canvas import Canvas
app=QApplication([])
im=QImage(300,300,QImage.Format.Format_ARGB32);im.fill(QColor('red'));before=QImage(im);area=QRegion(im.rect())
for work in (lambda c,p:fill(im,(0,0),area,QColor('blue'),cancel=c,progress=p),lambda c,p:opaque(im,area,c,p),lambda c,p:background(im,area,c,p),lambda c,p:select(im,(0,0),area,cancel=c,progress=p)):
 cancel=threading.Event();updates=[]
 def progress(done,total):
  updates.append((done,total));cancel.set()
 try:work(cancel,progress);raise AssertionError('cancel ignored')
 except InterruptedError:pass
 assert updates and im==before
# The selection is a traversal boundary, not just a write mask.
allowed=QRegion(0,0,3,3).united(QRegion(5,0,3,3))
result=fill(im,(0,0),allowed,QColor(0,0,0,0))
assert result.pixelColor(0,0).alpha()==0 and result.pixelColor(5,0)==QColor('red') and im==before
canvas=Canvas();canvas.set_image(im);history=list(canvas.history)
with patch('packstudio.task_progress.run_progress',side_effect=InterruptedError) as worker:
 assert canvas.pixel_task('test',im,lambda c,p:im) is None
 assert worker.called and not canvas.task_running and canvas.image==before and canvas.history==history
def stale(cancel,progress):
 canvas.image.setPixelColor(0,0,QColor('green'));return before
with patch('packstudio.task_progress.run_progress',side_effect=lambda parent,title,work:work(None,None)):
 assert canvas.pixel_task('test',im,stale) is None
assert canvas.image.pixelColor(0,0)==QColor('green') and not canvas.task_running
print('PASS pixel-task progress, mid-operation cancellation, immutable originals, connectivity boundaries, canceled history, stale result rejection')
