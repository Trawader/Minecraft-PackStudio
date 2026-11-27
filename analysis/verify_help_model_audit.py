"""Java default namespaces, cross-version references and model index reuse."""
import sys,json
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from packstudio.resource_graph import ResourceGraph
from packstudio.models import ModelLibrary
from packstudio.adaptation import adapt
from packstudio.core import Vanilla

def raw(value):return json.dumps(value).encode()
model='assets/demo/models/item/example.json'
files={model:raw({'parent':'item/handheld','textures':{'layer0':'items/diamond_sword','extra':'demo:item/custom'}})}
graph=ResourceGraph(files).parse()
assert graph.edges[model]=={'assets/minecraft/models/item/handheld.json','assets/minecraft/textures/items/diamond_sword.png','assets/demo/textures/item/custom.png'}
out,_=adapt(files,'1.8.9','1.20.1',Vanilla());converted=json.loads(out[model])
assert converted['parent']=='minecraft:item/handheld'
assert converted['textures']=={'layer0':'minecraft:item/diamond_sword','extra':'demo:item/custom'}
back,_=adapt(out,'1.20.1','1.8.9',Vanilla())
assert json.loads(back[model])['textures']['layer0']=='minecraft:items/diamond_sword'
assert 'assets/minecraft/models/item/handheld.json' in back
# Extension-relative references retain their own path rules.
props='assets/demo/optifine/cit/example.properties'
assert graph.local(props,'./custom','texture')=='assets/demo/optifine/cit/custom.png'
assert graph.resource(props,'item/custom','textures','.png')=='assets/demo/textures/item/custom.png'

base={'assets/minecraft/models/item/handheld.json':raw({'parent':'builtin/generated'})}
vanilla=SimpleNamespace(paths=lambda version:set(base),get=lambda version,path:base.get(path))
library=ModelLibrary(vanilla);library.update(files,'1.20.1')
resolved=library.resolve(model)
assert library.texture('#layer0',resolved)=='assets/minecraft/textures/items/diamond_sword.png'
assert library.texture('#extra',resolved)=='assets/demo/textures/item/custom.png'
cache=library.cache;entries=library.entries
png='assets/minecraft/textures/items/diamond_sword.png';armor='assets/minecraft/textures/models/armor/iron_layer_1.png'
for index in range(10):
    edited={**files,png:bytes([index]),armor:bytes([index])};library.update(edited)
    assert library.cache is cache and library.entries is entries
    assert library.files[png]==bytes([index])
changed={**files,model:raw({'parent':'item/handheld','textures':{'layer0':'demo:item/changed'}})}
library.update(changed);assert library.cache is not cache
assert library.texture('#layer0',library.resolve(model))=='assets/demo/textures/item/changed.png'
print('PASS default/explicit namespace, forward/reverse conversion, extension-relative paths, preview resolution; 10 PNG edits reuse model index and JSON edit invalidates it.')
