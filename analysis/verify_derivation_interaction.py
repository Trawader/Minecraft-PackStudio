"""Handler and image tests, without constructing GUI windows."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from types import SimpleNamespace as NS
from PySide6.QtGui import QImage,QColor,QRegion
from packstudio.part_derivation import MaskCanvas,rgba
from packstudio.material_derivation import outlined_preview
from packstudio.canvas import Canvas
image=QImage(16,16,QImage.Format.Format_RGBA8888);image.fill(QColor(90,100,110,127));before=rgba(image)
state=NS(image=image,selection_region=QRegion(),tool='mask_add',mask_brush_size=3,mask_eraser_size=1,last_mask_point=None,pos=lambda e:e,sync_selection=lambda:None)
MaskCanvas.mark(state,(3,3));MaskCanvas.mark(state,(9,3))
assert state.selection_region==QRegion(2,2,9,3)
state.tool='mask_remove';state.last_mask_point=None
MaskCanvas.mark(state,(5,3))
assert state.selection_region==QRegion(2,2,9,3).subtracted(QRegion(5,3,1,1))
assert rgba(image)==before
mask=bytes([int(i%16<8) for i in range(256)])
preview=outlined_preview(image,mask)
assert rgba(image)==before and not preview.isNull()
points=set()
canvas=NS(read_only=False,tool='eraser',color=QColor('red'),eraser_size=5,brush_size=1,selection_weights={},amounts={},editable=lambda p:True,pixel=lambda p:QColor('red'),paint_pixel=lambda p,c:points.add(p),update_pixels=lambda r:None,strokeUpdated=NS(emit=lambda:None))
Canvas.stroke(canvas,(8,8),(8,8))
assert len(points)==25
print('PASS continuous mask brush, separate eraser size, source-safe outline, main eraser footprint')

# A stepped blade creates many QRegion scan bands. Their shared edges must
# never become visible lines inside the selection.
from PySide6.QtCore import Qt
blade=QImage(32,32,QImage.Format.Format_RGBA8888);blade.fill(QColor(20,100,180,255))
mask=bytes(int(4<=y<28 and y//2<=x<y//2+12) for y in range(32) for x in range(32))
original=rgba(blade)
for size in (96,200,427):
    shown=outlined_preview(blade,mask,size,size)
    base=blade.scaled(size,size,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation)
    unchanged=0
    for y in range(size):
        for x in range(size):
            sx,sy=x*32//size,y*32//size
            if 2<=sx<30 and 2<=sy<30 and all(mask[yy*32+xx] for yy in range(sy-2,sy+3) for xx in range(sx-2,sx+3)):
                assert shown.pixel(x,y)==base.pixel(x,y),(size,x,y)
                unchanged+=1
    assert unchanged>0 and rgba(shown)!=rgba(base)
assert rgba(blade)==original
print('PASS stepped selection has no internal seams at three display sizes; source unchanged')
