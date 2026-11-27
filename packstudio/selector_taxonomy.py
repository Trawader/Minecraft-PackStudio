"""Game identities, not texture filenames, determine selector categories.

Wiki references and editorial choices: docs/selector-classification.md.
"""
import re
import json
from functools import lru_cache
from .semantics import translations,describe
from .versions import before

TOOLS={'pickaxe':'镐','axe':'斧','shovel':'锹','hoe':'锄','shears':'剪刀','flint_and_steel':'打火石',
       'brush':'刷子','fishing_rod':'钓鱼竿','carrot_on_a_stick':'骑乘控制','warped_fungus_on_a_stick':'骑乘控制',
       'compass':'定位与测量','recovery_compass':'定位与测量','clock':'定位与测量','spyglass':'望远镜',
       'lead':'生物交互','name_tag':'生物交互','saddle':'骑乘装备','elytra':'飞行装备'}
MOB_DROPS=set('bone string feather leather rabbit_hide rabbit_foot rotten_flesh spider_eye gunpowder slime_ball slimeball magma_cream blaze_rod blaze_powder breeze_rod ghast_tear ender_pearl shulker_shell phantom_membrane ink_sac glow_ink_sac scute turtle_scute armadillo_scute nether_star prismarine_shard prismarine_crystals nautilus_shell honeycomb egg'.split())
FOOD=set('apple golden_apple enchanted_golden_apple bread cookie melon_slice sweet_berries glow_berries chorus_fruit carrot golden_carrot potato baked_potato poisonous_potato beetroot dried_kelp beef cooked_beef porkchop cooked_porkchop mutton cooked_mutton chicken cooked_chicken rabbit cooked_rabbit cod cooked_cod salmon cooked_salmon tropical_fish pufferfish mushroom_stew rabbit_stew beetroot_soup suspicious_stew honey_bottle milk_bucket'.split())


@lru_cache(maxsize=16384)
def item_base(name):
    if name=='broken_elytra':return 'elytra'
    # "bowl" is not "bow"; "spectral_arrow" is an arrow, not a state of "spectral".
    match=re.fullmatch(r'(.+?)_(pulling_\d+|pull_\d+|standby|charged|firework|arrow|broken|cast|overlay|blocking|throwing|in_hand)',name)
    if match and (match[1] in ('bow','crossbow','shield','elytra','fishing_rod','trident','potion','splash_potion','lingering_potion','tipped_arrow') or match[1].startswith('leather_')):return match[1]
    if re.fullmatch(r'(?:recovery_compass|compass|clock)_\d+',name):return name.rsplit('_',1)[0]
    trim=re.fullmatch(r'((?:leather|chainmail|iron|golden|diamond|netherite|turtle)_(?:helmet|chestplate|leggings|boots))_(?:.+_)?trim',name)
    if trim:return trim[1]
    return name


HEADS={'skull_skeleton':'skeleton_skull','skull_wither':'wither_skeleton_skull','skull_steve':'player_head',
       'skull_zombie':'zombie_head','skull_creeper':'creeper_head','skull_dragon':'dragon_head'}
HEAD_NAMES=set(HEADS.values())|{'piglin_head'}


def linked_identity(kind,name):
    """Explicit inventory/block relationships; never match arbitrary name fragments."""
    kind={'items':'item','blocks':'block'}.get(kind,kind)
    if name in HEADS:return 'block',HEADS[name]
    if name in HEAD_NAMES:return 'block',name
    for crop in ('pumpkin','melon'):
        if name in (crop+'_stem','attached_'+crop+'_stem',crop+'_stem_connected',crop+'_stem_disconnected'):
            return 'item',crop+'_seeds'
    return kind,name


def object_kind(kind,name,namespace='minecraft',block_names=()):
    if kind!='item':return kind
    if (namespace,name) in block_names:return 'block'
    if namespace=='minecraft':
        zh,en=translations()
        # Legacy packs can lack blockstate JSON, while still providing a block's inventory icon.
        if any('block.minecraft.'+name in names for names in (zh,en)) and not any('item.minecraft.'+name in names for names in (zh,en)):return 'block'
    return kind


