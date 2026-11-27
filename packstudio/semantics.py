"""Local semantic identities. Paths are version bindings, never display identities."""
import json
import re
from pathlib import Path
from functools import lru_cache
from .versions import before,VERSIONS,records

DATA=Path(__file__).parent/'data'

@lru_cache(maxsize=1)
def search_tags():return json.loads((DATA/'search_tags.json').read_text('utf-8'))

def hidden_terms(code):
    stem=Path(code).stem
    terms=search_tags().get(stem,{})
    from .naming import presentation
    identity=identities()[0].get(code,code.split('/textures/')[-1].removesuffix('.png'))
    return presentation(identity,'',' '.join(terms.get('tags',[])).lower())[1]
GROUPS={'heart':'血量 / Health','crosshair':'准心 / Crosshair','ping':'延迟 / Latency',
 'experience':'经验条 / XP bar','boss':'Boss 血条 / Boss bar','food':'饥饿值 / Hunger',
 'armor':'护甲 / Armor','air':'氧气 / Air','jump':'跳跃条 / Jump bar','attack':'攻击粒子 / Combat particles',
 'potion':'药水粒子 / Potion particles','enchant':'附魔文字 / Enchanting glyphs',
 'water':'水与液滴 / Water and drips','fire':'火焰与烟花 / Fire and fireworks','other':'其他 / Other','unused':'历史未使用／用途未确认 / Historical unused or unconfirmed'}

ANIMATION_NAMES={'explosion':'爆炸','big_smoke':'篝火烟雾','cherry':'樱花落瓣','leaf':'落叶','gust':'风弹／旋风',
 'sculk_charge':'幽匿能量','sculk_soul':'幽匿灵魂','soul':'灵魂','sonic_boom':'音波攻击','shriek':'尖啸',
 'trial_spawner_detection':'试炼刷怪笼探测','geyser_base':'喷泉底部','geyser_plume':'喷泉水柱','geyser_poof':'喷泉底部水雾'}
ANIMATION_NAMES.update({'goldheart':'金色爱心（未使用）','pale_oak':'苍白橡树落叶','orange_poplar':'橙色杨树落叶','red_poplar':'红色杨树落叶','yellow_poplar':'黄色杨树落叶',
 'small_gust':'小型风弹','sculk_charge_pop':'幽匿能量消散','trial_spawner_detection_ominous':'不祥试炼刷怪笼探测','raid_omen':'袭击之兆','trial_omen':'试炼之兆','ominous_spawning':'不祥生成'})
ANIMATION_NAMES['bubble_pop']='气泡破裂'

def animation_family(path):
    if '/particle/' not in path:return None
    match=re.fullmatch(r'(.+?)_(\d+)',Path(path).stem)
    if not match:return None
    name,index=match.groups();label=ANIMATION_NAMES.get(name,name)
    return name,label+' / '+name,int(index)

@lru_cache(maxsize=11)
def particle_usage(version):
    from .core import Vanilla
    vanilla=Vanilla()
    result={}
    for path in sorted(vanilla.paths(version)):
        if not path.startswith('assets/minecraft/particles/') or not path.endswith('.json'):continue
        p=Path(path);data=json.loads(vanilla.get(version,path))
        for texture in data.get('textures',[]):
            if isinstance(texture,str):result.setdefault(texture.split(':')[-1],set()).add(p.stem)
    return {k:', '.join(sorted(v)) for k,v in result.items()}

@lru_cache(maxsize=1)
def identities():
    index=DATA/'semantic_index.json'
    if index.exists():
        data=json.loads(index.read_text('utf-8'))
        return data['paths'],{k:frozenset(v) for k,v in data['versions'].items()}
    return build_identities()

def build_identities():
    edges=json.loads((DATA/'texture_aliases.json').read_text('utf-8'));graph={}
    for e in edges:
        graph.setdefault(e['source'],set()).add(e['target']);graph.setdefault(e['target'],set()).add(e['source'])
    paths=set().union(*(records(v) for v in VERSIONS))
    for p in paths:
        q=p.replace('/textures/blocks/','/textures/block/').replace('/textures/items/','/textures/item/')
        if q!=p and q in paths:graph.setdefault(p,set()).add(q);graph.setdefault(q,set()).add(p)
    result={};availability={}
    for p in sorted(paths):
        if p in result or not p.endswith('.png'):continue
        family={p};todo=[p]
        while todo:
            for q in graph.get(todo.pop(),()):
                if q not in family:family.add(q);todo.append(q)
        canonical=max(family,key=lambda q:(max((i for i,v in enumerate(VERSIONS) if q in records(v)),default=-1),q))
        code=canonical.split('/textures/')[-1].removesuffix('.png')
        if code=='entity/boat':code='entity/boat_low'
        elif code.startswith('entity/boat/'):code+='_high'
        for q in family:result[q]=code
        availability[code]=frozenset(v for v in VERSIONS if any(q in records(v) for q in family))
    return result,availability

