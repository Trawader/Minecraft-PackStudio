"""Mask conversion and shared selection operations without GUI construction."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from types import SimpleNamespace as NS
from PySide6.QtGui import QImage,QColor,QRegion
from packstudio.part_derivation import mask_region,region_mask
from packstudio.canvas import Canvas
from packstudio.wand import select
im=QImage(5,3,QImage.Format.Format_RGBA8888);im.fill(QColor(10,20,30,255));im.setPixelColor(4,2,QColor(10,20,30,0))
original=im.copy();mask=bytearray([1,1,0,1,0,0,1,0,0,0,0,0,0,0,0])
assert region_mask(im,mask_region(mask,5))==mask
assert not any(region_mask(im,QRegion()))
assert region_mask(im,QRegion(im.rect()))[-1]==0
for mode,expected in [('add',QRegion(0,0,3,1)),('subtract',QRegion(0,0,1,1)),('replace',QRegion(1,0,2,1))]:
 state=NS(selection_operation=mode,selection_before=QRegion(0,0,2,1),weights_before={},selection_weights={},sync_selection=lambda:None)
 Canvas.combine_selection(state,QRegion(1,0,2,1),{})
 assert state.selection_region==expected
region,weights=select(im,(0,0),QRegion(im.rect()),0,True,False)
assert sum(region_mask(im,region))==14
assert im==original
print('PASS mask round trip, empty/transparent masks, add/subtract/replace, shared wand, source unchanged')
