"""Chinese annotations for texture-only resources without an item translation key."""
from pathlib import PurePosixPath
from .semantics import translations

NAMES={
 'enchanted_item_glint':'物品附魔光效','enchanted_glint_entity':'实体附魔光效','forcefield':'世界边界',
 'pumpkinblur':'南瓜头视野遮罩','shadow':'实体阴影','underwater':'水下遮罩','unknown_pack':'未知资源包图标',
 'unknown_server':'未知服务器图标','vignette':'视野暗角','credits_vignette':'鸣谢背景暗角',
 'clouds':'云','end_sky':'末地天空','moon_phases':'月相图集','sun':'太阳','rain':'雨','snow':'雪',
 'alex':'艾莉克斯','steve':'史蒂夫','armorstand':'盔甲架','banner':'旗帜','shield':'盾牌',
 'boat':'船','boat_low':'旧版船','chest_boat':'运输船','chest':'箱子','equipment':'穿戴装备',
 'armor':'盔甲','humanoid':'人形盔甲','humanoid_baby':'幼年人形盔甲','humanoid_leggings':'人形护腿',
 'horse_body':'马铠','llama_body':'羊驼装饰','wolf_body':'狼铠','wings':'翅膀','saddle':'鞍',
 'fish':'鱼','tropical_a':'热带鱼 A 型','tropical_b':'热带鱼 B 型','player':'玩家皮肤',
 'wide':'标准手臂','slim':'纤细手臂','villager':'村民','zombie_villager':'僵尸村民',
 'profession':'职业','profession_level':'职业等级','type':'类型','baby':'幼年',
 'normal':'普通','christmas':'圣诞','trapped':'陷阱','left':'左半部','right':'右半部',
 'base':'底图','overlay':'叠加层','top':'顶部','bottom':'底部','side':'侧面','front':'正面','back':'背面',
 'iron':'铁','gold':'金','golden':'金','diamond':'钻石','chainmail':'锁链','leather':'皮革',
 'netherite':'下界合金','copper':'铜','layer':'贴图层','eyes':'眼睛','angry':'愤怒','tame':'驯服',
 'all_black':'全黑','black':'黑色','blue':'蓝色','brown':'棕色','cyan':'青色','gray':'灰色',
 'green':'绿色','light_blue':'淡蓝色','light_gray':'淡灰色','lime':'黄绿色','magenta':'品红色',
 'orange':'橙色','pink':'粉红色','purple':'紫色','red':'红色','white':'白色','yellow':'黄色',
 'border':'方框边','bricks':'砖纹','circle':'圆形','cross':'斜十字','curly_border':'锯齿边',
 'gradient':'渐变','gradient_up':'向上渐变','rhombus':'菱形','skull':'头颅','flower':'花朵',
 'globe':'地球','mojang':'Mojang 标志','piglin':'猪灵','flow':'涡流','guster':'旋风',
 'stripe_bottom':'底横条','stripe_top':'顶横条','stripe_left':'左竖条','stripe_right':'右竖条',
 'stripe_center':'中竖条','stripe_middle':'中横条','stripe_downleft':'左斜条','stripe_downright':'右斜条',
 'stripes_small':'竖条纹','half_horizontal':'上半部','half_horizontal_bottom':'下半部',
 'half_vertical':'左半部','half_vertical_right':'右半部','triangle_bottom':'底三角','triangle_top':'顶三角',
 'triangles_bottom':'底锯齿','triangles_top':'顶锯齿','square_bottom_left':'左下角方块',
 'square_bottom_right':'右下角方块','square_top_left':'左上角方块','square_top_right':'右上角方块',
 'diagonal_left':'左斜半部','diagonal_right':'右斜半部','diagonal_up_left':'左上斜半部','diagonal_up_right':'右上斜半部',
 'full_moon':'满月','new_moon':'新月','waning_crescent':'残月','waxing_crescent':'峨眉月',
 'first_quarter':'上弦月','last_quarter':'下弦月','waning_gibbous':'亏凸月','waxing_gibbous':'盈凸月',
 'celestial':'天体','moon':'月亮','note':'音符粒子',
}

def chinese_resource_name(identity,preview,namespace='minecraft'):
    zh,_=translations()
    parts=identity.split('/');labels=[]
    for segment in parts[1:]:
        normalized=segment.removesuffix('_high').removesuffix('_low')
        label=NAMES.get(segment)
        if not label:
            for key in (f'entity.{namespace}.{normalized}',f'block.{namespace}.{normalized}',
                        f'item.{namespace}.{normalized}',f'entity.minecraft.villager.{normalized}'):
                if key in zh:label=zh[key];break
        if not label and '_layer_' in segment:
            material,layer=segment.split('_layer_',1);label=NAMES.get(material,material)+'盔甲 · 第 '+layer+' 层'
        labels.append(label or segment.replace('_',' '))
    kinds={'entity':'实体贴图','models':'模型贴图','misc':'效果贴图','environment':'环境贴图',
           'gui':'界面贴图','particle':'粒子贴图','painting':'画','colormap':'颜色映射'}
    annotation=kinds.get(parts[0],'自定义资源')
    return annotation+' · '+' · '.join(labels or [PurePosixPath(preview).stem])