def material_family(name):
    """Families organize existing objects inside their creative category, not new objects."""
    if name=='wool' or name.endswith(('_wool','_carpet')) or name=='carpet':return ('羊毛家族',)
    if name.endswith('_glazed_terracotta'):return ('陶瓦家族','上釉陶瓦（独立纹理）')
    if name in ('terracotta','hardened_clay','stained_hardened_clay') or name.endswith('_terracotta'):return ('陶瓦家族',)
    if name.endswith('_concrete_powder'):return ('混凝土粉末家族',)
    if name.endswith('_concrete'):return ('混凝土家族',)
    if name in ('glass','glass_pane','tinted_glass') or name.endswith(('_stained_glass','_stained_glass_pane')):return ('玻璃家族',)
    woods=('oak','spruce','birch','jungle','acacia','dark_oak','mangrove','cherry','bamboo','crimson','warped','pale_oak')
    plain=name.removeprefix('stripped_')
    if any(plain.startswith(wood+'_') for wood in woods) and plain.endswith(('_planks','_log','_wood','_stem','_hyphae','_stairs','_slab','_fence','_fence_gate','_door','_trapdoor','_button','_pressure_plate','_sign')):return ('木材家族',)
    stone=('stone','smooth_stone','cobblestone','mossy_cobblestone','stone_brick','stone_bricks','mossy_stone_bricks','cracked_stone_bricks','chiseled_stone_bricks','granite','polished_granite','andesite','polished_andesite','diorite','polished_diorite','deepslate','cobbled_deepslate','polished_deepslate','sandstone','red_sandstone','blackstone','polished_blackstone','tuff','end_stone')
    if any(name==base or name.startswith(base+'_') for base in stone):return ('石材家族',)
    return ()


def category(identity,preview,full=False,version='1.8.9'):
    if identity.startswith(('entity/','models/armor/')):return entity_category(preview)
    if '/particle/' in preview and not preview.endswith('/particles.png'):
        from .semantics import part_group,GROUPS,animation_family
        family=animation_family(preview);group=GROUPS[part_group(preview)]
        return ('粒子',group,family[1]+' · 动画帧') if family else ('粒子',group)
    base=creative_category(identity,preview,full,version)
    kind,_,name=identity.partition('/');kind,name=linked_identity(kind,name)
    family=material_family(name) if kind=='block' else ()
    if not base or not family or base[0]!='方块':return base
    # Preserve the creative category, with the agreed material-family collection below it.
    tail=base[2:]
    if tail==('木材',):tail=()
    return base[:2]+family+tail


