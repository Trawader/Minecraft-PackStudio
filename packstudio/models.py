"""Data-driven Java block models and Techne reference geometry.

JSON faces use Minecraft's 0..16 texture coordinates. Techne UVs use the
declared atlas size. Neither parser rewrites any resource pack data.
"""
import json
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from .core import ROOT, safe_path,decode

@dataclass
class Face:
    vertices: list
    texture: str
    uv: tuple = (0,0,1,1)
    rotation: int = 0

def rotate(point,origin,axis,angle):
    v=[point[i]-origin[i] for i in range(3)];a=math.radians(angle);c,s=math.cos(a),math.sin(a)
    i,j={'x':(1,2),'y':(2,0),'z':(0,1)}[axis]
    v[i],v[j]=v[i]*c-v[j]*s,v[i]*s+v[j]*c
    return tuple(v[k]+origin[k] for k in range(3))

def box_faces(lo,hi):
    x,y,z=lo;X,Y,Z=hi
    return {
        'north':[(X,Y,z),(x,Y,z),(x,y,z),(X,y,z)],
        'south':[(x,Y,Z),(X,Y,Z),(X,y,Z),(x,y,Z)],
        'west':[(x,Y,z),(x,Y,Z),(x,y,Z),(x,y,z)],
        'east':[(X,Y,Z),(X,Y,z),(X,y,z),(X,y,Z)],
        'up':[(x,Y,z),(X,Y,z),(X,Y,Z),(x,Y,Z)],
        'down':[(x,y,Z),(X,y,Z),(X,y,z),(x,y,z)]}

def default_uv(side,a,b):
    x,y,z=a;X,Y,Z=b
    return {'down':(x,16-Z,X,16-z),'up':(x,z,X,Z),'north':(16-X,16-Y,16-x,16-y),'south':(x,16-Y,X,16-y),'west':(z,16-Y,Z,16-y),'east':(16-Z,16-Y,16-z,16-y)}[side]

def resource(value,kind='models',namespace='minecraft'):
    ns,name=value.split(':',1) if ':' in value else (namespace,value)
    return safe_path(f'assets/{ns}/{kind}/{name}'+('.json' if kind=='models' else '.png'))

GROUPS={
 'cube':('普通方块','Cubes'),'slab':('台阶','Slabs'),'stairs':('楼梯','Stairs'),
 'anvil':('铁砧','Anvils'),'cauldron':('炼药锅','Cauldrons'),'chest':('箱子','Chests'),
 'plants':('花草与作物','Flowers & crops'),'fence':('栅栏与墙','Fences & walls'),
 'doors':('门与活板门','Doors & trapdoors'),'rail':('轨道','Rails'),'redstone':('红石与机械','Redstone & machinery'),
 'other':('其他方块','Other blocks'),'player':('玩家与人形','Players & humanoids'),
 'passive':('动物','Animals'),'hostile':('敌对生物','Hostile mobs'),'boss':('大型生物','Bosses'),
 'vehicle':('载具与装饰实体','Vehicles & decorations'),'special':('特殊方块','Special blocks'),
 'custom':('物品模型','Item models')}

ANVIL_IDS={'anvil':'anvil_undamaged','anvil_top':'anvil_undamaged','chipped_anvil':'anvil_slightly_damaged','chipped_anvil_top':'anvil_slightly_damaged','damaged_anvil':'anvil_very_damaged','damaged_anvil_top':'anvil_very_damaged'}

def block_group(name,parents=''):
    text=name+' '+parents
    for key,words in [('anvil',['anvil']),('cauldron',['cauldron']),('chest',['chest']),('stairs',['stairs']),('slab',['slab','half_slab']),('doors',['door','trapdoor']),('fence',['fence','wall']),('rail',['rail']),('plants',['cross','flower','sapling','crop','wheat','stem','mushroom','tallgrass','fern','lily','reeds','cactus','vine']),('redstone',['piston','redstone','repeater','comparator','lever','button','pressure_plate','tripwire','hopper'])]:
        if any(w in text for w in words):return key
    return 'cube' if 'cube' in text or not parents else 'other'

