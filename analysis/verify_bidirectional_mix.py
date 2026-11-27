"""Ten bidirectional real-pack mixes through the internal export API; no windows."""
import os,sys,json,random,hashlib,time,zipfile
from collections import Counter
from dataclasses import replace
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
from packstudio.core import Layer,Vanilla,import_pack,decode,png,write_zip
from packstudio.layouts import tag_import
from packstudio.adaptation import RULES,slot,crop,rename_map
from packstudio.export_dialog import defaults,prepare_files
from packstudio.versions import FORMATS

app=QApplication([]);vanilla=Vanilla();seed=2026110410
destination=ROOT/'test'/('bidirectional-results-'+time.strftime('%Y%m%d-%H%M%S'));destination.mkdir()
paths=sorted((ROOT/'test').glob('*.zip'));assert len(paths)==5
hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
packs=[import_pack(p) for p in paths]
for pack in packs:tag_import(pack)
# Both added ZIPs declare 1.20.1. Create an explicit modern-layout source
# for downgrade coverage; do not mislabel either original as native 1.21.11.
modern_source=next(p for p in packs if 'MCDark' in p.name)
base=defaults([modern_source])
converted=prepare_files([modern_source],vanilla,'1.20.1',base,'1.21.11',base['title'],base['body'],base['cover'],'keep')
write_zip(destination/'derived-source-1.21.11.zip',converted)
derived=Layer('Derived 1.21.11 from '+modern_source.name,converted,source_version='1.21.11');tag_import(derived)
packs.append(derived)
targets=['1.7.10','1.8.9','1.9.4','1.12.2','1.13.2','1.16.5','1.20.1','1.20.6','1.21.11','26.3']
if os.environ.get('MIX_TARGETS'):targets=os.environ['MIX_TARGETS'].split(',')
sheets=['assets/minecraft/textures/gui/icons.png','assets/minecraft/textures/particle/particles.png']
report={'seed':seed,'inputs':hashes,'sources':[{'name':p.name,'version':p.source_version,'derived':p is derived} for p in packs],'runs':[]}

def equal_pixels(a,b):
 if a.size()!=b.size():return False
 # Keep QImage owners alive while reading constBits. Compare premultiplied
 # colour: transparent RGB is irrelevant and Qt alpha arithmetic may round by
 # one visible channel level. Alpha must still match exactly, including erasure.
 image_a=a.convertToFormat(QImage.Format.Format_RGBA8888)
 image_b=b.convertToFormat(QImage.Format.Format_RGBA8888)
 a=bytes(image_a.constBits());b=bytes(image_b.constBits())
 return all(a[i+3]==b[i+3] and all(abs(a[i+j]*a[i+3]-b[i+j]*b[i+3])<=255 for j in range(3)) for i in range(0,len(a),4))

def overlap(a,b):
 x,y,w,h,tw,th=a;X,Y,W,H,TW,TH=b
 return max(x/tw,X/TW)<min((x+w)/tw,(X+W)/TW) and max(y/th,Y/TH)<min((y+h)/th,(Y+H)/TH)