def variant_id(path,version):
    """UV layout variants are independent from mere changes in pixel artwork."""
    code=describe(path)['code']
    if '/entity/chest/' in path:return code+('_low' if before(version,'1.15') else '_high')
    if path.endswith('/entity/enderdragon/dragon.png'):return code+('_low' if before(version,'1.15') else '_high')
    if '/entity/horse/' in path:return code+('_low' if before(version,'1.13') else '_high')
    if '/entity/' in path and not code.endswith(('_low','_high')):
        size=records(version).get(path,{}).get('size')
        shapes={tuple(records(v)[path]['size']) for v in VERSIONS if path in records(v) and 'size' in records(v)[path]}
        if size and len(shapes)>1:
            first=next(v for v in VERSIONS if records(v).get(path,{}).get('size')==size)
            return code+'_'+first
    return code

@lru_cache(maxsize=1)
def translations():
    zh=json.loads((DATA/'game_names_zh.json').read_text('utf-8'))
    en={}
    from .core import Vanilla
    vanilla=Vanilla()
    for v in VERSIONS:
        raw=vanilla.get(v,'assets/minecraft/lang/en_us.json')
        if raw:en.update(json.loads(raw))
    return zh,en

def category(path):
    if '/textures/blocks/' in path or '/textures/block/' in path:return '方块 / Blocks'
    if '/textures/items/' in path or '/textures/item/' in path:return '物品 / Items'
    if '/textures/entity/' in path:return '生物（实体）/ Entities'
    if '/gui/' in path:return 'GUI'
    if '/particle/' in path:return '粒子 / Particles'
    return '贴图 / Textures'

def block_category(code):
    if any(x in code for x in ('stairs','slab','wall','fence')):return '建筑部件 / Building parts'
    if any(x in code for x in ('ore','diamond','emerald','gold','iron','copper','coal','lapis')):return '矿物 / Minerals'
    if any(x in code for x in ('flower','leaves','sapling','grass','fern','mushroom','crop','wheat','vine')):return '植物 / Plants'
    if any(x in code for x in ('log','wood','planks','bamboo')):return '木材 / Wood'
    if any(x in code for x in ('chest','furnace','crafting','anvil','hopper','piston','redstone','dispenser')):return '功能方块 / Functional blocks'
    return '基础方块 / Basic blocks'

@lru_cache(maxsize=40000)
def describe(path):
    ids,available=identities();code=ids.get(path,path.split('/textures/')[-1].removesuffix('.png'))
    stem=code.split('/')[-1];zh,en=translations();keys=[f'{kind}.minecraft.{stem}' for kind in ('block','item','entity')]
    # Face textures share the actual in-game object name; retain the suffix for precision.
    base=stem
    while '_' in base and not any(k in zh or k in en for k in keys):
        base=base.rsplit('_',1)[0];keys=[f'{kind}.minecraft.{base}' for kind in ('block','item','entity')]
    cn=next((zh[k] for k in keys if k in zh),'');english=next((en[k] for k in keys if k in en),stem.replace('_',' ').title())
    label=f'{cn} / {english}' if cn else english
    if base!=stem:label+=f' · {stem}'
    legacy_key='item.'+Path(path).stem.replace('_','.')+'.name'
    if legacy_key in zh:label=zh[legacy_key]+' / '+Path(path).stem
    historical={'quiver':'箭袋（历史未使用）','ruby':'红宝石（历史未使用）','spawn_egg':'刷怪蛋底色','spawn_egg_overlay':'刷怪蛋斑点',
      'empty_armor_slot_boots':'靴子空槽图标','empty_armor_slot_chestplate':'胸甲空槽图标','empty_armor_slot_helmet':'头盔空槽图标','empty_armor_slot_leggings':'护腿空槽图标'}
    if Path(path).stem in historical:label=historical[Path(path).stem]+' / '+Path(path).stem
    group=part_group(path) if '/gui/sprites/' in path or '/particle/' in path else 'other'
    if group!='other':label=part_name(path)
    family=animation_family(path)
    if family:label=f'{family[1]} · 帧 {family[2]}'
    if '/particle/' in path and Path(path).stem in search_tags():label=search_tags()[Path(path).stem]['name']
    keywords=GROUPS[group] if group!='other' else ''
    tags=hidden_terms(path) if '/particle/' in path else ''
    from .naming import presentation
    label,search=presentation(code,label,f'{label} {keywords} {tags} {code} {path}'.lower())
    return {'code':code,'name':label,'search':search,'versions':available.get(code,frozenset()),'category':category(path)}

