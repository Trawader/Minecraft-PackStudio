"""Release reference modes and live-preview races; no UI construction."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from threading import Event
from concurrent.futures import Future
from types import SimpleNamespace as NS
from PySide6.QtGui import QImage,QColor
from packstudio.derivation_reference import reference_transfer,expand_mask,aligned
from packstudio.part_derivation import rgba,luminance
from packstudio.live_recolor import LivePreview,PreviewRenderer
from packstudio.recolor import Settings
from packstudio.core import png
im=QImage(8,8,QImage.Format.Format_RGBA8888);target=QImage(im)
for y in range(8):
 for x in range(8):
  v=50+y*20;im.setPixelColor(x,y,QColor(v,v,v,73 if x==0 else 255));target.setPixelColor(x,y,QColor(255,y*30,y*30,255))
mask=bytearray([1]*64);mask[0]=0;before=rgba(im)
for mode in ('color','position'):
 out=reference_transfer(im,mask,target,bytes([1]*64),100,mode)
 assert out.pixelColor(0,0)==im.pixelColor(0,0)
 assert rgba(out)[3::4]==before[3::4] and rgba(im)==before
 assert reference_transfer(im,mask,target,mask,0,mode)==im
 if mode=='color':
  assert all(abs(luminance(*out.pixelColor(x,y).getRgb()[:3])-luminance(*im.pixelColor(x,y).getRgb()[:3]))<=1 for y in range(8) for x in range(8))
 else:
  assert out.pixelColor(4,0).green()<out.pixelColor(4,7).green()
other=QImage(9,8,QImage.Format.Format_RGBA8888);other.fill(QColor('red'))
try:reference_transfer(im,mask,other,bytes([1]*72),100,'position');raise AssertionError()
except ValueError:pass
line=QImage(5,1,QImage.Format.Format_RGBA8888)
for x in range(5):line.setPixelColor(x,0,QColor(10+x*10,20,30,255))
assert expand_mask(line,b'\1\0\0\0\0',15)==bytearray([1,1,0,0,0])
assert expand_mask(line,b'\1\0\0\0\0',255,overrides={1:False})==bytearray([1,0,0,0,0])
print('PASS alpha, mask, source, shading, position gradient, layout rejection, bounded neighbor expansion and manual protection')
renderer=PreviewRenderer();raw=png(im);cancel=Event();result=renderer.render(raw,Settings(mode='opacity',opacity=50),cancel)
assert result.pixelColor(0,0).alpha()==36
cancel.set()
try:renderer.render(raw,Settings(),cancel);raise AssertionError()
except InterruptedError:pass
seen=[]
for closed,job,revision,count in ((False,1,2,0),(True,1,1,0),(False,2,2,1)):
 f=Future();f.set_result(im);state=NS(future=f,poll=NS(stop=lambda:None),closed=closed,job_revision=job,revision=revision,ready=NS(emit=lambda v:seen.append(v)))
 prior=len(seen);LivePreview.collect(state);assert len(seen)-prior==count and state.future is None
print('PASS canceled preview, stale results discarded, closed-window result suppression, current result delivered')
