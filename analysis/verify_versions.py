"""Offscreen version conversion regression using real vanilla layouts."""
import os,sys,json,tempfile
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
from packstudio.core import *
from packstudio.versions import records,source_version,FORMATS
from packstudio.adaptation import adapt,export_composition
from packstudio.models import ModelLibrary
from packstudio.export_dialog import prepare_files,defaults
app=QApplication([]);v=Vanilla()
old='assets/minecraft/textures/blocks/stone.png';new=old.replace('/blocks/','/block/')
raw=v.get('1.8.9',old)
out,report=adapt({old:raw},'1.8.9','1.21.11',v)
assert out[new]==raw and old not in out
back,_=adapt(out,'1.21.11','1.8.9',v);assert back[old]==raw
boat='assets/minecraft/textures/entity/boat.png'
out,notes=adapt({boat:v.get('1.8.9',boat)},'1.8.9','1.20.1',v)
assert boat not in out and notes[0]['action']=='omitted'
atlas='assets/minecraft/textures/particle/particles.png'
image=decode(v.get('1.8.9',atlas));image.fill(QColor('red'))
image.setPixelColor(0,0,QColor(0,0,0,0))
out,notes=adapt({atlas:png(image)},'1.8.9','1.20.6',v)
sprite='assets/minecraft/textures/particle/generic_0.png'
assert decode(out[sprite]).width()==8 and decode(out[sprite]).pixelColor(0,0).alpha()==0
out2,_=adapt({sprite:out[sprite]},'1.20.6','1.8.9',v)
restored=decode(out2[atlas]);assert restored.width()==128 and restored.pixelColor(1,1)==QColor('red')
assert restored.pixelColor(100,100)==decode(v.get('1.8.9',atlas)).pixelColor(100,100)
large,_=adapt({atlas:png(image)},'1.8.9','1.13.2',v)
assert decode(large[atlas]).width()==256 and decode(large[atlas]).pixelColor(1,1)==QColor('red')
bottom=Layer('bottom',{sprite:out[sprite]},source_version='1.20.6')
patch=decode(out[sprite]);patch.fill(0)
component=Layer('erase',{'0':png(patch)},kind='component',target=atlas,regions=[(0,0,8/128,8/128)],source_version='1.8.9')
composed,_=export_composition([component,bottom],v,'1.20.6','1.8.9')
assert decode(composed[sprite]).pixelColor(1,1).alpha()==0
assert bottom.files[sprite]==out[sprite]
sign='assets/minecraft/textures/entity/signs/oak.png'
sign_image=decode(v.get('1.21.11',sign))
for y in range(sign_image.height()):
    for x in range(sign_image.width()):sign_image.setPixelColor(x,y,QColor(x*3,y*5,80,255))
converted,_=adapt({sign:png(sign_image)},'1.21.11','26.2',v)
sign_new='assets/minecraft/textures/block/oak_sign.png'
assert decode(converted[sign_new]).pixelColor(0,0)==sign_image.pixelColor(2,0)
back,_=adapt({sign_new:converted[sign_new]},'26.2','1.21.11',v)
assert decode(back[sign]).pixelColor(2,0)==sign_image.pixelColor(2,0)
assert decode(back[sign]).pixelColor(26,0)==sign_image.pixelColor(26,0)
from packstudio.versions import asset_tags
assert asset_tags({boat:v.get('1.8.9',boat)},'1.21.11')[boat]=='1.8.9'
invalid_mix=Layer('mixed boat', {boat:v.get('1.8.9',boat)},source_version='1.21.11')
converted,notes=export_composition([invalid_mix],v,'1.21.11','1.8.9');assert boat not in converted
mixed=Layer('mixed',{old:raw,sprite:out[sprite]},asset_versions={old:'1.8.9',sprite:'1.20.6'})
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as tmp:
    path=Path(tmp)/'project.packstudio';save_project(path,[mixed],'26.3')
    layers,version=load_project(path);assert version=='26.3' and layers[0].asset_versions==mixed.asset_versions
library=ModelLibrary(v)
for version in VERSIONS:
    library.update({},version)
    texture=old if VERSIONS.index(version)<4 else new
    key=library.identify(texture);assert key and library.faces(key,texture),(version,key)
    for model_key in library.entries:
        if not model_key.startswith('xml:'):
            assert library.faces(model_key,texture),(version,model_key)
    layer=Layer(version,{texture:v.get(version,texture)},source_version=version)
    exported=prepare_files([layer],v,'1.8.9',defaults([layer]),version,'Test','',None)
    metadata=json.loads(exported['pack.mcmeta'])['pack']
    assert 'min_format' in metadata if FORMATS[version]>=75 else 'pack_format' in metadata
    print(version,len(library.entries),'models',flush=True)
library.update({},'1.21.11');assert library.from_id('minecraft:mace')
library.update({},'1.8.9');assert library.identify(boat)=='xml:Boat (Legacy)'
print(f'PASS: {len(VERSIONS)} versions, IDs, rename roundtrip, incompatible boat, alpha, default fill, mixed tags, component erasure and persistence')
