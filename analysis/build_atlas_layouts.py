"""Build reproducible atlas signatures and semantic availability from local vanilla."""
import sys,os,json,hashlib
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from packstudio.core import Vanilla,decode
from packstudio.versions import VERSIONS,records
from packstudio import layouts
from packstudio.adaptation import RULES_BY_SOURCE,slot,crop
# Ignore a previous generated catalogue while rebuilding it.
layouts.layout_catalog=lambda:{}
vanilla=Vanilla();result={}
for path,rules in RULES_BY_SOURCE.items():
    for version in VERSIONS:
        if path not in records(version):continue
        raw=vanilla.get(version,path);image=decode(raw);available=[];signature=[]
        for rule in rules:
            found=slot(rule,version)
            if not found or found[0]!=path:continue
            pixels=crop(image,found[1]).convertToFormat(image.Format.Format_RGBA8888)
            if rule['family'] in ('gui','particle','effect','map') and not any(bytes(pixels.constBits())[3::4]):continue
            available.append(rule['target']);signature.append((rule['target'],found[1],rule.get('ops',[])))
        # Container/creative positions changed even where overlay sprite lists coincide.
        if path.endswith(('/container/inventory.png','/creative_inventory/tabs.png')):signature.append(('legacy-container',version in VERSIONS[:2]))
        rgb,alpha=layouts.fingerprints(image,(image.width(),image.height()))
        result.setdefault(path,{})[version]=dict(size=[image.width(),image.height()],sha256=hashlib.sha256(raw).hexdigest(),pixels=rgb,alpha=alpha,
            layout=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest(),available=sorted(set(available)))
(ROOT/'packstudio/data/atlas_layouts.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
print(len(result),'atlas paths;',sum(len(v) for v in result.values()),'version signatures')