for index,target in enumerate(targets):
 if os.environ.get('MIX_CASES') and str(index+1) not in os.environ['MIX_CASES'].split(','):continue
 if os.environ.get('MIX_TARGET'):target=os.environ['MIX_TARGET']
 started=time.time();rng=random.Random(seed+index);run={'target':target,'checks':[]};report['runs'].append(run)
 try:
  high=[i for i,p in enumerate(packs) if p.source_version=='1.20.1']
  low=[i for i,p in enumerate(packs) if p.source_version=='1.8.9']
  base_index=([high[0],len(packs)-1,high[1],high[0],high[1],len(packs)-1,low[0],low[1],low[2],low[0]])[index]
  base=packs[base_index];run['base_version']=base.source_version;run['base_name']=base.name
  layers=[];expected=[];manifest=[];used=[]
  # Two parts per uploaded pack plus two from the derived modern-layout pack.
  for n in range(12):
   source_index=(n+index)%len(packs);source=packs[source_index];version=source.source_version
   sheet=sheets[n//6]
   candidates=[r for r in RULES if r['source']==sheet and slot(r,version) and slot(r,target) and slot(r,version)[0] in source.files and not r.get('ops')]
   rng.shuffle(candidates)
   candidates=[r for r in candidates if not any(slot(r,target)[0]==slot(other,target)[0] and overlap(slot(r,target)[1],slot(other,target)[1]) for other in used)]
   assert candidates,('no component candidates',source.name,sheet,target)
   rule=candidates[0];used.append(rule);path,box=slot(rule,version)
   patch=crop(decode(source.files[path]),box);x,y,w,h,tw,th=box
   layer=Layer('part '+rule['target'],{'0':png(patch)},'component',path,[(x/tw,y/th,w/tw,h/th)],source_version=version)
   layers.append(layer);expected.append((rule,patch));manifest.append({'kind':'component','source':source.name,'source_version':version,'semantic_target':rule['target'],'source_box':box,'pixels':[patch.width(),patch.height()]})
  # A lower copy of the same semantic part, sourced from another pack/layout.
  rule=used[0]
  for owner in packs:
   match=slot(rule,owner.source_version)
   if match and match[0] in owner.files:
    path,box=match;x,y,w,h,tw,th=box;patch=crop(decode(owner.files[path]),box)
    layers.append(Layer('lower duplicate',{'0':png(patch)},'component',path,[(x/tw,y/th,w/tw,h/th)],source_version=owner.source_version))
    manifest.append({'kind':'duplicate component below','source':owner.name,'semantic_target':rule['target']});break
  for n,sheet in enumerate(sheets):
   owner=packs[low[(index+n)%len(low)]]
   layers.append(replace(owner,name='whole atlas '+sheet,files={sheet:owner.files[sheet]},kind='png'))
   manifest.append({'kind':'whole atlas','source':owner.name,'path':sheet})
  images=[];destinations=set()
  from packstudio.versions import records
  for n in range(12):
   owner=packs[(n+index)%len(packs)];mapping=rename_map(owner.source_version,target)
   candidates=sorted(p for p in owner.files if p.endswith('.png') and any(t in p for t in ('/textures/blocks/','/textures/items/','/textures/block/','/textures/item/')))
   rng.shuffle(candidates)
   for path in candidates:
    dest=mapping.get(path,path)
    if dest not in records(target) or dest in destinations:continue
    layers.append(replace(owner,name='image '+path,files={path:owner.files[path]},kind='png'))
    images.append((dest,owner.files[path]));destinations.add(dest);manifest.append({'kind':'image','source':owner.name,'source_version':owner.source_version,'path':path,'target_path':dest});break
   else:raise AssertionError(('no PNG candidate',owner.name,target))
  layers.append(base);manifest.append({'kind':'base pack','source':base.name,'version':base.source_version})
  settings=defaults(layers)
  run['layers_top_to_bottom']=manifest
  conversion=[]
  files=prepare_files(layers,vanilla,'1.8.9',settings,target,settings['title'],settings['body'],settings['cover'],'keep',conversion)
  output=destination/f'mix-{index+1}-{target}.zip';write_zip(output,files)
  run['zip']=output.name;run['layers_top_to_bottom']=manifest
  for rule,patch in expected:
   path,box=slot(rule,target);assert path in files,path
   actual=crop(decode(files[path]),box)
   assert actual.width()>=patch.width() and actual.height()>=patch.height(),('downsampled',rule['target'])
   assert equal_pixels(actual,patch.scaled(actual.size())),('component overwritten',rule['target'])
   run['checks'].append({'kind':'component pixel match','id':rule['target'],'output':path,'size':[actual.width(),actual.height()]})
  for path,raw in images:
   assert path in files and equal_pixels(decode(files[path]),decode(raw)),('PNG priority',path)
  run['checks'].append({'kind':'independent PNG pixel matches','count':len(images)})
  meta=json.loads(files['pack.mcmeta'])['pack'];fmt=meta.get('min_format',meta.get('pack_format'));fmt=fmt[0] if isinstance(fmt,list) else fmt
  assert fmt==FORMATS[target]
  with zipfile.ZipFile(output) as archive:
   assert archive.testzip() is None
   assert len(archive.namelist())==len(set(archive.namelist()))
  png_count=0
  for path,raw in files.items():
   if path.endswith('.png'):decode(raw);png_count+=1
  run.update(status='PASS',files=len(files),png_decoded=png_count,conversion_actions=dict(Counter(r['action'] for r in conversion)),seconds=round(time.time()-started,2))
 except Exception as error:
  import traceback
  run.update(status='FAIL',error=str(error),traceback=traceback.format_exc());print(run['traceback'],flush=True)
 (destination/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
 print(target,run['status'],run.get('seconds'),flush=True)
assert all(hashlib.sha256(p.read_bytes()).hexdigest()==hashes[p.name] for p in paths)
report['original_zip_hashes_unchanged']=True
(destination/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
print(str(destination),flush=True)
assert all(r['status']=='PASS' for r in report['runs'])