ENTITY_NAMES={
 'Steve':'史蒂夫','Steve (Minimal)':'史蒂夫（旧皮肤）','Alex':'艾 Alex','Alex (Minimal)':'Alex（旧皮肤）',
 'Zombie':'僵尸','Zombie Villager':'僵尸村民','Skeleton':'骷髅','Creeper':'苦力怕','Cow':'牛','Pig':'猪','Sheep':'羊','Sheep (Wool)':'羊毛外层','Chicken':'鸡','Wolf':'狼','Ocelot':'豹猫','Rabbit':'兔子','Horse':'马',
 'Bat':'蝙蝠','Blaze':'烈焰人','Dragon':'末影龙','Enderman':'末影人','EnderMite':'末影螨','Ghast':'恶魂','Guardian':'守卫者','Iron Golem':'铁傀儡','Magma Cube':'岩浆怪','Silverfish':'蠹虫','Slime':'史莱姆','SnowMan':'雪傀儡','Spider':'蜘蛛','Squid':'鱿鱼','Villager':'村民','Witch':'女巫','Wither':'凋灵','Shulker':'潜影贝','Shulker Bullet':'潜影弹',
 'Chest':'箱子','Large Chest':'大箱子','Sign':'告示牌','Book':'附魔书','Banner':'旗帜','Armor Stand':'盔甲架','Boat':'船','Minecart':'矿车','Ender Crystal':'末影水晶','Leash Knot':'拴绳结','Cape':'披风','Shield':'盾牌','Elytra':'鞘翅'}

