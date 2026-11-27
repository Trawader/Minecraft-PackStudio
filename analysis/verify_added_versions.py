"""Six supplied baselines: release boundaries, offline assets and actual exports."""
import os,sys,json,tempfile,hashlib
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
from packstudio.core import Vanilla,Layer,decode,png,write_zip,import_pack,save_project,load_project
from packstudio.versions import VERSIONS,FORMATS,records,detect
from packstudio.adaptation import adapt,RULES,slot
from packstudio.semantics import variant_id,identities
from packstudio.layouts import layout_catalog,tag_import
from packstudio.export_dialog import prepare_files,defaults
from packstudio.selector_taxonomy import creative_category
from packstudio.builtin_assets import paths
from packstudio.game_objects import entries
app=QApplication([]);vanilla=Vanilla()
added=('1.14.4','1.15.2','1.18.2','1.19.2','1.20.4','1.21.1')
assert len(VERSIONS)==17
assert [FORMATS[v] for v in added]==[4,5,8,9,22,34]
stone='assets/minecraft/textures/block/stone.png'
crosshair='assets/minecraft/textures/gui/sprites/hud/crosshair.png'
icons='assets/minecraft/textures/gui/icons.png'
rule=next(r for r in RULES if r['target']==crosshair)
chest='assets/minecraft/textures/entity/chest/normal.png'
dragon='assets/minecraft/textures/entity/enderdragon/dragon.png'
for path in (chest,dragon):
 assert variant_id(path,'1.14.4')==variant_id(path,'1.13.2')
 assert variant_id(path,'1.15.2')==variant_id(path,'1.16.5')
 assert variant_id(path,'1.14.4')!=variant_id(path,'1.15.2')
assert creative_category('item/oak_boat','',version='1.18.2')==('交通运输',)
assert creative_category('item/oak_boat','',version='1.20.4')!=('交通运输',)
assert set(detect({'pack.mcmeta':b'{"pack":{"pack_format":4}}'}))=={'1.13.2','1.14.4'}
assert 'assets/minecraft/textures/map/map_icons.png' in records('1.20.4')
assert 'assets/minecraft/textures/map/map_icons.png' not in records('1.21.1')
assert 'assets/minecraft/textures/models/armor/diamond_layer_1.png' in records('1.21.1')
assert 'assets/minecraft/textures/entity/equipment/humanoid/diamond.png' not in records('1.21.1')
report=[]
with tempfile.TemporaryDirectory() as temp:
 for version in added:
  catalog=records(version);assert catalog and set(catalog)<=paths(version)
  raw=vanilla.get(version,stone);assert hashlib.sha256(raw).hexdigest()==catalog[stone]['sha256']
  assert version in identities()[1][identities()[0][stone]]
  for path in (icons,'assets/minecraft/textures/gui/container/inventory.png'):
   if path in catalog:assert version in layout_catalog()[path]
  expected=icons if version in added[:4] else crosshair
  assert slot(rule,version)[0]==expected
  # A custom sprite (including an alpha=1 pixel) survives both atlas and sprite targets.
  image=decode(vanilla.get('1.20.6',crosshair));image.fill(QColor(12,99,210,255));image.setPixelColor(0,0,QColor(251,251,251,1))
  source=png(image);converted,notes=adapt({crosshair:source},'1.20.6',version,vanilla)
  back,_=adapt(converted,version,'1.20.6',vanilla)
  recovered=decode(back[crosshair]);assert recovered.pixelColor(0,0).alpha()==1
  assert recovered.pixelColor(1,1)==image.pixelColor(1,1)
  # Same-generation entities retained; incompatible 1.14/1.15 UV excluded with a report.
  out,notes=adapt({chest:vanilla.get(version,chest)},version,'1.14.4' if version=='1.14.4' else '1.16.5',vanilla)
  assert chest in out
  model='assets/minecraft/models/block/stone.json'
  custom='assets/example/textures/custom.png';config='assets/example/custom.json'
  files={stone:raw,custom:source,config:b'{"texture":"example:custom"}',
         'packstudio-conversion-report.json':b'user-owned',
         'pack.mcmeta':json.dumps({'pack':{'pack_format':FORMATS[version],'description':'test'}}).encode()}
  layer=Layer(version,files,source_version=version);tag_import(layer);before=dict(layer.files)
  rows=entries(layer,version)
  assert any(row['id']=='minecraft:block/stone' for row in rows)
  assert all(set(row['paths'])<=files.keys() for row in rows)
  assert all('elytra' not in row['id'] for row in rows)
  base=defaults([layer]);notes=[]
  result=prepare_files([layer],vanilla,version,base,version,base['title'],base['body'],None,'keep',notes)
  assert result[stone]==raw and result[custom]==source and result[config]==files[config]
  assert result['packstudio-conversion-report.json']==b'user-owned' and layer.files==before
  assert json.loads(result['pack.mcmeta'])['pack']['pack_format']==FORMATS[version]
  target=Path(temp)/(version+'.zip');write_zip(target,result);assert import_pack(target).files==result
  project=Path(temp)/(version+'.packstudio');save_project(project,[layer],version)
  layers,loaded=load_project(project);assert loaded==version and layers[0].files==before
  report.append({'version':version,'files':len(catalog),'format':FORMATS[version],'result':'PASS'})
  print(version,'PASS',flush=True)
 out,notes=adapt({chest:vanilla.get('1.14.4',chest)},'1.14.4','1.15.2',vanilla)
 assert chest not in out and any(n['action']=='omitted' for n in notes)
(ROOT/'analysis/added-version-results.json').write_text(json.dumps({'checks':report,'in_game_verified':False},ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS six added versions: boundaries, offline catalog, semantic availability, alpha-preserving GUI roundtrips, incompatible UV reporting, custom resources, source immutability, ZIP/project roundtrips')