def creative_category(identity,preview,full=False,version='1.8.9'):
    kind,_,name=identity.partition('/')
    kind,name=linked_identity(kind,name)
    legacy=before(version,'1.19.3')
    materials=('道具','材料') if version in ('1.7.10','1.8.9','1.9.4') else ('道具',) if legacy else ('道具','原材料')
    if name in HEAD_NAMES:return ('方块','装饰方块' if legacy else '功能方块','头颅')
    if name in ('elytra','boat','minecart','saddle','carrot_on_a_stick','warped_fungus_on_a_stick','rail','powered_rail','detector_rail','activator_rail') or name.endswith(('_minecart','_boat','_raft')):
        return ('交通运输',) if legacy else ('工具与实用物品','交通运输')
    if name in ('snowball','fire_charge'):return ('道具',) if legacy else ('道具','原材料')
    if name in ('pumpkin_seeds','melon_seeds','wheat_seeds','beetroot_seeds'):
        return materials+('种子',) if legacy else ('方块','自然方块','种子')
    if kind=='block':
        zh,en=translations()
        if not any('block.minecraft.'+name in names for names in (zh,en)):return None
        if name.endswith('_trapdoor'):return ('方块','红石','活板门')
        if name.endswith('_door') or name=='door':return ('方块','红石','门')
        for suffix,title in [('fence_gate','栅栏门'),('button','按钮'),('pressure_plate','压力板')]:
            if name.endswith('_'+suffix):return ('方块','红石',title)
        if name in ('redstone','redstone_wire','redstone_block','redstone_torch','redstone_lamp','piston','sticky_piston','observer','repeater','comparator','dispenser','dropper','hopper','tripwire_hook','daylight_detector','target','lever','tnt','trapped_chest'):return ('方块','红石')
        for suffix,title in [('stairs','楼梯'),('slab','台阶'),('fence','栅栏'),('wall','墙')]:
            if name.endswith('_'+suffix):return ('方块','装饰方块' if legacy and suffix in ('fence','wall') else '建筑方块',title)
        if legacy and name in ('brewing_stand','cauldron'):return ('道具','酿造')
        if legacy and name=='beacon':return ('道具',)
        if any(token in name for token in ('anvil','furnace','smoker','chest','barrel','crafting','enchanting','brewing','cauldron','loom','stonecutter','grindstone','smithing','cartography','fletching','beacon','lectern','composter','shulker_box')):return ('方块','装饰方块' if legacy else '功能方块')
        if name.endswith(('_sign','_hanging_sign','_bed','_banner','_candle')) or name in ('bed','sign','banner','candle','flower_pot','decorated_pot','lantern','soul_lantern'):return ('方块','装饰方块')
        if name.endswith(('_carpet','_glass_pane')) or name=='glass_pane':return ('方块','装饰方块' if legacy else '染色方块')
        if any(token in name for token in ('glass','wool','terracotta','concrete')):return ('方块','建筑方块' if legacy else '染色方块')
        if name.endswith(('_log','_wood','_planks','_stem','_hyphae')):return ('方块','建筑方块','木材')
        if legacy:
            if any(token in name for token in ('leaves','flower','sapling','mushroom','coral','vine','fern','bush')) or name in ('grass','tall_grass','dead_bush','cactus','lily_pad','torch','ladder','snow'):return ('方块','装饰方块')
            return ('方块','建筑方块')
        if any(token in name for token in ('ore','dirt','grass','sand','leaves','flower','sapling','ice','snow','water','lava','mushroom','coral','vine','crop','wheat','carrots','potatoes','beetroots','wart')):return ('方块','自然方块')
        return ('方块','建筑方块')
    if kind=='item':
        name=item_base(name)
        if name in ('arrow','spectral_arrow','tipped_arrow'):return ('战斗','武器','箭与弹药')
        if name in ('bow','crossbow','trident','mace'):return ('战斗','武器')
        if name.endswith(('_sword','_spear')):return ('战斗','武器','剑' if name.endswith('_sword') else '矛')
        if name=='wind_charge':return ('战斗',)
        if name in ('firework_rocket','firework_star'):return ('道具',) if legacy else ('工具与实用物品',)
        if name.endswith(('_horse_armor','_wolf_armor')) or name=='wolf_armor':return ('道具','马铠') if legacy else ('战斗','坐骑与生物护甲')
        for suffix,title in [('helmet','头盔'),('chestplate','胸甲'),('leggings','护腿'),('boots','靴子')]:
            if name.endswith('_'+suffix):return ('战斗','防具',title)
        if name in ('shield','totem_of_undying'):return ('战斗',)
        for suffix in ('pickaxe','axe','shovel','hoe'):
            if name.endswith('_'+suffix):return ('工具' if legacy else '工具与实用物品',TOOLS[suffix])
        if name in TOOLS:return ('工具' if legacy else '工具与实用物品',)
        if name.endswith('_dye'):return materials+('染料',)
        if name in ('ghast_tear','fermented_spider_eye','blaze_powder','magma_cream','glistering_melon_slice','golden_carrot','rabbit_foot','dragon_breath','potion','splash_potion','lingering_potion','glass_bottle'):
            return ('道具','酿造') if legacy else ('道具','食物与饮品') if name.endswith('potion') or name=='golden_carrot' else materials
        if name=='milk_bucket':return ('道具',) if legacy else ('道具','食物与饮品')
        if name in FOOD or name in ('rotten_flesh','spider_eye','pumpkin_pie'):return ('道具','食物' if legacy else '食物与饮品')
        if name in ('bone','slime_ball','slimeball','ender_pearl','ender_eye'):return ('道具',) if legacy else materials
        if name in MOB_DROPS:return materials
        if name.endswith('_spawn_egg'):return ('道具','刷怪蛋')
        if name=='bowl':return materials
        if name.endswith(('_bucket','_bundle')) or name in ('bucket','bundle','milk_bucket'):return ('道具',) if legacy else ('工具与实用物品',)
        if name in ('map','filled_map','writable_book','written_book','book','enchanted_book','paper'):return ('道具',) if legacy else ('工具与实用物品',)
        if name.startswith('music_disc_') or name in ('goat_horn','disc_fragment_5'):return ('道具','唱片与乐器')
        if name.endswith(('_smithing_template','_pottery_sherd','_banner_pattern')):return ('道具','模板与纹样')
        if name.endswith(('_ingot','_nugget')) or name.startswith('raw_') or name in ('coal','charcoal','diamond','emerald','lapis_lazuli','quartz','amethyst_shard','netherite_scrap','flint','clay_ball','brick','nether_brick','echo_shard','stick','bowl'):return materials
        if name.endswith('_seeds') or name in ('wheat','sugar','cocoa_beans','bone_meal'):return materials
        return None
    from .object_catalog import hierarchy
    return hierarchy(preview,full)


