import os,sys,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QToolBar
from PySide6.QtGui import QImage,QColor
from packstudio.core import Layer,Vanilla,png,decode
from packstudio.export_dialog import defaults,prepare_files
from packstudio.original_export import target_version
from packstudio.layouts import confirm_layout
from packstudio.studio import StudioWindow
app=QApplication([]);vanilla=Vanilla();icons='assets/minecraft/textures/gui/icons.png'
def export(layers):
 base=defaults(layers)
 return prepare_files(layers,vanilla,'1.21.11',base,'unchanged',base['title'],base['body'],base['cover'],'vanilla')
def meta(fmt):return json.dumps({'pack':{'pack_format':fmt,'description':'test'}}).encode()
low=Layer('low',{icons:vanilla.get('1.8.9',icons)},source_version='1.8.9');confirm_layout(low,icons,'1.8.9')
stone='assets/minecraft/textures/block/stone.png'
high=Layer('high',{stone:vanilla.get('1.21.11',stone),'pack.mcmeta':meta(75)},source_version='1.21.11')
assert target_version([low,high])=='1.21.11'
out=export([low,high]);assert icons not in out and 'assets/minecraft/textures/gui/sprites/hud/crosshair.png' in out
assert json.loads(out['pack.mcmeta'])['pack']['pack_format']==75
# Modern evidence overrides a stale legacy declaration in the base pack.
mace='assets/minecraft/textures/item/mace.png'
stale=Layer('stale',{mace:vanilla.get('1.21.11',mace),'pack.mcmeta':meta(1)})
assert target_version([stale]) not in ('1.7.10','1.8.9')
# Unknown base must not borrow the working version for a legacy component.
im=QImage(15,15,QImage.Format.Format_ARGB32);im.fill(QColor('magenta'))
part=Layer('crosshair',{'0':png(im)},'component',icons,[(0,0,15/256,15/256)],source_version='1.8.9')
unknown=Layer('unknown',{'assets/example/custom.txt':b'x'})
assert target_version([part,unknown]) is None
out=export([part,unknown]);result=decode(out[icons]);original=decode(vanilla.get('1.8.9',icons))
assert result.pixelColor(1,1)==QColor('magenta')
assert result.copy(20,0,236,256)==original.copy(20,0,236,256)
assert 'assets/minecraft/textures/gui/sprites/hud/crosshair.png' not in out
# High-version standalone sprites remain standalone.
sprite='assets/minecraft/textures/particle/heart.png'
modern=Layer('modern',{sprite:vanilla.get('1.21.11',sprite)},kind='png',source_version='1.21.11')
assert export([modern])==modern.files
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='rulers-') as tmp:
 os.environ['PACKSTUDIO_SETTINGS_FILE']=str(Path(tmp)/'settings.ini')
 w=StudioWindow(Path(tmp)/'library',drafts=False)
 assert not w.findChildren(QToolBar)
 w.rulers_toggle.setChecked(True);assert w.canvas.show_rulers
 w.canvas.set_image(im);w.canvas.grab();w.dirty=False;w.close()
 w=StudioWindow(Path(tmp)/'library',drafts=False);assert w.canvas.show_rulers;w.dirty=False;w.close()
print('PASS base-version adaptation, modern evidence, original legacy component completion, standalone sprites, no sidebar, persistent rulers')
