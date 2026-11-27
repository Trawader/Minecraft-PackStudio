"""Cached, local evidence for resource layouts; no network or source mutations."""
import hashlib
import json
import struct
from functools import lru_cache
from pathlib import Path

# Explicit release boundaries must not depend on positions in this list.
FORMATS={'1.7.10':1,'1.8.9':1,'1.9.4':2,'1.12.2':3,'1.13.2':4,
         '1.14.4':4,'1.15.2':5,'1.16.5':6,'1.18.2':8,'1.19.2':9,
         '1.20.1':15,'1.20.4':22,'1.20.6':32,'1.21.1':34,'1.21.11':75,'26.2':88,'26.3':97}
VERSIONS=tuple(FORMATS)

def version_key(version):return tuple(map(int,version.split('.')))
def before(version,boundary):return version_key(version)<version_key(boundary)

@lru_cache(maxsize=1)
def catalog():
    path=Path(__file__).parent/'data/version_catalog.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'versions':{},'rename_candidates':[]}

def records(version):
    return catalog()['versions'].get(version,{}).get('files',{})

def detect(files,hint=None):
    """Return candidates, never invent certainty for shared format 1 resources."""
    try:
        pack=json.loads(files.get('pack.mcmeta',b'{}')).get('pack',{})
        fmt=pack.get('min_format',pack.get('pack_format',hint))
        if isinstance(fmt,list):fmt=fmt[0]
    except (ValueError,AttributeError,IndexError):fmt=hint
    candidates=[v for v in VERSIONS if FORMATS[v]==fmt]
    if not candidates:candidates=list(VERSIONS)
    paths={p for p in files if p.startswith('assets/')}
    # Hash only relevant inputs once, not once per candidate.
    hashes={p:hashlib.sha256(files[p]).hexdigest() for p in paths}
    scores={v:(sum(records(v).get(p,{}).get('sha256')==h for p,h in hashes.items()),len(paths & records(v).keys())) for v in candidates}
    best=max(scores.values(),default=(0,0))
    return [v for v in candidates if scores[v]==best]

def source_version(layer,fallback='1.8.9'):
    explicit=getattr(layer,'source_version','')
    if explicit in VERSIONS:return explicit
    key=(len(layer.files),layer.format_hint,fallback)
    cached=getattr(layer,'_version_candidates',None)
    if cached and cached[0]==key:candidates=cached[1]
    else:
        candidates=detect(layer.files,layer.format_hint);layer._version_candidates=(key,candidates)
    return fallback if fallback in candidates else candidates[-1]

def metadata_format(pack,version):
    for key in ('supported_formats','min_format','max_format','pack_format'):pack.pop(key,None)
    if FORMATS[version]>=75:
        value=[FORMATS[version],1 if version=='26.3' else 0]
        pack.update(min_format=value,max_format=value)
    else:pack['pack_format']=FORMATS[version]

def asset_tags(files,version):
    """Tag out-of-era paths and incompatible entity atlas ratios inside mixed packs."""
    result={}
    for path,data in files.items():
        if not path.startswith('assets/'):continue
        candidates=[v for v in VERSIONS if path in records(v)]
        if '/textures/entity/' in path and data.startswith(b'\x89PNG\r\n\x1a\n') and len(data)>=24:
            w,h=struct.unpack('>II',data[16:24])
            candidates=[v for v in candidates if records(v)[path].get('size',[0,0])[0]*h==records(v)[path].get('size',[0,0])[1]*w]
        if candidates and version not in candidates:
            result[path]=min(candidates,key=lambda v:abs(VERSIONS.index(v)-VERSIONS.index(version)))
    return result