def entity_category(path):
    if '/horse/armor/' in path or path.endswith('_saddle.png'):return ('实体','其他')
    relative=path.split('/textures/entity/',1)[-1].removesuffix('.png')
    mobs={'allay','armadillo','axolotl','bat','bee','blaze','breeze','camel','cat','chicken','cod','cow','creaking','creeper','dolphin','donkey','drowned','elder_guardian','enderdragon','dragon','enderman','endermite','evoker','fox','frog','ghast','happy_ghast','glow_squid','goat','guardian','hoglin','horse','husk','illusioner','iron_golem','irongolem','llama','magma_cube','mooshroom','mule','ocelot','panda','parrot','phantom','pig','piglin','piglin_brute','pillager','polar_bear','polarbear','pufferfish','rabbit','ravager','salmon','sheep','shulker','silverfish','skeleton','slime','sniffer','snow_golem','snowman','spider','squid','stray','strider','tadpole','trader_llama','tropical_fish','turtle','vex','villager','vindicator','wandering_trader','warden','witch','wither','wither_skeleton','wolf','zoglin','zombie','zombie_villager','zombie_pigman','zombified_piglin','zombie_pig','nautilus'}
    root=relative.split('/')[0]
    mob=root in mobs or any(root.startswith(name+'_') for name in mobs)
    return ('实体','生物' if mob and '/models/armor/' not in path else '其他')


@lru_cache(maxsize=8)
def _language_files(entries):
    result={}
    for path,raw in entries:
        try:
            text=raw.decode('utf-8-sig')
            data=json.loads(text) if path.endswith('.json') else dict(line.split('=',1) for line in text.splitlines() if '=' in line and not line.lstrip().startswith('#'))
            if isinstance(data,dict):result.update({(path.split('/')[1],key):value for key,value in data.items() if isinstance(value,str)})
        except (UnicodeError,ValueError):continue
    return result


def local_names(files,language='zh'):
    locale='zh_cn' if language=='zh' else 'en_us'
    return _language_files(tuple(sorted((p,raw) for p,raw in files.items() if '/lang/' in p and p.lower().endswith(('/'+locale+'.json','/'+locale+'.lang')))))


