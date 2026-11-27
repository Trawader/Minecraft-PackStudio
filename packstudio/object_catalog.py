"""Game-object views over existing library paths; no copies or invented resources."""
import re
from collections import defaultdict
from pathlib import PurePosixPath
from .semantics import describe

TOP=('方块','战斗','工具','工具与实用物品','交通运输','道具','粒子','准心','实体','天空')
WOODS=('oak','spruce','birch','jungle','acacia','dark_oak','mangrove','cherry','bamboo','crimson','warped','pale_oak')


def hierarchy(path,full=False):
    info=describe(path);code=info['code'];stem=code.rsplit('/',1)[-1]
    if '/textures/models/armor/' in path:
        from .selector_taxonomy import entity_category
        return entity_category(path)
    if any(folder in path for folder in ('/optifine/sky/','/mcpatcher/sky/')):
        return ('贴图','天空','自定义天空') if full else ('天空','自定义天空')
    if '/textures/environment/' in path:
        return ('贴图','天空','环境贴图') if full else ('天空','环境贴图')
    if not info['versions'] or any(t in path for t in ('/optifine/','/mcpatcher/')):
        return ('其他','特殊与扩展资源') if full else None
    if code.startswith(('block/','item/','blocks/','items/')):
        from .selector_taxonomy import category,object_kind,item_base,linked_identity
        kind,name=code.split('/',1)
        kind,name=linked_identity(kind,name)
        if kind=='item':name=item_base(name);kind=object_kind(kind,name)
        return category(kind+'/'+name,path,full)
    if code.startswith('particle/'):return ('粒子',)
    if 'crosshair' in code:return ('icons',) if full else ('准心',)
    if code.startswith('entity/'):return ('实体',)
    if code.startswith(('environment/','misc/')) or 'cloud' in stem:return ('贴图',) if full else ('天空',)
    if '/gui/' in path:return ('icons',) if full and path.endswith('/icons.png') else ('贴图','界面') if full else None
    return ('其他','暂未分类') if full else None


def related_index(source):
    from .selector_taxonomy import item_base
    index=defaultdict(set)
    for path in source.files:
        if path.endswith('.png') and any(folder in path for folder in ('/textures/item/','/textures/items/')):
            parent,filename=path.rsplit('/',1);index[(parent,item_base(filename[:-4]))].add(path)
    return index


def related_paths(source,path,siblings=None,index=None):
    """Explicit local layouts for multi-state items and shared armor textures."""
    result={path};stem=PurePosixPath(path).stem
    if not any(folder in path for folder in ('/textures/item/','/textures/items/')):return result
    namespace=path.split('/')[1] if path.startswith('assets/') else 'minecraft'
    base=f'assets/{namespace}/'
    from .selector_taxonomy import item_base
    root=item_base(stem)
    candidates=index.get((path.rsplit('/',1)[0],root),()) if index is not None else siblings.get(path.rsplit('/',1)[0],()) if siblings is not None else source.files
    for candidate in candidates:
        if candidate.rsplit('/',1)[0]==path.rsplit('/',1)[0]:
            other=candidate.rsplit('/',1)[-1].removesuffix('.png')
            if candidate.endswith('.png') and item_base(other)==root:
                result.add(candidate)
    for name in (stem,root):
        for folder in ('models/item','items'):
            model=base+folder+'/'+name+'.json'
            if model in source.files:result.add(model)
    # Inventory icons and their in-world projectile share an object, not a directory.
    entity_textures={
        'arrow':('projectiles/arrow','arrow'),
        'spectral_arrow':('projectiles/spectral_arrow',),
        'tipped_arrow':('projectiles/tipped_arrow',),
        'trident':('trident',),'shield':('shield_base','shield_base_nopattern'),
        'elytra':('elytra',),'fishing_rod':('fishing_hook',)}
    result.update(base+'textures/entity/'+name+'.png' for name in entity_textures.get(root,()) if base+'textures/entity/'+name+'.png' in source.files)
    match=re.fullmatch(r'(leather|chainmail|iron|golden|diamond|netherite|turtle)_(helmet|chestplate|leggings|boots)',stem)
    if match:
        material,slot=match.groups();material='gold' if material=='golden' else material
        layer=2 if slot=='leggings' else 1
        candidates=[base+f'textures/models/armor/{material}_layer_{layer}{suffix}.png' for suffix in ('','_overlay')]
        humanoid='humanoid_leggings' if slot=='leggings' else 'humanoid'
        candidates += [base+f'textures/entity/equipment/{humanoid}/{material}{suffix}.png' for suffix in ('','_overlay')]
        candidates.append(base+f'equipment/{material}.json')
        result.update(p for p in candidates if p in source.files)
    return result


def object_entity_paths(source,identity,namespace='minecraft'):
    """Explicit item-to-entity layouts; collect existing files only."""
    kind,_,name=identity.partition('/')
    if kind!='item':return set()
    base=f'assets/{namespace}/textures/entity/';targets=set()
    if name=='elytra':targets.update(('elytra.png','equipment/wings/elytra.png'))
    boat=re.fullmatch(r'(.+?)_(chest_boat|boat|chest_raft|raft)',name)
    if name=='boat':targets.add('boat.png')
    if boat:
        wood,variant=boat.groups();folder='chest_boat' if variant.startswith('chest_') else 'boat'
        targets.update((f'{folder}/{wood}.png',f'{folder}/boat_{wood}.png',f'{folder}/boat_{wood.replace("dark_oak","darkoak")}.png'))
        if wood=='oak' and folder=='boat':targets.add('boat.png')
    if name=='minecart' or name.endswith('_minecart'):
        targets.update(('minecart.png','minecart/minecart.png'))
        if name=='chest_minecart':targets.update(('chest/normal.png','chest/normal_left.png','chest/normal_right.png'))
    if name=='saddle':
        targets.update(('pig/pig_saddle.png','strider/strider_saddle.png'))
        targets.update(p[len(base):] for p in source.files if p.startswith(base+'equipment/') and p.endswith('_saddle/saddle.png'))
    if name in ('carrot_on_a_stick','warped_fungus_on_a_stick'):
        targets.update(('fishing_hook.png',))
    return {base+path for path in targets if base+path in source.files}


def entries(source,full=False,index=None):
    output=[]
    if index is None:index=related_index(source)
    from .resource_graph import properties,sky_texture
    sky_refs=defaultdict(set)
    for path,raw in source.files.items():
        if path.endswith('.properties') and any(folder in path for folder in ('/optifine/sky/','/mcpatcher/sky/')):
            target=sky_texture(path,properties(raw).get('source'))
            if target in source.files:sky_refs[target].add(path)
    siblings=defaultdict(list)
    for path in source.files:siblings[path.rsplit('/',1)[0]].append(path)
    for path in sorted(source.files):
        if not path.lower().endswith('.png'):continue
        groups=(('贴图','天空','自定义天空') if full else ('天空','自定义天空')) if path in sky_refs else hierarchy(path,full)
        if groups:output.append((groups,path,describe(path)['name'],related_paths(source,path,siblings,index)|sky_refs.get(path,set())))
    return output
