"""Derivation interaction handlers and pixel parity; no GUI."""
import sys,time
from pathlib import Path
from types import SimpleNamespace as NS
from threading import Event
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QColor
from packstudio.core import Vanilla,decode,png
from packstudio.material_derivation import DerivationDialog,generate_files,render_target,anchor
from packstudio.part_derivation import transfer,part_mask,histogram
v=Vanilla();source=decode(v.get('1.20.6','assets/minecraft/textures/block/red_concrete.png'))
target=decode(v.get('1.20.6','assets/minecraft/textures/block/blue_concrete.png'))
mask=part_mask(source,'concrete');target_mask=part_mask(target,'concrete');hist=histogram(source,mask)
path='assets/minecraft/textures/block/blue_concrete.png';raw=png(target);colour=anchor(target)
job=(path,raw,bytes(target_mask),colour,colour,False)
before=png(source);progress=[]
for strength in (0,35,100):
    files=generate_files(source,bytes(mask),[job],strength,hist,b'{"texture":{"blur":false}}',progress=lambda a,b:progress.append((a,b)))
    result=decode(files[path]);expected=transfer(source,mask,target,target_mask,strength,hist)
    assert result.convertToFormat(QImage.Format.Format_RGBA8888)==expected.convertToFormat(QImage.Format.Format_RGBA8888) and result.size()==source.size()
    assert files[path+'.mcmeta']==b'{"texture":{"blur":false}}'
assert before==png(source) and progress[-1]==(1,1)
# Exact boundary and alpha protection for partial masks.
source.setPixelColor(0,0,QColor(12,34,56,73));mask[0]=0
out=render_target(source,mask,raw,target_mask,100,hist,colour,(200,80,40),True)
assert out.pixelColor(0,0)==source.pixelColor(0,0)
assert all(out.pixelColor(x,y).alpha()==source.pixelColor(x,y).alpha() for y in range(source.height()) for x in range(source.width()))
print('PASS existing algorithm parity, mask/alpha and metadata preservation')
cancel=Event();cancel.set()
try:generate_files(source,mask,[job],100,hist,None,cancel);raise AssertionError('Cancellation ignored')
except InterruptedError:pass
print('PASS canceled generation returns no project output')
# Preview selection is independent of check state; apply requires checks + tool review.
class Item:
    def __init__(self,path,checked):self.path=path;self.checked=checked
    def data(self,role):return self.path
    def checkState(self):return Qt.CheckState.Checked if self.checked else Qt.CheckState.Unchecked
    def setCheckState(self,state):self.checked=state==Qt.CheckState.Checked
items=[Item('a',False),Item('b',True)];ui={}
state=NS(list=NS(count=lambda:2,item=lambda i:items[i],currentItem=lambda:items[0],blockSignals=lambda value:None),
         window=NS(tr=lambda zh,en:en),family='equipment:sword',confirm_mask=NS(isChecked=lambda:False),
         add_button=NS(setText=lambda text:ui.update(text=text),setEnabled=lambda value:ui.update(enabled=value)))
state.checked_paths=lambda:DerivationDialog.checked_paths(state);state.sync_actions=lambda:DerivationDialog.sync_actions(state)
assert DerivationDialog.selected_path(state)=='a' and state.checked_paths()==['b']
state.sync_actions();assert ui['enabled'] and '(1)' in ui['text']
state.confirm_mask.isChecked=lambda:True;state.sync_actions();assert ui['enabled']
DerivationDialog.check_all(state,False);assert not ui['enabled'] and not state.checked_paths()
print('PASS selection/check independence and composition button gating')
# Snapshot protection is checked without changing any resource.
owner=NS(files={'source.png':before,path:raw});state=NS(owner=owner,descriptor={'origin':'source'},path='source.png',original=before,metadata=None,
    targets={path:(raw,None,True)},version='1.20.6',window=NS(source=lambda origin:owner,vanilla=v,layers=[]))
DerivationDialog.validate_targets(state,[path]);owner.files[path]=b'changed'
try:DerivationDialog.validate_targets(state,[path]);raise AssertionError('Changed reference accepted')
except ValueError:pass
print('PASS changed reference rejected')

from packstudio.core import import_pack
from packstudio.layouts import tag_import
from packstudio.material_derivation import family
from packstudio.versions import records,source_version
import json
results=[]
for packfile in sorted((ROOT/'reference'/'V3.2').glob('*.zip'))[:2]:
    layer=import_pack(packfile);tag_import(layer);seen=set()
    for path,raw in layer.files.items():
        if not path.endswith('.png'):continue
        kind=family(path)
        if kind is None or kind in seen:continue
        image=decode(raw)
        if image.width()*image.height()>512*512:continue
        version=source_version(layer,'1.8.9')
        target_path=next((p for p in sorted(records(version)) if p!=path and family(p)==kind),None)
        if target_path is None:continue
        target_raw=v.get(version,target_path);target_image=decode(target_raw)
        source_mask=part_mask(image,kind);target_mask=part_mask(target_image,kind)
        if not any(source_mask) or not any(target_mask):continue
        hist=histogram(image,source_mask);colour=anchor(target_image)
        started=time.perf_counter()
        output=generate_files(image,source_mask,[(target_path,target_raw,target_mask,colour,colour,False)],100,hist,None)
        result=decode(output[target_path]);expected=transfer(image,source_mask,target_image,target_mask,100,hist)
        assert result.convertToFormat(QImage.Format.Format_RGBA8888)==expected.convertToFormat(QImage.Format.Format_RGBA8888)
        results.append(dict(pack=packfile.name,path=path,family=kind,pixels=image.width()*image.height(),seconds=round(time.perf_counter()-started,4)))
        seen.add(kind)
        if len(seen)>=3:break
assert results
(ROOT/'analysis'/'v32-derivation-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS real material parity:',len(results),'samples; max processing seconds:',max(r['seconds'] for r in results))

from packstudio.part_derivation import rgba
probe=QImage(4,4,QImage.Format.Format_ARGB32);probe.fill(QColor(12,34,56,78))
for _ in range(200):assert rgba(probe)==bytes((12,34,56,78))*16
print('PASS RGBA buffer lifetime stability')
from unittest.mock import patch
from packstudio.material_derivation import open_dialog
from PySide6.QtWidgets import QDialog
disposed=[];created=NS(uid='new');calls=[];layers=[NS(uid='existing')]
w=NS(layers=layers,remember=lambda:calls.append('history'),changed=lambda:calls.append('changed'),refresh=lambda:None,
     switch_mode=lambda mode:None,browse_layer=lambda uid:calls.append(uid),statusBar=lambda:NS(showMessage=lambda message:None))
with patch('packstudio.material_derivation.DerivationDialog',return_value=NS(exec=lambda:QDialog.DialogCode.Accepted,output=created,deleteLater=lambda:disposed.append(1))):
    open_dialog(w,{})
assert layers[0] is created and len(layers)==2 and calls==['history','changed','new']
with patch('packstudio.material_derivation.DerivationDialog',return_value=NS(exec=lambda:QDialog.DialogCode.Rejected,output=None,deleteLater=lambda:disposed.append(1))):
    open_dialog(w,{})
assert len(layers)==2 and len(calls)==3 and len(disposed)==2
print('PASS composition insertion, history entry and canceled dialog isolation')