def english_name(identity,preview,namespace='minecraft',names=None):
    if ':' in identity:namespace,identity=identity.split(':',1)
    kind,_,name=identity.partition('/')
    if not name:name=kind
    _,en=translations()
    keys=[f'{k}.{namespace}.{name.replace("/",".")}' for k in (kind,'block','item','entity')]
    for key in keys:
        if names and (namespace,key) in names:return names[(namespace,key)]
        if key in en:return en[key]
    label=describe(preview)['name']
    if ' / ' in label:return label.split(' / ',1)[1]
    return name.replace('/',' · ').replace('_',' ').title()



def chinese_name(identity,preview,namespace='minecraft',names=None):
    kind,_,name=identity.partition('/');zh,en=translations()
    if not name:name=kind;kind='resource'
    keys=[f'{k}.{namespace}.{name.replace("/",".")}' for k in (kind,'block','item','entity')]
    for key in keys:
        if names and (namespace,key) in names:return names[(namespace,key)]
    for key in keys:
        if key in zh:return zh[key]
    for suffix,title in [('top','顶面'),('bottom','底面'),('side','侧面'),('front','正面'),('back','背面'),('overlay','叠加层'),('stage','生长阶段')]:
        base,sep,tail=name.rpartition('_'+suffix)
        if sep:
            for k in ('block','item','entity'):
                value=zh.get(f'{k}.{namespace}.{base}')
                if value:return value+' · '+title+tail.replace('_',' ')
    # Reuse the semantic catalogue's existing translated names for legacy aliases.
    fallback=describe(preview)['name']
    if re.search('[\u4e00-\u9fff]',fallback):
        translated=fallback.split(' / ')[0]
        return translated+' · '+name if ' · ' in fallback else translated
    from .resource_names import chinese_resource_name
    return chinese_resource_name(identity,preview,namespace)


STATE_KEYS={'facing':'朝向','axis':'轴向','half':'半部','hinge':'门轴','open':'开启','powered':'通电','lit':'点亮','age':'生长阶段','stage':'阶段','level':'液位','waterlogged':'含水','shape':'形状','type':'类型','part':'部件','occupied':'占用','persistent':'持久','distance':'距离','rotation':'旋转','moisture':'湿润度','snowy':'积雪','bites':'食用次数','extended':'伸出','attached':'附着','enabled':'启用','triggered':'触发','in_wall':'嵌墙','north':'北侧','east':'东侧','south':'南侧','west':'西侧','up':'上方','down':'下方','power':'信号强度','layers':'层数','delay':'延迟','mode':'模式','locked':'锁定','conditional':'条件模式','charges':'充能','honey_level':'蜂蜜量','candles':'蜡烛数','eggs':'蛋数','hatch':'孵化阶段','berries':'浆果','bloom':'开花','unstable':'不稳定','disarmed':'解除','instrument':'乐器','note':'音高'}
STATE_VALUES={'true':'是','false':'否','north':'北','south':'南','east':'东','west':'西','up':'上','down':'下','upper':'上半部','lower':'下半部','top':'顶部','bottom':'底部','left':'左','right':'右','head':'头部','foot':'脚部','single':'单体','double':'双层','straight':'直','inner_left':'内左','inner_right':'内右','outer_left':'外左','outer_right':'外右','none':'无','low':'低','tall':'高','side':'侧向','normal':'默认','compare':'比较','subtract':'减法'}


def state_name(condition):
    if isinstance(condition,dict):
        parts=[]
        for key,value in condition.items():
            if key in ('OR','AND') and isinstance(value,list):parts.append((' 或 ' if key=='OR' else ' 且 ').join('('+state_name(v)+')' for v in value))
            else:parts.append(state_name(key+'='+str(value).lower()))
        return '，'.join(parts) or '无条件部件'
    if not condition or condition=='normal':return '默认状态'
    parts=[]
    for term in condition.split(','):
        key,sep,value=term.partition('=')
        parts.append(STATE_KEYS.get(key,key)+'：'+ '|'.join(STATE_VALUES.get(v,v) for v in value.split('|')) if sep else STATE_VALUES.get(term,term))
    return '，'.join(parts)
