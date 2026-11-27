"""Audit regressions and deterministic retention measurements; no UI windows."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from types import SimpleNamespace as NS
from unittest.mock import patch
from PySide6.QtGui import QImage,QColor
from packstudio import builtin_assets as assets
from packstudio.material_derivation import DerivationDialog
from packstudio.resource_editors import ResourceEditors
assets._blob_cache.clear();assets._blob_bytes=0
loads=[]
def read(name):loads.append(name);return bytes(1024*1024)
with patch.object(assets,'store',return_value=(NS(read=read),{})):
    for i in range(128):assets.blob(str(i))
    assert len(assets._blob_cache)==32 and assets._blob_bytes==32*1024*1024
    old=len(loads);assets.blob('127');assert len(loads)==old
    assets.blob('0');assert len(loads)==old+1
retained=assets._blob_bytes
assets._blob_cache.clear();assets._blob_bytes=0
with patch.object(assets,'store',return_value=(NS(read=lambda name:bytes(assets.CACHE_BYTES+1)),{})):
    assert len(assets.blob('oversize'))>assets.CACHE_BYTES
    assert not assets._blob_cache and assets._blob_bytes==0
image=QImage(1024,1024,QImage.Format.Format_RGBA8888);image.fill(QColor('red'))
calls=[];strength=[100];ramp=[((0,0,0),(100,100,100),(255,255,255))]
w=NS(preview_cache=None,mask_revision=0,strength=NS(value=lambda:strength[0]),current_ramp=lambda p:ramp[0],generate=lambda p,preview:(calls.append(p) or image))
for i in range(20):result=DerivationDialog.preview_result(w,'test')
assert len(calls)==1 and result.sizeInBytes()<=320*200*4
strength[0]=50;DerivationDialog.preview_result(w,'test');assert len(calls)==2
w.mask_revision+=1;DerivationDialog.preview_result(w,'test');assert len(calls)==3
ramp[0]=((5,5,5),(100,100,100),(255,255,255));DerivationDialog.preview_result(w,'test');assert len(calls)==4
for valid in (False,True):
    deletes=[];menu=NS(exec=lambda p:None,deleteLater=lambda:deletes.append(1))
    owner=NS(cards=NS(itemAt=lambda p:NS(data=lambda r:{}),viewport=lambda:NS(mapToGlobal=lambda p:p)),window=NS(resource_menu=lambda d:menu))
    with patch('shiboken6.isValid',return_value=valid):ResourceEditors.card_menu(owner,None)
    assert bool(deletes)==valid
report={'status':'passed','synthetic_cache_before_bytes':128*1024*1024,'synthetic_cache_after_bytes':retained,'identical_preview_requests':20,'render_calls':1,'preview_cache_max_bytes':320*200*4,'oversized_blob_cached':False,'destroyed_menu_cleanup':'passed'}
Path('analysis/audit-20261126-results.json').write_text(json.dumps(report,indent=2),'utf-8')
print(json.dumps(report))
