"""Mixed-version ordering and explicit atlas fallback policies, no GUI."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtGui import QImage,QColor
from packstudio.core import Layer,Vanilla,decode,png
from packstudio.adaptation import export_composition,slot,RULES,crop
from packstudio.layouts import confirm_layout
v=Vanilla();old='assets/minecraft/textures/blocks/stone.png';new='assets/minecraft/textures/block/stone.png'
def solid(color):
    im=QImage(16,16,QImage.Format.Format_ARGB32);im.fill(QColor(color));return png(im)
rows=[]
for target in ('1.12.2','1.20.6','26.3'):
    for order in (False,True):
        for policy in ('keep','vanilla','lower'):
            a=Layer('legacy',{old:solid('red')},source_version='1.12.2');b=Layer('modern',{new:solid('blue')},source_version='1.20.6')
            layers=[a,b] if order else [b,a];before=[dict(l.files) for l in layers]
            out,notes=export_composition(layers,v,target,'1.8.9',policy)
            expected=old if target=='1.12.2' else new
            assert out[expected]==next(iter(layers[0].files.values()))
            assert all(l.files==raw for l,raw in zip(layers,before))
            layers[0].enabled=False
            out,_=export_composition(layers,v,target,'1.8.9',policy)
            assert out[expected]==next(iter(layers[1].files.values()))
            rows.append(dict(target=target,legacy_on_top=order,policy=policy,passed=True))
# A fully transparent upper GUI sprite may be intentional. Test all choices.
rule=next(r for r in RULES if r['source'].endswith('/gui/icons.png') and slot(r,'1.8.9') and slot(r,'1.20.6') and slot(r,'1.20.6')[1]==[0,0,1,1,1,1])
sheet=rule['source'];target_path,_=slot(rule,'1.20.6')
im=decode(v.get('1.8.9',sheet));im.fill(0)
upper=Layer('transparent atlas',{sheet:png(im)},source_version='1.8.9');confirm_layout(upper,sheet,'1.8.9')
lower=Layer('lower sprite',{target_path:solid('blue')},source_version='1.20.6')
for policy in ('keep','lower','vanilla'):
    out,_=export_composition([upper,lower],v,'1.20.6','1.8.9',policy)
    result=decode(out[target_path])
    if policy=='keep':assert all(result.pixelColor(x,y).alpha()==0 for y in range(result.height()) for x in range(result.width()))
    if policy=='lower':assert result==decode(lower.files[target_path])
    if policy=='vanilla':assert result==decode(v.get('1.20.6',target_path))
print('PASS 18 mixed-order cases, disabled layers, three explicit atlas policies')
(ROOT/'analysis'/'v32-mixed-order-results.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')

from packstudio.core import import_pack
from packstudio.layouts import tag_import
from packstudio.export_integrity import reference_issues
from collections import Counter
import hashlib
paths=sorted((ROOT/'reference'/'V3.2').glob('*.zip'))[:2]
digests=[hashlib.sha256(p.read_bytes()).digest() for p in paths]
layers=[import_pack(p) for p in paths]
for layer in layers:tag_import(layer)
before=[dict(l.files) for l in layers];real=[]
for target in ('1.12.2','1.20.6'):
    for ordered in (layers,list(reversed(layers))):
        top,top_notes=export_composition([ordered[0]],v,target,'1.8.9','keep')
        result,notes=export_composition(ordered,v,target,'1.8.9','keep')
        checked=0
        for path,raw in top.items():
            if any(folder in path for folder in ('/textures/block/','/textures/blocks/','/textures/item/','/textures/items/')):
                assert result.get(path)==raw,(target,path)
                checked+=1
        issues=reference_issues(result,target)
        real.append(dict(target=target,top=ordered[0].name,checked_textures=checked,
            actions=dict(Counter(n['action'] for n in notes)),
            omission_reasons=dict(Counter(n['detail'] for n in notes if n['action']=='omitted')),
            reference_issues=issues))
        print('PASS real mixed order',target,checked,flush=True)
assert all(layer.files==raw for layer,raw in zip(layers,before))
assert all(hashlib.sha256(p.read_bytes()).digest()==digest for p,digest in zip(paths,digests))
(ROOT/'analysis'/'v32-real-mixed-results.json').write_text(json.dumps(real,ensure_ascii=False,indent=2),encoding='utf-8')
