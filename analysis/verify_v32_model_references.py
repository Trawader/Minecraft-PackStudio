"""Model sprite-object reference checks using bundled models, without GUI."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from packstudio.core import Vanilla,Layer
from packstudio.resource_graph import ResourceGraph
from packstudio.export_integrity import reference_issues,protected_paths
from packstudio.adaptation import export_composition
v=Vanilla();counts={}
for version in ('26.2','26.3'):
    count=0
    for path in sorted(v.paths(version)):
        if '/models/' not in path or not path.endswith('.json'):continue
        raw=v.get(version,path);data=json.loads(raw);textures=data.get('textures',{})
        objects=[value for value in textures.values() if isinstance(value,dict)]
        if not objects:continue
        graph=ResourceGraph({path:raw}).parse()
        for value in objects:
            sprite=value.get('sprite')
            if not isinstance(sprite,str) or sprite.startswith('#'):continue
            target=graph.resource(path,sprite,'textures','.png')
            assert target in graph.edges[path],(version,path,sprite)
        assert not graph.issues,(version,path,graph.issues)
        count+=1
    counts[version]=count
assert all(counts.values())
print('PASS bundled sprite-object models:',counts)
model='assets/minecraft/models/block/stone.json';texture='assets/minecraft/textures/blocks/stone.png'
raw=json.dumps({'textures':{'all':{'sprite':'minecraft:blocks/stone','force_translucent':True},'particle':'#all'}}).encode()
files={model:raw,texture:v.get('1.12.2',texture),texture+'.mcmeta':b'{"animation":{}}',
       'assets/demo/models/custom.json':json.dumps({'parent':'minecraft:block/stone'}).encode()}
selected=protected_paths([Layer('protected',files,source_version='26.2')])
assert {model,texture,texture+'.mcmeta'}<=selected
out,_=export_composition([Layer('protected',files,source_version='26.2')],v,'1.20.1','1.8.9')
assert all(out[p]==files[p] for p in files)
print('PASS custom caller protects object-model texture and animation unchanged')
missing=json.dumps({'textures':{'all':{'sprite':'minecraft:block/missing_fixture'}}}).encode()
issues=reference_issues({model:missing},'26.2')
assert any('missing_fixture.png' in row['detail'] for row in issues)
existing=v.get('26.2','assets/minecraft/models/block/black_stained_glass.json')
assert not reference_issues({'assets/minecraft/models/block/black_stained_glass.json':existing},'26.2')
malformed=json.dumps({'textures':{'all':{'sprite':None}}}).encode()
assert ResourceGraph({model:malformed}).parse().issues
print('PASS missing reference, vanilla fallback, malformed sprite reporting')
(ROOT/'analysis'/'v32-model-reference-results.json').write_text(json.dumps({'bundled_models_checked':counts,'custom_chain':True,'missing_and_fallback':True},indent=2),encoding='utf-8')
