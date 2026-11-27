"""Verify supported operations with all reference-directory reads prohibited."""
import os,sys,json,tempfile,hashlib
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from packstudio.core import Vanilla,Layer,decode,png,write_zip,import_pack
from packstudio.versions import VERSIONS,records,detect,FORMATS
from packstudio.builtin_assets import store
from packstudio.export_dialog import defaults,prepare_files
from packstudio.layouts import tag_import
from packstudio.semantics import particle_usage,translations
from packstudio.models import ModelLibrary
from packstudio.studio import StudioWindow
app=QApplication([])
archive,manifest=store();assert archive.testzip() is None
assert set(manifest)==set(VERSIONS)
objects={name.removeprefix('objects/') for name in archive.namelist() if name.startswith('objects/')}
assert objects=={key for version in manifest.values() for key in version.values()}
for key in objects:assert hashlib.sha256(archive.read('objects/'+key)).hexdigest()==key

original_open=Path.open;original_glob=Path.glob;original_rglob=Path.rglob
def guard(fn):
 def checked(path,*args,**kwargs):
  assert 'reference' not in path.parts,'Unexpected external reference read: '+str(path)
  return fn(path,*args,**kwargs)
 return checked
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='builtin-check-') as tmp,patch.object(Path,'open',guard(original_open)),patch.object(Path,'glob',guard(original_glob)),patch.object(Path,'rglob',guard(original_rglob)):
 os.environ['PACKSTUDIO_SETTINGS_FILE']=str(Path(tmp)/'settings.ini')
 v=Vanilla();assert v.root is None
 fallback=Vanilla(Path(tmp)/'missing-assets')
 for version in VERSIONS:
  assert set(records(version))<=v.paths(version)
  path=next(p for p in v.paths(version) if p.endswith('/stone.png') and '/textures/' in p)
  raw=v.get(version,path);assert raw and raw==fallback.get(version,path)
  assert version in detect({path:raw}) or len(detect({path:raw}))>1
 override=Path(tmp)/'external/1.8.9/minecraft/textures/blocks/stone.png';override.parent.mkdir(parents=True)
 override.write_bytes(b'override probe')
 external=Vanilla(Path(tmp)/'external');assert external.get('1.8.9','assets/minecraft/textures/blocks/stone.png')==b'override probe'
 assert external.get('1.8.9','assets/minecraft/textures/blocks/dirt.png')==v.get('1.8.9','assets/minecraft/textures/blocks/dirt.png')
 assert particle_usage('1.21.11') and translations()[1]
 icons='assets/minecraft/textures/gui/icons.png';particles='assets/minecraft/textures/particle/particles.png';inventory='assets/minecraft/textures/gui/container/inventory.png'
 files={p:v.get('1.8.9',p) for p in (icons,particles,inventory)}
 files['pack.mcmeta']=b'{"pack":{"pack_format":1,"description":"offline"}}'
 source=Layer('offline',files,source_version='1.8.9');tag_import(source)
 image=decode(files[icons]);image.fill(0)
 source.files[icons]=png(image)
 image=decode(files[particles]);image.fill(0);source.files[particles]=png(image)
 base=defaults([source])
 for version in VERSIONS:
  result=prepare_files([source],v,'1.8.9',base,version,'offline','',None,'vanilla')
  target=icons if icons in records(version) else 'assets/minecraft/textures/gui/sprites/hud/crosshair.png'
  assert target in result
  restored=decode(result[target]);assert any(restored.pixelColor(x,y).alpha() for y in range(restored.height()) for x in range(restored.width()))
  particle_target=particles if particles in records(version) else 'assets/minecraft/textures/particle/critical_hit.png'
  restored=decode(result[particle_target]);assert any(restored.pixelColor(x,y).alpha() for y in range(restored.height()) for x in range(restored.width()))
  assert inventory in result
  write_zip(Path(tmp)/(version+'.zip'),result)
  loaded=import_pack(Path(tmp)/(version+'.zip'));assert loaded.files==result
 library=ModelLibrary(v);assert 'Steve' in library.xml
 assert library.faces('xml:Steve','assets/minecraft/textures/entity/steve.png')
 w=StudioWindow(Path(tmp)/'library',drafts=False);w.defaults.setChecked(True);w.library_mode.setCurrentIndex(1);w.refresh()
 assert w.tree.topLevelItemCount() and w.vanilla.root is None
 w.dirty=False;w.close()
print(f'PASS all {len(VERSIONS)} versions: bundled hashes, no external reads, recognition, GUI/particles export, missing icons fill, model geometry, read-only library display')