class ModelLibrary:
    def __init__(self,vanilla):
        self.vanilla=vanilla;self.version='1.8.9';self.files={};self.cache={};self.signature=None;self.entries={};self.texture_index={};self.issues=[]
        self.xml={p.stem:p for p in (Path(__file__).parent/'data/models').glob('*.xml')}
        if 'Steve' in self.xml:self.xml['Zombie']=self.xml['Steve']
        if 'Steve (Minimal)' in self.xml:self.xml['Zombie (Legacy)']=self.xml['Steve (Minimal)']
        self.xml['Boat (Legacy)']=Path(__file__).parent/'data/boat_legacy.xml'
        self.update({})
    def get(self,path):
        version='1.8.9' if self.version=='1.7.10' and ('/models/' in path or '/blockstates/' in path) and path.endswith('.json') else self.version
        return self.files.get(path) or self.vanilla.get(version,path)
    def update(self,files,version=None):
        self.version=version or self.version
        signature=(self.version,tuple(sorted((p,data) for p,data in files.items() if '/models/' in p or '/blockstates/' in p or '/items/' in p)))
        self.files=files
        if signature==self.signature:return
        self.signature=signature;self.cache={};self.entries={};self.texture_index={};self.issues=[]
        paths=self.vanilla.paths('1.8.9' if self.version=='1.7.10' else self.version)|set(files)
        for path in sorted(paths):
            if '/models/' not in path or not path.endswith('.json'):continue
            try:
                model=self.resolve(path)
                generated=any('generated' in p or 'handheld' in p for p in model.get('_parents',[])) and 'layer0' in model.get('textures',{})
                if not model.get('elements') and not generated:continue
                # Abstract parent templates remain resolvable, but are not selectable objects.
                if not generated and not any(self.texture(f.get('texture',''),model) for e in model['elements'] for f in e.get('faces',{}).values()):continue
                name=path.split('/models/',1)[1][:-5];category='block' if name.startswith('block/') else 'item'
                group=block_group(name,' '.join(model.get('_parents',[]))) if category=='block' else 'custom'
                self.entries[path]=(category,group,name)
                for element in model.get('elements',[]):
                    for face in element.get('faces',{}).values():
                        texture=self.texture(face.get('texture',''),model)
                        if texture:self.texture_index.setdefault(texture,set()).add(path)
                if generated:
                    for slot in model['textures']:
                        if slot.startswith('layer'):
                            texture=self.texture('#'+slot,model)
                            if texture:self.texture_index.setdefault(texture,set()).add(path)
            except (ValueError,KeyError,TypeError,RecursionError) as e:self.issues.append((path,str(e)))
        for name,path in self.xml.items():
            category='block' if path.parent.name=='Blocks' else 'entity'
            if category=='block':group='chest' if 'Chest' in name else 'special'
            elif path.parent.name in ('Entities','Items') or name in ('Cape','Boat (Legacy)'):group='vehicle'
            elif path.parent.name=='Players' or name in ('Zombie','Zombie Villager','Skeleton'):group='player'
            elif name in ('Dragon','Wither'):group='boss'
            elif name in ('Cow','Pig','Sheep','Sheep (Wool)','Chicken','Wolf','Ocelot','Rabbit','Horse','Bat','Squid','Villager','Iron Golem','SnowMan'):group='passive'
            else:group='hostile'
            self.entries['xml:'+name]=(category,group,ENTITY_NAMES.get(name,name)+' / '+name)
        for slot,title in [('helmet','头盔'),('chestplate','胸甲'),('leggings','护腿'),('boots','靴子'),('all','完整盔甲层')]:
            self.entries['armor:'+slot]=('entity','player','盔甲穿戴 · '+title)
    def resolve(self,path,trail=()):
        if path in self.cache:return self.cache[path]
        if path in trail or len(trail)>40:raise ValueError('Circular or excessive model inheritance')
        data=self.get(path)
        if data is None:
            if path in ('assets/minecraft/models/item/generated.json','assets/minecraft/models/item/handheld.json','assets/minecraft/models/item/handheld_rod.json'):data=b'{"parent":"builtin/generated"}'
            else:raise ValueError(f'Missing parent: {path}')
        own=json.loads(data.decode('utf-8-sig'));parent=own.get('parent');base={}
        if parent and not parent.startswith(('builtin/','minecraft:builtin/')):
            base=self.resolve(resource(parent,namespace=path.split('/')[1]),trail+(path,))
        model={**base,**own};model['textures']={**base.get('textures',{}),**own.get('textures',{})}
        model['_namespace']=path.split('/')[1];model['_parents']=base.get('_parents',[])+([parent] if parent else [])
        self.cache[path]=model;return model
    def texture(self,value,model):
        seen=set()
        while isinstance(value,str) and value.startswith('#'):
            if value in seen:return ''
            seen.add(value);value=model.get('textures',{}).get(value[1:],'')
        if isinstance(value,dict):value=value.get('sprite','')
        if not isinstance(value,str):return ''
        return resource(value,'textures',model['_namespace']) if value else ''
    def identify(self,path,image=None):
        stem=Path(path).stem.lower();lower=path.lower()
        if '/entity/' in lower or '/models/armor/' in lower:
            if '/models/armor/' in lower or '/entity/equipment/humanoid/' in lower or '/entity/equipment/humanoid_leggings/' in lower:
                return 'armor:leggings' if 'layer_2' in stem or '/humanoid_leggings/' in lower else 'armor:all'
            if stem=='boat':return 'xml:Boat (Legacy)'
            if '/entity/boat/' in lower and self.version not in ('26.2','26.3'):return 'xml:Boat'
            if self.version not in ('1.7.10','1.8.9','1.9.4','1.12.2'):
                # Old Techne geometry is not proof of modern UV compatibility.
                from .versions import records
                reference=records('1.8.9').get(path)
                current=records(self.version).get(path)
                if not reference or not current or reference['sha256']!=current['sha256']:return None
            if 'wither_skeleton' in lower:return 'xml:Skeleton'
            special=[('chest/','Large Chest' if 'double' in stem else 'Chest'),('zombie_villager','Zombie Villager'),('zombie','Zombie'),('pigman','Zombie'),('sheep_fur','Sheep (Wool)'),('wither','Wither'),('enderdragon','Dragon'),('endercrystal','Ender Crystal'),('armorstand','Armor Stand'),('iron_golem','Iron Golem'),('snowman','SnowMan'),('magma','Magma Cube'),('slime/magmacube','Magma Cube'),('cat/','Ocelot'),('guardian','Guardian'),('enchanting_table_book','Book'),('lead_knot','Leash Knot'),('banner','Banner'),('horse/','Horse')]
            for key,name in special:
                if key in lower and 'xml:'+name in self.entries:
                    if name=='Zombie' and image is not None and image.height()*2==image.width():return 'xml:Zombie (Legacy)'
                    return 'xml:'+name
            for name in sorted(self.xml,key=len,reverse=True):
                key=name.lower().replace(' ','_')
                if key in lower:
                    if name in ('Steve','Alex') and image is not None and image.height()*2==image.width():return 'xml:'+name+' (Minimal)'
                    return 'xml:'+name
            if '/models/armor/' in lower:return 'xml:Steve'
            return None
        candidates=list(self.texture_index.get(path,()))
        if candidates:
            def score(key):
                name=Path(key).stem
                return (name==stem, sorted(name.split('_'))==sorted(stem.split('_')),name.replace('_undamaged','')==stem, self.entries[key][0]=='block',self.entries[key][1]=='cube',not any(w in name for w in ['inventory','inner','outer','upper','wall','side']),-len(name),name)
            return max(candidates,key=score)
        ns=path.split('/')[1] if path.startswith('assets/') else 'minecraft'
        for kind in ('block','item'):
            direct=resource(f'{kind}/{stem}',namespace=ns)
            if direct in self.entries:return direct
        # Recognize renamed modern anvils using their stable item identifiers.
        for name,target in ANVIL_IDS.items():
            if stem==name:return resource('block/'+target)
        return None
    def from_id(self,identifier):
        ns,name=identifier.split(':',1) if ':' in identifier else ('minecraft',identifier)
        definition=self.get(f'assets/{ns}/items/{safe_path(name)}.json')
        if definition:
            data=json.loads(definition).get('model',{})
            # Dynamic conditions need game state; do not arbitrarily choose a branch.
            if data.get('type') in ('minecraft:model','model'):
                path=resource(data['model'],namespace=ns)
                if path in self.entries:return path
        for kind in ('block','item'):
            path=resource(f'{kind}/{name}',namespace=ns)
            if path in self.entries:return path
        state=self.get(f'assets/{ns}/blockstates/{safe_path(name)}.json')
        if state:
            data=json.loads(state);variants=data.get('variants',{})
            values=list(variants.values())+[p.get('apply',{}) for p in data.get('multipart',[])]
            for value in values:
                value=value[0] if isinstance(value,list) else value
                model=value.get('model','')
                for candidate in (model,'block/'+model):
                    path=resource(candidate,namespace=ns)
                    if path in self.entries:return path
        normalized=name.replace('_',' ').lower()
        if name in ANVIL_IDS:return resource('block/'+ANVIL_IDS[name])
        return next(('xml:'+n for n in self.xml if n.lower()==normalized),None)
    def faces(self,key,selected_path):
        if key.startswith('armor:'):
            slot=key.split(':',1)[1]
            parts={'helmet':{'Head'},'chestplate':{'Body','Right Arm','Left Arm'},'leggings':{'Body','Right Leg','Left Leg'},'boots':{'Right Leg','Left Leg'},'all':{'Head','Body','Right Arm','Left Arm','Right Leg','Left Leg'}}[slot]
            return self.xml_faces('Steve (Minimal)',selected_path,parts)
        if key.startswith('xml:'):return self.xml_faces(key[4:],selected_path)
        model=self.resolve(key);result=[]
        if not model.get('elements') and 'layer0' in model.get('textures',{}):return self.generated_faces(model)
        for element in model.get('elements',[]):
            a,b=element['from'],element['to'];geometry=box_faces(a,b)
            for side,face in element.get('faces',{}).items():
                if side not in geometry:continue
                vertices=geometry[side]
                rotation=element.get('rotation')
                if rotation:
                    origin=rotation.get('origin',[8,8,8])
                    rotations=[(rotation['axis'],rotation['angle'])] if 'axis' in rotation else [(axis,rotation.get(axis,0)) for axis in 'xyz']
                    for axis,angle in rotations:
                        vertices=[rotate(v,origin,axis,angle) for v in vertices]
                        if rotation.get('rescale') and 'axis' in rotation:
                            scale=1/max(.001,math.cos(math.radians(angle)));idx='xyz'.index(axis)
                            vertices=[tuple(origin[i]+(v[i]-origin[i])*(1 if i==idx else scale) for i in range(3)) for v in vertices]
                # Display space has downward Y, like Techne.
                vertices=[(x,-y,z) for x,y,z in vertices]
                uv=face.get('uv',default_uv(side,a,b))
                result.append(Face(vertices,self.texture(face.get('texture',''),model),tuple(v/16 for v in uv),face.get('rotation',0)))
        return result
    def generated_faces(self,model):
        result=[]
        for slot in sorted(k for k in model['textures'] if k.startswith('layer')):
            texture=self.texture('#'+slot,model);z=int(slot[5:])*.02
            result.extend([Face([(0,-16,z),(16,-16,z),(16,0,z),(0,0,z)],texture),Face([(16,-16,z+1),(0,-16,z+1),(0,0,z+1),(16,0,z+1)],texture,(1,0,0,1))])
            data=self.get(texture)
            if not data:continue
            image=decode(data);w,h=image.width(),image.height()
            if max(w,h)>512:continue
            def opaque(x,y):return 0<=x<w and 0<=y<h and image.pixelColor(x,y).alpha()>0
            for y in range(h):
                for x in range(w):
                    if not opaque(x,y):continue
                    a,b=x*16/w,y*16/h-16;A,B=(x+1)*16/w,(y+1)*16/h-16
                    sides=[((-1,0),[(a,b,z),(a,b,z+1),(a,B,z+1),(a,B,z)]),((1,0),[(A,b,z+1),(A,b,z),(A,B,z),(A,B,z+1)]),((0,-1),[(a,b,z),(A,b,z),(A,b,z+1),(a,b,z+1)]),((0,1),[(a,B,z+1),(A,B,z+1),(A,B,z),(a,B,z)])]
                    for (dx,dy),vertices in sides:
                        if not opaque(x+dx,y+dy):result.append(Face(vertices,texture,(x/w,y/h,(x+1)/w,(y+1)/h)))
        return result
    def xml_faces(self,name,selected_path,parts=None):
        root=ET.parse(self.xml[name]);model=root.find('.//Model');tw,th=map(float,model.findtext('TextureSize').split(','));result=[]
        for shape in model.findall('.//Shape'):
            if parts is not None and shape.get('Name') not in parts:continue
            if shape.findtext('Hidden')=='True':continue
            def values(tag,default):return [float(v) for v in shape.findtext(tag,default).split(',')]
            ox,oy,oz=values('Offset','0,0,0');w,h,d=values('Size','0,0,0');pos=values('Position','0,0,0');angles=values('Rotation','0,0,0');u,v=values('TextureOffset','0,0');grow=float(shape.findtext('Scale','0'))
            # Convert cuboid UV layout into our downward-Y display geometry.
            verts=box_faces((ox-grow,oy-grow,oz-grow),(ox+w+grow,oy+h+grow,oz+d+grow))
            rects={'north':(u+d,v+d,u+d+w,v+d+h),'south':(u+2*d+w,v+d,u+2*d+2*w,v+d+h),'west':(u,v+d,u+d,v+d+h),'east':(u+d+w,v+d,u+2*d+w,v+d+h),'down':(u+d,v,u+d+w,v+d),'up':(u+d+w,v+d,u+d+2*w,v)}
            for side,points in verts.items():
                # box_faces is Y-up; flip vertical vertex order for Techne UVs.
                points=[points[i] for i in (3,2,1,0)]
                if shape.findtext('IsMirrored')=='True':points=[(2*ox+w-p[0],p[1],p[2]) for p in points]
                for axis,angle in zip('xyz',angles):
                    if angle:points=[rotate(p,(0,0,0),axis,angle) for p in points]
                points=[tuple(p[i]+pos[i] for i in range(3)) for p in points]
                a,b,c,e=rects[side];result.append(Face(points,selected_path,(a/tw,b/th,c/tw,e/th)))
        return result
