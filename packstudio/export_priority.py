"""Whole-file priority, with explicit opt-in atlas fallback policies."""
from .core import decode,png
from .versions import source_version

def visible_files(layers):
    from dataclasses import replace
    covered=set();result=[]
    for layer in layers:
        if not layer.enabled:continue
        if layer.kind=='component':result.append(layer);continue
        files={p:data for p,data in layer.files.items() if p not in covered};covered.update(layer.files)
        if files:result.append(replace(layer,files=files))
    return result

def atlas_slots(files,source,target):
    from .adaptation import RULES,slot,crop
    seen=set();images={}
    for rule in RULES:
        sheet=rule['source']
        if sheet not in files or not sheet.endswith(('/gui/icons.png','/particle/particles.png')):continue
        a,b=slot(rule,source),slot(rule,target)
        if not b:continue
        key=(b[0],tuple(b[1]))
        if key in seen:continue
        seen.add(key)
        missing=a is None
        if a:
            if sheet not in images:images[sheet]=decode(files[sheet])
            patch=crop(images[sheet],a[1])
            missing=not any(patch.pixelColor(x,y).alpha() for y in range(patch.height()) for x in range(patch.width()))
        yield {'sheet':sheet,'path':b[0],'box':b[1],'missing':missing,'id':rule['target']}

def missing_atlases(layers,target,fallback):
    from .layouts import checked_layouts
    result=[];covered=set()
    for layer in visible_files(layers):
        if not layer.enabled or layer.kind=='component':continue
        layouts,_=checked_layouts(layer,fallback);groups={}
        for path,raw in layer.files.items():
            if path in covered:continue
            covered.add(path);v=layouts.get(path,layer.asset_versions.get(path,source_version(layer,fallback)))
            groups.setdefault(v,{})[path]=raw
        for version,files in groups.items():
            result.extend(dict(row,layer=layer.name) for row in atlas_slots(files,version,target) if row['missing'])
    return result

def apply_policy(group,source,target,converted,below,vanilla,policy):
    from .adaptation import crop,paint
    rows=list(atlas_slots(group,source,target));report=[]
    # A top atlas owns its complete semantic family even when the target uses sprites.
    # Preserve a lower copy solely for the explicitly selected B fallback.
    for row in rows:
        if row['path']!=row['sheet']:below.pop(row['path'],None)
    for row in rows:
        if not row['missing']:continue
        path,box=row['path'],row['box']
        fallback=policy.get('below',{}).get(path) if policy['mode']=='lower' else None
        fallback=fallback or (vanilla.get(target,path) if policy['mode']!='keep' else None)
        if fallback:patch=crop(decode(fallback),box)
        else:
            raw=converted.get(path) or vanilla.get(target,path)
            if not raw:continue
            patch=crop(decode(raw),box);patch.fill(0)
        if box==[0,0,1,1,1,1]:
            if policy['mode']=='keep' and path not in converted:continue
            converted[path]=png(patch)
        else:
            raw=converted.get(path) or vanilla.get(target,path)
            if not raw:continue
            image=decode(raw);paint(image,patch,box);converted[path]=png(image)
        report.append({'path':path,'action':'atlas_fallback','detail':policy['mode']+' · '+row['id'],'source':source,'target':target})
    return report

def choose_policy(parent,layers,vanilla,target,fallback):
    if target=='unchanged':return 'keep'
    rows=missing_atlases(layers,target,fallback)
    if not rows:return 'vanilla'
    from PySide6.QtWidgets import QMessageBox
    box=QMessageBox(parent);box.setWindowTitle('图集缺失处理')
    box.setText(f'发现 {len(rows)} 个目标部件没有来源，或在来源图集中完全透明。请选择本次导出方式。')
    box.setInformativeText('A：使用目标版本原版补全。\nB：按覆盖顺序寻找下层部件补全，找不到再用原版。\nC：不补全，保留透明或缺失。\n完全透明也可能是刻意隐藏的素材；这时请选择 C。')
    a=box.addButton('A 原版补全',QMessageBox.ButtonRole.AcceptRole)
    b=box.addButton('B 自动适配（下层补全）',QMessageBox.ButtonRole.AcceptRole)
    c=box.addButton('C 继续导出（不补全）',QMessageBox.ButtonRole.AcceptRole)
    box.addButton(QMessageBox.StandardButton.Cancel);box.setDefaultButton(a)
    box.setDetailedText('\n'.join(r['layer']+' · '+r['id'] for r in rows));box.exec()
    return {a:'vanilla',b:'lower',c:'keep'}.get(box.clickedButton())
