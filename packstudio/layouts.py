"""Per-image layout evidence, independent of the enclosing pack declaration."""
import hashlib,json
from functools import lru_cache
from pathlib import Path
from .versions import VERSIONS,source_version

@lru_cache(maxsize=1)
def layout_catalog():
    path=Path(__file__).parent/'data/atlas_layouts.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}

def digest(data):return hashlib.sha256(data).hexdigest()

def fingerprints(image,size):
    from PySide6.QtGui import QImage
    normalized=image.scaled(*size).convertToFormat(QImage.Format.Format_RGBA8888)
    pixels=bytes(normalized.constBits())
    # Ignore RGB beneath alpha=0, which PNG editors may change without a visual edit.
    visible=bytearray(pixels)
    for i in range(0,len(visible),4):
        if visible[i+3]==0:visible[i:i+3]=b'\0\0\0'
    return digest(visible),digest(pixels[3::4])

def inspect_atlases(layer,fallback='1.8.9'):
    from .core import decode
    rows=[];source=source_version(layer,fallback)
    for path,data in layer.files.items():
        entries=layout_catalog().get(path)
        if not entries:continue
        groups={}
        for version,entry in entries.items():groups.setdefault(entry['layout'],[]).append(version)
        candidates=[{'versions':versions,'version':versions[0]} for versions in groups.values()]
        checksum=digest(data);confirmation=layer.layout_confirmations.get(path,{})
        chosen=None;reason='需要确认自定义图集布局 / Custom layout needs confirmation'
        exact=[v for v,e in entries.items() if e['sha256']==checksum]
        def nearest(versions):return min(versions,key=lambda v:abs(VERSIONS.index(v)-VERSIONS.index(source)))
        if confirmation.get('version') in entries and (confirmation.get('stable') or confirmation.get('sha256')==checksum):
            chosen=confirmation['version'];reason='已标记布局版本 / Tagged layout version'
        elif exact:chosen=nearest(exact);reason='原版文件哈希匹配 / Exact vanilla file'
        elif len(groups)==1:chosen=candidates[0]['version'];reason='已知版本共用布局 / Shared layout'
        else:
            image=decode(data);computed={};matches={'pixels':[],'alpha':[]}
            for version,entry in entries.items():
                w,h=entry['size']
                if image.width()*h!=image.height()*w:continue
                if (w,h) not in computed:computed[w,h]=fingerprints(image,(w,h))
                rgb,alpha=computed[w,h]
                if rgb==entry['pixels']:matches['pixels'].append(version)
                if alpha==entry['alpha']:matches['alpha'].append(version)
            for mode in ('pixels','alpha'):
                values=matches[mode]
                if values and len({entries[v]['layout'] for v in values})==1:
                    chosen=nearest(values);reason='图像像素匹配 / Pixel match' if mode=='pixels' else '透明轮廓匹配 / Alpha layout match';break
        rows.append(dict(path=path,sha256=checksum,chosen=chosen,reason=reason,candidates=candidates,pack_version=source,uid=layer.uid))
    return rows

def confirm_layout(layer,path,version):
    if version not in layout_catalog().get(path,{}):raise ValueError('Unknown atlas layout')
    layer.layout_confirmations[path]={'version':version,'sha256':digest(layer.files[path]),'stable':True}
    layer.asset_versions[path]=version

def tag_import(layer,fallback='1.8.9'):
    """Assign the recognised/declared layout once; edits retain that layout label."""
    from .versions import detect
    candidates=detect(layer.files,layer.format_hint)
    known=layer.source_version in VERSIONS or len(candidates)<len(VERSIONS)
    version=source_version(layer,fallback)
    layer.source_version=version if known else ''
    for row in inspect_atlases(layer,fallback):
        chosen=row['chosen'] or layer.asset_versions.get(row['path'],version if known else '')
        if chosen in layout_catalog().get(row['path'],{}):confirm_layout(layer,row['path'],chosen)

class LayoutReviewRequired(ValueError):
    pass

def checked_layouts(layer,fallback):
    rows=inspect_atlases(layer,fallback)
    pending=[r['path'] for r in rows if not r['chosen']]
    if pending:raise LayoutReviewRequired('请先确认图集布局 / Confirm atlas layouts first:\n'+'\n'.join(pending))
    return {r['path']:r['chosen'] for r in rows},rows
