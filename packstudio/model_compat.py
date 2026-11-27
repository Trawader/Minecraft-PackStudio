"""Conservative model compatibility based on shipped vanilla asset identities.

Retain source paths as aliases. Translate only evidenced targets and supported
JSON fields; unknown geometry/conditions remain intact and are reported.
"""
import copy,json
from .versions import records,before


def adapt_models(files,source,target,vanilla):
    if source==target:return dict(files),[]
    from .adaptation import rename_map
    from .export_integrity import is_model_config
    from .resource_graph import ResourceGraph
    texture_map=rename_map(source,target);src=records(source);dest=records(target)
    files=dict(files)
    # Some vanilla parents disappeared in the destination. Bring the referenced
    # source definition along instead of leaving a dangling parent. Textures
    # with verified target aliases can continue using destination vanilla.
    checked=set()
    while True:
        graph=ResourceGraph(files).parse()
        roots={p for p in files if is_model_config(p)}
        _,missing=graph.closure(roots,include_callers=False)
        added=False
        for path in missing-checked:
            checked.add(path)
            if path in dest or texture_map.get(path,path) in dest:continue
            if not ('/models/' in path and path.endswith('.json') or '/textures/' in path and path.endswith('.png')):continue
            raw=vanilla.get(source,path)
            if raw is not None:
                files[path]=raw;added=True
                if path.endswith('.png'):
                    sidecar=vanilla.get(source,path+'.mcmeta')
                    if sidecar is not None:files[path+'.mcmeta']=sidecar
        if not added:break
    model_map={}
    for a,b in texture_map.items():
        for kind in ('item','block'):
            prefixes=(f'assets/minecraft/textures/{kind}/',f'assets/minecraft/textures/{kind}s/')
            if not a.startswith(prefixes) or not b.startswith(prefixes):continue
            old=f'assets/minecraft/models/{kind}/'+a.rsplit('/',1)[1][:-4]+'.json'
            new=f'assets/minecraft/models/{kind}/'+b.rsplit('/',1)[1][:-4]+'.json'
            if old in src and new in dest and old not in dest:model_map[old]=new
    out=dict(files);notes=[];graph=ResourceGraph(files)
    def note(path,detail,action='unresolved'):
        notes.append(dict(path=path,action=action,detail=detail,source=source,target=target))
    def ref(path,value,folder,extension,mapping):
        if not isinstance(value,str) or value.startswith('#'):return value
        if value in ('builtin/generated','builtin/entity','minecraft:builtin/generated','minecraft:builtin/entity'):return value
        resolved=graph.resource(path,value,folder,extension)
        if not resolved:return value
        # Legacy bare blockstate names refer to models/block, including vanilla parents.
        if folder=='models' and '/blockstates/' in path and '/' not in value.split(':')[-1]:
            ns,name=resolved.split('/')[1],resolved.rsplit('/',1)[1]
            resolved=f'assets/{ns}/models/block/{name}'
        mapped=mapping.get(resolved,resolved)
        parts=mapped.split('/',3)
        return parts[1]+':'+parts[3].removesuffix(extension)
    # Preserve originals and emit target aliases for all supplied referenced textures.
    for path,raw in files.items():
        target_path=texture_map.get(path)
        if target_path and target_path not in files:out[target_path]=raw
        if path.endswith('.png.mcmeta') and path[:-7] in texture_map:
            out.setdefault(texture_map[path[:-7]]+'.mcmeta',raw)
    for path,raw in files.items():
        if not is_model_config(path):continue
        try:value=json.loads(raw.decode('utf-8-sig'))
        except (ValueError,UnicodeError):
            note(path,'JSON 无法解析，保留原始模型配置');continue
        if not isinstance(value,dict):
            note(path,'非标准模型配置结构，保留原文件');continue
        value=copy.deepcopy(value);target_path=model_map.get(path,path)
        if '/models/' in path:
            if 'parent' in value:value['parent']=ref(path,value['parent'],'models','.json',model_map)
            textures=value.get('textures')
            if isinstance(textures,dict):
                for key,entry in list(textures.items()):
                    if isinstance(entry,str):textures[key]=ref(path,entry,'textures','.png',texture_map)
                    elif isinstance(entry,dict) and isinstance(entry.get('sprite'),str):
                        entry['sprite']=ref(path,entry['sprite'],'textures','.png',texture_map)
                        if before(target,'26.2'):
                            if set(entry)=={'sprite'}:textures[key]=entry['sprite']
                            else:note(path,'贴图对象含额外字段，保留原结构；旧版本可能不支持')
            display=value.get('display')
            if isinstance(display,dict) and before(source,'1.9')!=before(target,'1.9'):
                for old,new in (('firstperson','firstperson_righthand'),('thirdperson','thirdperson_righthand')):
                    a,b=(old,new) if before(source,'1.9') else (new,old)
                    if a in display and b not in display:display[b]=copy.deepcopy(display[a])
            elements=value.get('elements',[])
            if before(target,'1.21.11') and isinstance(elements,list) and any(isinstance(e,dict) and isinstance(e.get('rotation'),dict) and 'axis' not in e['rotation'] for e in elements):
                note(path,'多轴旋转模型已保留，目标版本不支持该旋转格式')
            if before(target,'1.8'):
                note(path,'模型 JSON 已保留，目标版本没有对应的标准模型加载机制')
            if value.get('overrides') and not before(target,'1.21.11'):
                note(path,'旧式 overrides 已保留；新版物品选择器需单独适配')
        if '/blockstates/' in path:
            variants=value.get('variants')
            if isinstance(variants,dict) and before(source,'1.13')!=before(target,'1.13'):
                a,b=('normal','') if before(source,'1.13') else ('','normal')
                if a in variants and b not in variants:variants[b]=variants.pop(a)
            target_raw=vanilla.get(target,target_path)
            if target_raw:
                try:expected=json.loads(target_raw)
                except (ValueError,UnicodeError):expected={}
                if isinstance(variants,dict) and isinstance(expected.get('variants'),dict) and not set(variants)<=set(expected['variants']):
                    note(path,'方块状态键与目标原版不同，已保留自定义条件，请确认目标版本状态属性')
            else:note(path,'目标版本未找到同名方块状态入口，原配置保留')
        if '/items/' in path and before(target,'1.21.11'):
            note(path,'新版物品定义已保留，旧版本不支持此入口')
        def walk(node):
            if isinstance(node,dict):
                if isinstance(node.get('model'),str):node['model']=ref(path,node['model'],'models','.json',model_map)
                for child in node.values():walk(child)
            elif isinstance(node,list):
                for child in node:walk(child)
        walk(value)
        encoded=json.dumps(value,ensure_ascii=False).encode('utf-8')
        # Native target resources take priority over a generated alias.
        if target_path==path or target_path not in files:out[target_path]=encoded
        if target_path!=path:note(path,target_path,'model_renamed')
        else:note(path,'模型配置及依赖保留，已适配可确认的引用与显示字段','model_preserved')
        if '/models/item/' in target_path and not before(target,'1.21.11'):
            item=target_path.replace('/models/item/','/items/')
            if item not in out:
                default=vanilla.get(target,item)
                if default:out[item]=default
    return out,notes
