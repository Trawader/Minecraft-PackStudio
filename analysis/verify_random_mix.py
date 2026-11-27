"""Five reproducible real-pack mixes through the internal export API; no windows."""
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

app=QApplication([]);vanilla=Vanilla();seed=20261104
destination=ROOT/'test'/('mix-results-'+time.strftime('%Y%m%d-%H%M%S'));destination.mkdir()
paths=sorted((ROOT/'test').glob('*.zip'));assert len(paths)==3
hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
packs=[import_pack(p) for p in paths]
for pack in packs:tag_import(pack)
targets=['1.7.10','1.12.2','1.16.5','1.21.11','26.3']
sheets=['assets/minecraft/textures/gui/icons.png','assets/minecraft/textures/particle/particles.png']
report={'seed':seed,'inputs':hashes,'source_versions':[p.source_version for p in packs],'runs':[]}

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
 started=time.time();rng=random.Random(seed+index);run={'target':target,'checks':[]};report['runs'].append(run)
 try:
  base_index=index%3;base=packs[base_index]
  # Choose independently editable regions, present in every requested version.
  chosen=[]
  for sheet in sheets:
   candidates=[r for r in RULES if r['source']==sheet and slot(r,'1.8.9') and all(slot(r,v) for v in targets)]
   rng.shuffle(candidates);selected=[]
   for rule in candidates:
    if any(overlap(slot(rule,'1.8.9')[1],slot(other,'1.8.9')[1]) for other in selected):continue
    selected.append(rule)
    if len(selected)==5:break
   assert len(selected)==5
   chosen+=selected
  layers=[];expected=[];manifest=[]
  for n,rule in enumerate(chosen):
   source_index=(n+index)%3;source=packs[source_index];path,box=slot(rule,'1.8.9')
   patch=crop(decode(source.files[path]),box);x,y,w,h,tw,th=box
   layer=Layer('part '+rule['target'],{'0':png(patch)},'component',path,[(x/tw,y/th,w/tw,h/th)],source_version='1.8.9')
   layers.append(layer);expected.append((rule,patch));manifest.append({'kind':'component','source':paths[source_index].name,'semantic_target':rule['target'],'source_box':box,'pixels':[patch.width(),patch.height()]})
  # A lower duplicate competes with the first component, not with other types.
  duplicate_source=packs[(index+1)%3];rule=chosen[0];path,box=slot(rule,'1.8.9');patch=crop(decode(duplicate_source.files[path]),box)
  layers.append(replace(layers[0],name='lower duplicate',files={'0':png(patch)}))
  manifest.append({'kind':'duplicate component below','source':duplicate_source.name,'semantic_target':rule['target']})
  # Whole atlas images below the parts deliberately compete with the base pack.
  for n,sheet in enumerate(sheets):
   source_index=(index+n+1)%3;owner=packs[source_index]
   layers.append(replace(owner,name='whole atlas '+sheet,files={sheet:owner.files[sheet]},kind='png'))
   manifest.append({'kind':'whole atlas','source':paths[source_index].name,'path':sheet})
  # Add random item/block PNGs with unambiguous destination paths.
  common=set.intersection(*(set(p.files) for p in packs))
  mapping=rename_map('1.8.9',target)
  candidates=sorted(p for p in common if p.endswith('.png') and any(t in p for t in ('/textures/blocks/','/textures/items/')))
  rng.shuffle(candidates);images=[]
  from packstudio.versions import records
  for path in candidates:
   dest=mapping.get(path,path)
   if dest not in records(target):continue
   source_index=rng.randrange(3);owner=packs[source_index]
   layers.append(replace(owner,name='image '+path,files={path:owner.files[path]},kind='png'))
   images.append((dest,owner.files[path]));manifest.append({'kind':'image','source':paths[source_index].name,'path':path,'target_path':dest})
   if len(images)==12:break
  assert len(images)==12
  layers.append(base);manifest.append({'kind':'base pack','source':paths[base_index].name})
  settings=defaults(layers)
  files=prepare_files(layers,vanilla,'1.8.9',settings,target,settings['title'],settings['body'],settings['cover'],'vanilla')
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
  conversion=json.loads(files.get('packstudio-conversion-report.json',b'[]'))
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
