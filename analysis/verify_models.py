"""Model parsing, identification and export-preservation checks."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter,QColor,QFont
from packstudio.core import *
from packstudio.models import ModelLibrary
from packstudio.preview import Preview

app=QApplication([]);vanilla=Vanilla();library=ModelLibrary(vanilla)
for key in library.entries:
    assert library.faces(key,'assets/minecraft/textures/entity/steve.png'),key
for damage,model in [(0,'undamaged'),(1,'slightly_damaged'),(2,'very_damaged')]:
    assert library.identify(f'assets/minecraft/textures/blocks/anvil_top_damaged_{damage}.png').endswith(f'anvil_{model}.json')
assert library.from_id('minecraft:anvil').endswith('anvil_undamaged.json')
assert library.identify('assets/minecraft/textures/blocks/planks_oak.png').endswith('oak_planks.json')
assert library.identify('assets/minecraft/textures/entity/zombie/zombie_villager.png')=='xml:Zombie Villager'
assert library.identify('assets/minecraft/textures/entity/chest/normal_double.png')=='xml:Large Chest'
meta=b'{"pack":{"pack_format":46,"description":"Keep original"},"custom":{"keep":true}}'
pack=Layer('modern',{'pack.mcmeta':meta,'assets/example/models/block/custom.json':b'{}','unknown.bin':b'abc'})
assert newer_pack_sources([pack])==[('modern',46)]
target=ROOT/'.tmp'/'unchanged-verify.zip';export_pack(target,pack.files,'unchanged','ignored')
assert import_pack(target).files==pack.files
plain=ROOT/'.tmp'/'unchanged-no-meta.zip';export_pack(plain,{'x.txt':b'x'},'unchanged','ignored');assert 'pack.mcmeta' not in import_pack(plain).files
# Custom parent inheritance, non-Minecraft namespace and selected model override.
custom='assets/test/models/block/custom.json'
files={custom:json.dumps({'parent':'minecraft:block/stone','textures':{'all':'test:block/custom'}}).encode()}
library.update(files);assert library.identify('assets/test/textures/block/custom.png')==custom
assert all(f.texture=='assets/test/textures/block/custom.png' for f in library.faces(custom,''))
library.update({})
cases=[('Anvil','block/anvil_very_damaged','blocks/anvil_top_damaged_2'),('Cauldron','block/cauldron_empty','blocks/cauldron_side'),('Stairs','block/stone_stairs','blocks/cobblestone'),('Slab','block/half_slab_stone','blocks/stone_slab_top'),('Flower','block/poppy','blocks/flower_rose'),('Chest','xml:Chest','entity/chest/normal'),('Cow','xml:Cow','entity/cow/cow'),('Creeper','xml:Creeper','entity/creeper/creeper'),('Horse','xml:Horse','entity/horse/horse_brown'),('Dragon','xml:Dragon','entity/enderdragon/dragon'),('Player','xml:Steve','entity/steve'),('Villager','xml:Villager','entity/villager/villager')]
sheet=QImage(1200,1200,QImage.Format.Format_ARGB32);sheet.fill(QColor('#eeeeee'));painter=QPainter(sheet);painter.setFont(QFont('Segoe UI',12));view=Preview();view.resize(300,260)
for i,(name,key,tex) in enumerate(cases):
    key=key if key.startswith('xml:') else 'assets/minecraft/models/'+key+'.json';tex='assets/minecraft/textures/'+tex+'.png'
    data=vanilla.get('1.8.9',tex)
    assert data,(name,tex)
    view.set_model(library.faces(key,tex),lambda p:vanilla.get('1.8.9',p),tex,decode(data))
    assert not view.missing,(name,view.missing)
    x=(i%4)*300;y=(i//4)*400;painter.drawText(x+10,y+24,name);painter.drawPixmap(x,y+40,view.grab())
painter.end();sheet.save(str(ROOT/'.tmp'/'models-contact.png'))
print(f'PASS: {len(library.entries)} models parsed, anvil damage IDs, custom inheritance, unchanged export and 12 preview renders')

