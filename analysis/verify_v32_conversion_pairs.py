"""Cross-version PNG/metadata pairing; no QApplication or source mutation."""
import sys,json,hashlib,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from packstudio.core import Layer,Vanilla
from packstudio.adaptation import export_composition
v=Vanilla();old='assets/minecraft/textures/blocks/diamond_ore.png';new='assets/minecraft/textures/block/diamond_ore.png'
metadata=b'{"animation":{"frametime":2,"interpolate":true}}'
rows=[]
for path,era,pack,target,expected,explicit in [
    (old,'1.12.2','1.20.1','1.20.1',new,False),
    (new,'1.20.1','1.12.2','1.12.2',old,False),
    (old,'1.12.2','1.20.1','1.20.6',new,True),
    (new,'1.20.1','1.20.1','1.20.1',new,False)]:
    files={path:v.get(era,path),path+'.mcmeta':metadata,'notes.txt':b'keep','packstudio-conversion-report.json':b'user file'}
    assert files[path]
    layer=Layer('fixture',dict(files),source_version=pack)
    if explicit:layer.asset_versions[path]=era
    out,report=export_composition([layer],v,target,'1.8.9')
    assert out[expected]==files[path] and out[expected+'.mcmeta']==metadata
    if path!=expected:assert path not in out and path+'.mcmeta' not in out
    assert layer.files==files and layer.source_version==pack
    assert out['notes.txt']==b'keep' and out['packstudio-conversion-report.json']==b'user file'
    rows.append(dict(pack_version=pack,texture_version=era,target=target,explicit=explicit,paired=True))
print('PASS 4 same-version / mixed upgrade / downgrade / explicit-version cases')
# Unknown sidecars without a corresponding PNG stay ordinary files.
missing='assets/example/textures/orphan.PNG.mcmeta';layer=Layer('unknown',{missing:metadata},source_version='1.12.2')
out,_=export_composition([layer],v,'1.20.1','1.8.9');assert out[missing]==metadata
print('PASS unknown sidecar preservation')
(ROOT/'analysis'/'v32-conversion-pair-results.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')

# Real animation bytes extracted read-only; simulate a mixed-era enclosing pack.
from packstudio.versions import records
real=[]
for packfile in sorted((ROOT/'reference'/'V3.2').glob('*.zip')):
    digest=hashlib.sha256(packfile.read_bytes()).digest()
    with zipfile.ZipFile(packfile) as z:
        names=set(z.namelist())
        for sidecar in sorted(n for n in names if n.endswith('.png.mcmeta')):
            path=sidecar[:-7]
            if path not in names:continue
            if path in records('1.12.2') and '/textures/blocks/' in path:
                source,target='1.12.2','1.20.1';expected=path.replace('/textures/blocks/','/textures/block/')
            elif path in records('1.20.1') and '/textures/block/' in path:
                source,target='1.20.1','1.12.2';expected=path.replace('/textures/block/','/textures/blocks/')
            else:continue
            if expected not in records(target):continue
            files={path:z.read(path),sidecar:z.read(sidecar)}
            layer=Layer('real animation fixture',dict(files),source_version=target,asset_versions={path:source})
            out,_=export_composition([layer],v,target,'1.8.9')
            assert out[expected]==files[path] and out[expected+'.mcmeta']==files[sidecar]
            assert layer.files==files
            real.append(dict(pack=packfile.name,path=path,target=target));break
    assert hashlib.sha256(packfile.read_bytes()).digest()==digest
assert real
(ROOT/'analysis'/'v32-conversion-real-pairs.json').write_text(json.dumps(real,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS real animation pairs:',len(real),'packs; source ZIPs unchanged')

# A source PNG omitted by compatibility policy must not leave its animation behind.
from packstudio.adaptation import adapt
texture='assets/minecraft/textures/misc/enchanted_item_glint.png'
raw=v.get('1.8.9',texture);assert raw
for pairs in ([(texture,raw),(texture+'.mcmeta',metadata)],[(texture+'.mcmeta',metadata),(texture,raw)]):
    out,notes=adapt(dict(pairs),'1.8.9','1.20.6',v)
    assert texture not in out and texture+'.mcmeta' not in out
    assert any(n['path']==texture+'.mcmeta' and n['action']=='omitted' for n in notes)
out,_=adapt({texture+'.mcmeta':metadata},'1.8.9','1.20.6',v)
assert out[texture+'.mcmeta']==metadata  # Existing orphan configuration is not silently removed.
print('PASS omitted texture pairing in both ZIP orders; original orphan retained')
