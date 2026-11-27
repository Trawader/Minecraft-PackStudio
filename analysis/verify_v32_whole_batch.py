"""Whole-PNG folder batches: animation preservation, scope and cancellation."""
import sys,copy,json
from pathlib import Path
from types import SimpleNamespace as NS
from threading import Event
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtGui import QImage,QColor
from packstudio.core import png,decode
from packstudio.batch_recolor import plan_whole,preview_files
from packstudio.recolor import Settings
im=QImage(2,6,QImage.Format.Format_ARGB32);im.fill(QColor(60,90,120,200));im.setPixelColor(0,0,QColor(1,2,3,0))
files={'folder/a.png':png(im),'folder/deep/b.png':png(im),'other/c.png':png(im),'folder/bad.png':b'invalid','folder/a.png.mcmeta':json.dumps({'animation':{'frames':[0,1,0],'frametime':4}}).encode()}
owner=NS(files=files,kind='pack');original=copy.deepcopy(files)
units,baseline,metadata,errors=plan_whole(owner,{'kind':'folder','path':'folder'})
assert len(units)==2 and len(errors)==1 and all(u.reviewed and u.mask==u.allowed for u in units)
assert units[0].rect==(0,0,2,6) and metadata['folder/a.png.mcmeta']==files['folder/a.png.mcmeta']
for settings in (Settings(mode='opacity',opacity=50),Settings(mode='color',red=40),Settings(mode='range')):
    result=preview_files(units[:1],baseline,settings)
    assert set(result)=={'folder/a.png'}
    image=decode(result['folder/a.png']);assert image.size()==im.size() and image.pixelColor(0,0).alpha()==0
    if settings.mode=='opacity':assert all(image.pixelColor(x,y).alpha()==100 for x,y in ((1,0),(1,2),(1,5)))
    assert owner.files==original
cancel=Event();cancel.set()
try:preview_files(units,baseline,Settings(mode='opacity',opacity=20),cancel)
except InterruptedError:pass
else:raise AssertionError('Cancellation ignored')
assert owner.files==original
print('PASS folder scope, whole animation sheet including unused frames, metadata, excluded PNG, transparent pixels, cancellation, source isolation')
import ast
for p in Path('packstudio').rglob('*.py'):ast.parse(p.read_text('utf-8-sig'))
print('PASS syntax')
