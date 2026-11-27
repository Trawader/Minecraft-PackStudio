"""Pure adaptation for explicit pack conversion and export; inputs stay unchanged."""
import json
from functools import lru_cache
from pathlib import Path
from PySide6.QtCore import QRect
from PySide6.QtGui import QPainter,QColor,QTransform
from .core import decode,png,compose
from .versions import before,VERSIONS,records,catalog,source_version

RULES=json.loads((Path(__file__).parent/'data/slice_rules.json').read_text(encoding='utf-8'))
RULES_BY_SOURCE={}
for rule in RULES:RULES_BY_SOURCE.setdefault(rule['source'],[]).append(rule)

def slot(rule,version):
    entries=records(version);sheet=rule['source'];sprite=rule['target']
    if sheet in entries:
        name=Path(sprite).stem
        if rule['family']=='effect':
            if before(version,'1.9') and name in ('glowing','levitation','luck','unluck','slow_falling','conduit_power','dolphins_grace'):return None
            if before(version,'1.13') and name in ('slow_falling','conduit_power','dolphins_grace'):return None
        if rule['family']=='map':
            index=rule['box'][1]//8*16+rule['box'][0]//8
            if before(version,'1.9') and index>6:return None
            if before(version,'1.12') and index>7:return None
            if version=='1.12.2' and index>9:return None
        box=list(rule['box'])
        if rule['family']=='particle' and before(version,'1.13'):
            box[4:]=[128,128]
            if box[0]+box[2]>128 or box[1]+box[3]>128:return None
        if before(version,'1.9') and rule['family']=='gui':
            if any(x in sprite for x in ('offhand','attack_indicator','jump_bar_cooldown','effect_background')):return None
            if 'creative_inventory/tabs.png' in sheet:return None
        if rule['family']=='gui' and 'jump_bar_cooldown' in sprite and before(version,'1.20'):return None
        from .layouts import layout_catalog
        layout=layout_catalog().get(sheet,{}).get(version)
        if layout and rule['family'] in ('gui','particle','effect','map') and sprite not in layout['available']:return None
        return sheet,box
    if sprite in entries:return sprite,rule.get('target_box',[0,0,1,1,1,1])
    return None

def crop(image,box):
    x,y,w,h,tw,th=box
    left,top=round(x*image.width()/tw),round(y*image.height()/th)
    return image.copy(left,top,round((x+w)*image.width()/tw)-left,round((y+h)*image.height()/th)-top)

def paint(base,patch,box):
    x,y,w,h,tw,th=box
    from .core import preserve_resolution
    resized=preserve_resolution(base,patch,(x/tw,y/th,w/tw,h/th))
    if resized is not base:base.swap(resized)
    left,top=round(x*base.width()/tw),round(y*base.height()/th)
    rect=QRect(left,top,round((x+w)*base.width()/tw)-left,round((y+h)*base.height()/th)-top)
    painter=QPainter(base);painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    painter.drawImage(rect,patch);painter.end()

@lru_cache(maxsize=121)
def rename_map(source,target):
    old=before(source,'1.13');new=before(target,'1.13')
    mapping={r['source']:r['target'] for r in catalog()['rename_candidates']}
    # Identical stems across the flattening boundary are explicit path evidence.
    a,b=records('1.12.2'),records('1.13.2')
    for path in a:
        renamed=path.replace('/textures/blocks/','/textures/block/').replace('/textures/items/','/textures/item/')
        if renamed!=path and renamed in b:mapping.setdefault(path,renamed)
    graph={}
    edges=json.loads((Path(__file__).parent/'data/texture_aliases.json').read_text(encoding='utf-8'))
    for a,b in list(mapping.items())+[(e['source'],e['target']) for e in edges]:
        graph.setdefault(a,set()).add(b);graph.setdefault(b,set()).add(a)
    result={};dest=records(target)
    for path in records(source):
        if path in dest or path not in graph:continue
        seen=set();todo=[path]
        while todo:
            current=todo.pop()
            if current in seen:continue
            seen.add(current);todo.extend(graph.get(current,())-seen if current in graph else ())
        matches=seen & dest.keys()
        if len(matches)==1:result[path]=matches.pop()
    return result

