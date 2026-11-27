"""Optimization equivalence and source identity checks; no UI windows."""
import sys,time,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtGui import QImage,QColor,QRegion
from packstudio.recolor import render,Settings
from packstudio.batch_recolor_dialog import display_parts
root='assets/minecraft/textures/blocks'
a=root+'/sub/a.png';assert display_parts(a,{'kind':'folder','path':root})==['blocks','sub','a.png']
assert display_parts(a,{'kind':'png','path':a})==['a.png']
assert display_parts(a,{'kind':'root'})==a.split('/')
im=QImage(256,2,QImage.Format.Format_RGBA8888)
for y in range(2):
    for x in range(256):im.setPixelColor(x,y,QColor(x,255-x,71,x))
before=QImage(im)
for opacity in (0,1,33,50,99,100):
    fast=render(im,QRegion(im.rect()),Settings(mode='opacity',opacity=opacity))
    old=render(im,QRegion(im.rect()),Settings(mode='opacity',opacity=opacity),{(0,0):255})
    assert fast.convertToFormat(QImage.Format.Format_RGBA8888)==old.convertToFormat(QImage.Format.Format_RGBA8888)
    assert im==before
image=QImage(512,512,QImage.Format.Format_RGBA8888);image.fill(QColor(40,80,120,201));region=QRegion(image.rect());s=Settings(mode='opacity',opacity=50)
start=time.perf_counter();expected=render(image,region,s,{(0,0):255});old_time=time.perf_counter()-start
start=time.perf_counter();actual=render(image,region,s);new_time=time.perf_counter()-start
assert actual==expected
report={'pixels':512*512,'original_seconds':old_time,'scanline_seconds':new_time,'speedup':old_time/new_time,'all_alpha_values_equivalent':True,'source_unchanged':True}
Path('analysis/v32-opacity-optimization.json').write_text(json.dumps(report,indent=2),'utf8')
print(json.dumps(report))