def part_group(target):
    n=Path(target).stem
    if '/heart/' in target:return 'heart'
    if 'crosshair' in n:return 'crosshair'
    if 'ping' in n:return 'ping'
    if 'experience' in n:return 'experience'
    if 'boss' in target:return 'boss'
    for key in ('food','armor','air','jump'):
        if n.startswith(key):return key
    if n in ('critical_hit','enchanted_hit','damage') or 'sweep' in n:return 'attack'
    if n.startswith(('effect_','spell_')):return 'potion'
    if n.startswith('sga_'):return 'enchant'
    if n.startswith(('bubble','splash','drip','rain')):return 'water'
    if n.startswith(('flame','lava','spark','glitter','flash','smoke','generic_')):return 'fire'
    return 'other'

def part_name(target):
    from .naming import presentation
    code=target.split('/textures/')[-1].removesuffix('.png')
    return presentation(code,default_part_name(target))[0]

def default_part_name(target):
    n=Path(target).stem;group=part_group(target)
    if '/particle/' in target and n in search_tags():return search_tags()[n]['name']
    if group=='heart':
        words=[]
        for key,label in [('vehicle','坐骑'),('poisoned','中毒'),('withered','凋零'),('absorbing','伤害吸收'),('frozen','冰冻'),('hardcore','极限模式')]:
            if key in n:words.append(label)
        if not words:words.append('普通')
        words.append('空心（底框）' if 'container' in n else '半心' if 'half' in n else '满心')
        if 'blinking' in n:words.append('受伤闪烁')
        return ' · '.join(words)+' / '+n
    fixed={'crosshair':'准心','critical_hit':'暴击','enchanted_hit':'附魔攻击（锋利等）','damage':'伤害','bubble':'气泡','heart':'爱心','note':'音符','angry':'愤怒','glint':'闪光','flame':'火焰','lava':'熔岩','flash':'烟花闪光'}
    fixed['fishing_hook']='鱼钩'
    if n in fixed:return fixed[n]+' / '+n
    if group=='other':return n.replace('_',' ')+' / '+n
    if group=='enchant':return '附魔文字 '+n[-1].upper()+' / '+n
    if group=='ping':return '延迟状态 / '+n
    prefix=GROUPS.get(group,'其他').split(' / ')[0]
    state='空 / 背景' if 'background' in n or 'empty' in n else '填充 / 满' if 'progress' in n or 'full' in n else '半' if 'half' in n else '帧 '+n.rsplit('_',1)[-1]
    return f'{prefix} · {state} / {n}'

@lru_cache(maxsize=2048)
def parts(path,version):
    from .adaptation import RULES_BY_SOURCE,slot
    out=[];seen=set()
    for rule in RULES_BY_SOURCE.get(path,[]):
        match=slot(rule,version)
        if not match or match[0]!=path:continue
        x,y,w,h,tw,th=match[1];r=(x/tw,y/th,w/tw,h/th)
        if r in seen:continue
        seen.add(r);out.append({'name':part_name(rule['target']),'regions':[r],'code':rule['target'].split('/textures/')[-1].removesuffix('.png'),'group':part_group(rule['target'])})
    # Before 1.9 the boss bar was still part of icons.png.
    if path.endswith('/gui/icons.png') and before(version,'1.9'):
        for y,state in [(74,'空 / Background'),(79,'满 / Progress')]:
            out.append({'name':'Boss 血条 · '+state,'regions':[(0,y/256,182/256,5/256)],'code':'gui/boss/'+str(y),'group':'boss'})
    if path.endswith('/particle/particles.png'):
        size=256 if version=='1.13.2' else 128
        for x,y,label in [(0,48,'浅蓝图案 1（未使用，用途未知）'),(8,48,'浅蓝图案 2（未使用，用途未知）'),(24,40,'愤怒村民头部（未使用）')]:
            out.append({'name':label,'regions':[(x/size,y/size,8/size,8/size)],'code':f'particle/unused_{x}_{y}','group':'unused'})
    if path.endswith('/gui/icons.png'):
        for x,y,label in [(34,0,'红色心形轮廓（历史未使用）'),(43,0,'白色心形轮廓（历史未使用）'),(61,9,'坐骑空心闪烁（旧版）')]:
            r=(x/256,y/256,9/256,9/256)
            if r not in seen:out.append({'name':label,'regions':[r],'code':f'gui/legacy_{x}_{y}','group':'heart' if x==61 else 'unused'})
    from .naming import presentation
    for part in out:part['name']=presentation(part['code'],part['name'])[0]
    return out

def grouped_parts(path,version):
    groups={}
    for part in parts(path,version):groups.setdefault(part['group'],[]).append(part)
    return groups

@lru_cache(maxsize=4096)
def component_versions(code):
    from .adaptation import RULES,slot
    target='assets/minecraft/textures/'+code+'.png'
    matching=[r for r in RULES if r['target']==target]
    return frozenset(v for v in VERSIONS if any(slot(r,v) for r in matching))