def adapt(files,source,target,vanilla,below=None):
    if source==target:return dict(files),[]
    out={};report=[];consumed=set();blocked=set();omitted=set();dest=records(target);src=records(source);below=below or {}
    def note(path,action,detail):
        report.append(dict(path=path,action=action,detail=detail,source=source,target=target))
        if action=='omitted':omitted.add(path)
    # Convert semantic sprites, including atlas-to-atlas size/layout differences.
    images={}
    for rule in RULES:
        a,b=slot(rule,source),slot(rule,target)
        rebuild=a and a[0].endswith(('/gui/icons.png','/gui/widgets.png'))
        if not a or not b or (a==b and not rebuild) or a[0] not in files:continue
        source_path,source_box=a;target_path,target_box=b
        if source_path in blocked:continue
        im=images.setdefault(source_path,decode(files[source_path])) if source_path not in images else images[source_path]
        expected=src.get(source_path,{}).get('size')
        if expected and im.width()*expected[1]!=im.height()*expected[0]:
            blocked.add(source_path);consumed.add(source_path);note(source_path,'omitted','Atlas aspect ratio differs; animated/custom layout needs an explicit rule');continue
        patch=crop(im,source_box)
        operations=rule.get('ops',[])
        forward=source_path==rule['source']
        for op in operations if forward else reversed(operations):
            if op=='mirrorVertically':patch=patch.mirrored(False,True)
            elif op=='mirrorHorizontally':patch=patch.mirrored(True,False)
            elif op.startswith('rotate'):patch=patch.transformed(QTransform().rotate(int(op[6:])*(1 if forward else -1)))
        if target_box==[0,0,1,1,1,1]:out[target_path]=png(patch)
        else:
            data=out.get(target_path) or below.get(target_path) or vanilla.get(target,target_path)
            if data is None:continue
            base=decode(data)
            # paint checks the pixel budget BEFORE allocating a larger atlas.
            # Do not bypass it with a potentially huge intermediate scaled image.
            try:paint(base,patch,target_box)
            except ValueError as error:
                raise ValueError(f'{source} → {target}: {source_path} → {target_path}: {error}') from error
            out[target_path]=png(base)
        consumed.add(source_path)
        note(source_path,'relocated',target_path)
    inventory='assets/minecraft/textures/gui/container/inventory.png'
    # Inventory retains its path but the crafting area moved in 1.9.
    if inventory in files and inventory not in blocked and ((before(source,'1.9'))!=(before(target,'1.9'))):
        base=decode(below.get(inventory) or vanilla.get(target,inventory));im=decode(files[inventory])
        if im.width()>base.width():base=base.scaled(im.width(),im.width())
        old=before(source,'1.9')
        moves=[([0,0,176,166,256,256],[0,0,176,166,256,256])]
        # Copy shared inventory/player areas only; target defaults supply the new offhand.
        moves=[([0,0,76,166,256,256],[0,0,76,166,256,256]),([0,83,176,83,256,256],[0,83,176,83,256,256]),
               ([87,25,36,36,256,256],[97,17,36,36,256,256]),([141,34,23,23,256,256],[151,26,23,23,256,256])]
        for a,b in moves:
            if not old:a,b=b,a
            paint(base,crop(im,a),b)
        out[inventory]=png(base);consumed.add(inventory);note(inventory,'relocated','crafting/offhand; target vanilla fills missing regions')
    mapping=rename_map(source,target)
    for path in consumed:
        if path not in blocked and path in dest and path not in out and src.get(path,{}).get('size')==dest[path].get('size'):
            out[path]=files[path]
    # Resolve images before their sidecars, regardless of ZIP entry order.
    for path,data in sorted(files.items(),key=lambda item:item[0].lower().endswith('.png.mcmeta')):
        if path in consumed:continue
        renamed=mapping.get(path,path)
        if path.lower().endswith('.png.mcmeta'):
            texture=path[:-7]
            if texture in omitted:
                note(path,'omitted','Paired texture was omitted during conversion');continue
            if texture in consumed:
                note(path,'omitted','Atlas animation metadata requires per-sprite adaptation');continue
            if texture in mapping:renamed=mapping[texture]+'.mcmeta'
        if path=='pack.mcmeta':continue
        known=path in src or any(path in records(v) for v in VERSIONS)
        if path.startswith('assets/') and not known and path.endswith(('.png','.json')):
            note(path,'unresolved','Custom resource preserved; target compatibility is not verified')
        if path.startswith('assets/minecraft/') and known and renamed not in dest and not (renamed.endswith('.png.mcmeta') and renamed[:-7] in dest):
            note(path,'omitted','No verified target mapping; game uses target vanilla where available');continue
        if '/textures/entity/' in path and path in src and renamed in dest:
            from .semantics import variant_id
            if variant_id(path,source)!=variant_id(renamed,target):
                note(path,'omitted','Entity layout generation differs; source and target layout tags are incompatible');continue
            # Same filename is insufficient when atlas dimensions changed.
            if src[path].get('size')!=dest[renamed].get('size'):
                note(path,'omitted','Entity UV layout dimensions differ');continue
            if (before(source,'1.13'))!=(before(target,'1.13')) and src[path]['sha256']!=dest[renamed]['sha256']:
                note(path,'omitted','Cross-era entity layout not verified');continue
        if '/textures/entity/' in path and renamed in dest and path.endswith('.png'):
            expected=dest[renamed].get('size')
            actual=decode(data)
            if expected and actual.width()*expected[1]!=actual.height()*expected[0]:
                note(path,'omitted','Image aspect ratio does not match target entity UV');continue
        if path.startswith('assets/minecraft/') and ('/models/' in path or '/blockstates/' in path) and (before(source,'1.13'))!=(before(target,'1.13')):
            note(path,'omitted','Model/state schema crosses flattening boundary; target vanilla model is used');continue
        if renamed!=path:note(path,'renamed',renamed)
        if path.endswith('.json'):
            try:
                value=json.loads(data)
                if '/models/' in path and isinstance(value,dict):
                    if before(target,'1.21.11') and any('rotation' in e and 'axis' not in e['rotation'] for e in value.get('elements',[])):
                        note(path,'omitted','Target does not support multi-axis model elements');continue
                    if before(target,'26.2'):
                        value['textures']={k:v.get('sprite','') if isinstance(v,dict) else v for k,v in value.get('textures',{}).items()}
                refs={a.removeprefix('assets/minecraft/textures/').removesuffix('.png'):b.removeprefix('assets/minecraft/textures/').removesuffix('.png') for a,b in mapping.items()}
                def visit(value):
                    if isinstance(value,str):return ('minecraft:'+refs[value[10:]]) if value.startswith('minecraft:') and value[10:] in refs else refs.get(value,value)
                    if isinstance(value,list):return [visit(v) for v in value]
                    if isinstance(value,dict):return {k:visit(v) for k,v in value.items()}
                    return value
                if '/models/' in path and isinstance(value,dict) and 'textures' in value:value['textures']=visit(value['textures'])
                data=json.dumps(value,ensure_ascii=False).encode()
            except (ValueError,UnicodeError,TypeError,AttributeError,KeyError):note(path,'unresolved','JSON could not be adapted')
        out.setdefault(renamed,data)
    return out,report

