"""Focused integration checks; no game or reference-program automation."""
import os
import sys
if '--native' not in sys.argv:
    os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QColor
from PySide6.QtCore import QPoint,Qt
from PySide6.QtTest import QTest
from packstudio.canvas import Canvas
from packstudio.core import *
from packstudio.ui import Window

app=QApplication([])
canvas=Canvas();canvas.resize(400,400);canvas.show()
small=QImage(8,8,QImage.Format.Format_ARGB32);small.fill(QColor('white'));canvas.set_image(small);canvas.color=QColor('red')
assert canvas.tool=='mouse';canvas.set_tool('pencil')
QTest.mouseClick(canvas,Qt.MouseButton.LeftButton,pos=QPoint(22,22));assert canvas.image.pixelColor(0,0)==QColor('red')
canvas.undo();assert canvas.image.pixelColor(0,0)==QColor('white')
canvas.redo();assert canvas.image.pixelColor(0,0)==QColor('red')
canvas.tool='bucket';canvas.color=QColor('blue');QTest.mouseClick(canvas,Qt.MouseButton.LeftButton,pos=QPoint(34,34))
assert canvas.image.pixelColor(7,7)==QColor('blue') and canvas.image.pixelColor(0,0)==QColor('red')
picked=[];canvas.picked.connect(picked.append);canvas.tool='picker';QTest.mouseClick(canvas,Qt.MouseButton.LeftButton,pos=QPoint(22,22));assert picked[0]==QColor('red');canvas.close()
vanilla=Vanilla()
path='assets/minecraft/textures/gui/icons.png'
base=vanilla.get('1.8.9',path)
assert base
image=decode(base)
xp_regions=next(r for name,r in components(path) if 'XP bar' in name)
region=xp_regions[0]
x,y,w,h=pixel_rect(region,image)
patch=QImage(w,h,QImage.Format.Format_ARGB32);patch.fill(QColor('#fe12ab'))
bottom=Layer('bottom',{path:base,'assets/example/untouched.txt':b'keep'})
top=Layer('xp',{'0':png(patch)},'component',path,[region])
result,source=compose([top,bottom],vanilla,'1.8.9')
out=decode(result[path]);assert out.pixelColor(x,y)==QColor('#fe12ab');assert out.pixel(0,0)==image.pixel(0,0)
assert compose([bottom,top],vanilla,'1.8.9')[0][path]==base
patch.fill(QColor(0,0,0,0));top.files['0']=png(patch)
assert decode(compose([top,bottom],vanilla,'1.8.9')[0][path]).pixelColor(x,y).alpha()==0
assert path in compose([top],vanilla,'1.8.9')[0]
tmp=ROOT/'.tmp';tmp.mkdir(exist_ok=True)
save_project(tmp/'verify.packstudio',[top,bottom],'1.8.9');layers,version=load_project(tmp/'verify.packstudio')
assert compose(layers,vanilla,version)[0]==compose([top,bottom],vanilla,version)[0]
export_pack(tmp/'verify.zip',result,'1.8.9','Verify');assert import_pack(tmp/'verify.zip').files['assets/example/untouched.txt']==b'keep'
try:safe_path('../bad')
except ValueError:pass
else:raise AssertionError('Traversal accepted')
window=Window();window.show();app.processEvents()
for name in ('*Tsuki*.zip','! *Lemonade*.zip'):
    pack=next((ROOT/'reference').glob(name));window.add_pack(str(pack));print(pack.name,len(window.layers[0].files))
window.current=(path,xp_regions);window.load_canvas()
window.canvas.checkpoint();window.canvas.image.setPixelColor(0,0,QColor('#123456'));window.commit_canvas()
edited=decode(window.result()[0][path]);ex,ey,_,_=pixel_rect(region,edited)
assert edited.pixelColor(ex,ey)==QColor('#123456')
window.canvas.undo();assert decode(window.result()[0][path]).pixelColor(ex,ey)!=QColor('#123456')
for mode in ('block','player','creeper','none'):
    reference={'block':'assets/minecraft/textures/blocks/stone.png','player':'assets/minecraft/textures/entity/steve.png','creeper':'assets/minecraft/textures/entity/creeper/creeper.png'}
    if mode in reference:window.preview.image=decode(vanilla.get('1.8.9',reference[mode]))
    window.preview.mode=mode;window.preview.grab().save(str(tmp/f'preview-{mode}.png'))
assert window.tabs.count()==2
assert window.tree.topLevelItem(0).text(0)=='assets'
window.search.setText('icons.png');app.processEvents();window.search.clear()
window.current=('assets/minecraft/textures/blocks/stone.png',None);window.load_canvas()
assert window.preview.image==window.canvas.image
window.canvas.image.setPixelColor(0,0,QColor('magenta'));window.commit_canvas()
assert window.preview.image.pixelColor(0,0)==QColor('magenta')
window.preview_action.setChecked(False);assert window.preview_panel.isHidden()
window.preview_action.setChecked(True);assert not window.preview_panel.isHidden()
window.write_project(tmp/'ui-project.packstudio');assert not window.dirty
window.changed();window.write_project(tmp/'ui-copy.packstudio',copy=True)
assert window.dirty and window.project_path==tmp/'ui-project.packstudio'
window.save();assert not window.dirty
window.write_project(tmp/'ui-folder.packproject',folder=True);window.read_project(tmp/'ui-folder.packproject')
assert window.version.currentData()=='' and window.layers
window.current=('assets/minecraft/textures/blocks/stone.png',None);window.load_canvas()
window.tabs.setCurrentIndex(0);app.processEvents();window.grab().save(str(tmp/'editor.png'))
window.language_changed(1);window.language_changed(0)
assert window.version.findData('unchanged')>=0
window.model_id.setText('minecraft:anvil');window.find_model_id()
assert window.model_key.endswith('anvil_undamaged.json')
assert window.preview_category.currentData()=='block' and window.preview_group.currentData()=='anvil'
assert window.preview.faces
from unittest.mock import patch
from PySide6.QtWidgets import QMessageBox,QFileDialog
# Export uses the unified dialog now; ZIP contents are covered by the export suites.
with patch('packstudio.export_dialog.ExportDialog.exec',return_value=0) as dialog:
    window.export();assert dialog.called
window.dirty=False;window.close()
print('PASS: layer precedence, transparent patches, vanilla fallback, project round-trip, export, real pack import, component edit/undo, preview rendering and window construction')