def export_composition(layers,vanilla,target,fallback,fill_policy=None,protected=None):
    from .sounds import composed_definitions
    sound_definitions=composed_definitions(layers)
    if fill_policy in ('vanilla','keep'):
        from .export_priority import visible_files
        layers=visible_files(layers)
    if protected is None:
        from .export_integrity import protected_paths
        protected=protected_paths(layers)
    files={};report=[]
    for layer in reversed(layers):
        if not layer.enabled:continue
        source=source_version(layer,fallback)
        if layer.bindings:
            from dataclasses import replace
            from .core import Layer
            parts=[replace(layer,files={'0':layer.files[str(i)]},target=b['path'],regions=[b['region']],bindings=[]) for i,b in enumerate(layer.bindings)]
            files,notes=export_composition(parts+[Layer('base',files,source_version=target)],vanilla,target,fallback,protected=protected)
            report.extend(notes);continue
        if layer.kind=='component':
            if source!=target:
                from .core import Layer,pixel_rect
                data=vanilla.get(source,layer.target)
                if data is None:raise ValueError('缺少组件源版本图集：'+layer.target)
                base=decode(data);mask=base.copy();mask.fill(0)
                p=QPainter(mask)
                for region in layer.regions:p.fillRect(QRect(*pixel_rect(region,mask)),QColor('white'))
                p.end()
                complete,_=compose([layer],vanilla,source)
                converted,notes=adapt(complete,source,target,vanilla,files)
                class EmptyVanilla:
                    def get(self,version,path):
                        raw=vanilla.get(version,path)
                        if raw is None:return None
                        image=decode(raw);image.fill(0);return png(image)
                masks,_=adapt({layer.target:png(mask)},source,target,EmptyVanilla())
                for path,raw in converted.items():
                    if path not in masks or not path.endswith('.png'):continue
                    patch=decode(raw)
                    base_data=files.get(path) or vanilla.get(target,path)
                    result=decode(base_data) if base_data else patch.copy()
                    from .core import preserve_resolution
                    result=preserve_resolution(result,patch,(0,0,1,1))
                    patch=patch.scaled(result.size());coverage=decode(masks[path]).scaled(result.size())
                    if not base_data:result.fill(0)
                    # A separate coverage mask preserves deliberately erased pixels.
                    painter=QPainter(patch);painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn);painter.drawImage(0,0,coverage);painter.end()
                    painter=QPainter(result);painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut);painter.drawImage(0,0,coverage)
                    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver);painter.drawImage(0,0,patch);painter.end()
                    files[path]=png(result)
                report.extend(dict(item,layer=layer.name) for item in notes)
                continue
            from .core import Layer
            files,_=compose([layer,Layer('export base',files)],vanilla,target)
            continue
        groups={}
        from .versions import asset_tags
        inferred=asset_tags(layer.files,source)
        from .layouts import checked_layouts
        layouts,checks=checked_layouts(layer,fallback)
        for row in checks:
            report.append(dict(path=row['path'],action='layout_checked',detail=row['reason'],source=row['chosen'],target=target,layer=layer.name))
        for path,data in layer.files.items():
            # A PNG sidecar describes that texture, not the enclosing pack era.
            # Keep both in one conversion group so renaming/slicing is coherent.
            identity=path[:-7] if path.lower().endswith('.png.mcmeta') and path[:-7] in layer.files else path
            version=layouts.get(identity,layer.asset_versions.get(identity,inferred.get(identity,source)))
            groups.setdefault(version,{})[path]=data
        written=set()
        for version in sorted(groups,key=lambda v:(v==target,VERSIONS.index(v))):
            preserved={p:raw for p,raw in groups[version].items() if p in protected}
            group={p:raw for p,raw in groups[version].items() if p not in protected}
            converted,notes=adapt(group,version,target,vanilla,files if fill_policy in (None,'lower') else {})
            if fill_policy:
                from .export_priority import apply_policy
                notes+=apply_policy(group,version,target,converted,files,vanilla,{'mode':fill_policy,'below':dict(files)})
            converted.update(preserved)
            if version!=target:
                notes.extend(dict(path=p,action='extension_preserved',detail='扩展资源及其实际引用链按原路径、原内容保留；目标版本兼容性未确认',source=version,target=target) for p in preserved)
            files.update(converted)
            for path in written & converted.keys():report.append(dict(path=path,action='collision',detail='Within-layer collision: native target resources take priority, then newer source version',source=version,target=target,layer=layer.name))
            written.update(converted)
            report.extend(dict(item,layer=layer.name) for item in notes)
    files.update(sound_definitions)
    return files,report
