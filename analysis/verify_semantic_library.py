import os,sys,tempfile,copy
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from packstudio.studio import StudioWindow
from packstudio.core import Layer,decode,png,compose,save_project,load_project
from packstudio.semantics import describe,parts
app=QApplication.instance() or QApplication([])
with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'.tmp',prefix='semantic-check-') as tmp:
 os.environ['PACKSTUDIO_SETTINGS_FILE']=str(Path(tmp)/'settings.ini');os.environ['PACKSTUDIO_NAMING_FILE']=str(Path(tmp)/'names.json')
 w=StudioWindow(library_root=Path(tmp)/'library',drafts=False)
 icons='assets/minecraft/textures/gui/icons.png';stone='assets/minecraft/textures/blocks/stone.png'
 source=Layer('Test pack',{'pack.mcmeta':b'{"pack":{"pack_format":1}}',icons:w.vanilla.get('1.8.9',icons),stone:w.vanilla.get('1.8.9',stone)},source_version='1.8.9')
 w.sources=[source];w.refresh()
 particle_atlas='assets/minecraft/textures/particle/particles.png'
 source.files[particle_atlas]=w.vanilla.get('1.8.9',particle_atlas);w.refresh();w.search.setText('堆肥')
 assert any((i.data(0,Qt.ItemDataRole.UserRole) or {}).get('semantic_id')=='particle/glint' and not i.isHidden() for i in w.tree_items.values())
 w.search.clear()
 assert '石' in describe(stone)['search'];assert describe(stone)['code']==describe(stone.replace('/blocks/','/block/'))['code']
 assert '重锤' in describe('assets/minecraft/textures/item/mace.png')['search']
 assert describe('assets/minecraft/textures/particle/glint.png')['name']=='闪光 / Glint'
 for stem in ('glint','glow'):
  assert all(term in describe('assets/minecraft/textures/particle/'+stem+'.png')['search'] for term in ('发光','闪光'))
 assert '堆肥' in describe('assets/minecraft/textures/particle/glint.png')['search']
 assert '堆肥' not in describe('assets/minecraft/textures/particle/glint.png')['name']
 assert '1.21.11' in describe('assets/minecraft/textures/item/mace.png')['versions'] and '1.8.9' not in describe('assets/minecraft/textures/item/mace.png')['versions']
 w.search.setText('石');item=next(i for i in w.tree_items.values() if (i.data(0,Qt.ItemDataRole.UserRole) or {}).get('path')==stone);assert not item.isHidden()
 w.search.clear();w.library_mode.setCurrentIndex(1)
 assert w.selector_source.currentData()==source.uid and w.tree.topLevelItemCount()>0
 assert any((item.data(0,Qt.ItemDataRole.UserRole) or {}).get('preview_path')==stone for item in w.tree_items.values())
 p=parts(icons,'1.8.9');assert any('poisoned_hardcore' in x['code'] for x in p)
 heart=next(x for x in p if x['code'].endswith('/heart/full'))
 d={'origin':source.uid,'path':icons,'kind':'component','name':heart['name'],'regions':heart['regions']}
 w.edit_descriptor(d);w.canvas.set_pixel((1,1),QColor('magenta'));w.commit_canvas();assert decode(source.files[icons]).pixelColor(53,1)==QColor('magenta')
 w.add_to_composition(d);shadow=w.layers[0];assert shadow.library_uid==source.uid
 d2={**d,'origin':'stage:'+shadow.uid};w.edit_descriptor(d2);w.canvas.image.setPixelColor(1,1,QColor('cyan'));w.commit_canvas();assert decode(source.files[icons]).pixelColor(53,1)==QColor('magenta')
 w.library_mode.setCurrentIndex(0);w.vanilla_version.setCurrentText('1.21.11');w.defaults.setChecked(True)
 # V3's source-first selector no longer exposes the former vanilla group tree;
 # retain the underlying numeric-state identity check independently of layout.
 from packstudio.semantics import animation_family
 frames=['assets/minecraft/textures/particle/explosion_'+str(i)+'.png' for i in (10,2,1,0)]
 assert [Path(p).stem for p in sorted(frames,key=animation_family)][:3]==['explosion_0','explosion_1','explosion_2']
 modern='assets/minecraft/textures/gui/sprites/hud/heart/full.png'
 assert '血量' in describe(modern)['search']
 readonly={'origin':'@vanilla','path':modern,'kind':'png','name':'Heart'}
 w.edit_descriptor(readonly);before=png(w.canvas.image);w.canvas.stroke((0,0),(0,0));w.commit_canvas();assert png(w.canvas.image)==before and w.canvas.read_only
 menu=w.resource_menu(readonly);assert not menu.actions()[0].isEnabled();menu.deleteLater()
 bindings=[{'path':modern,'region':[0,0,1,1]},{'path':modern.replace('full.png','half.png'),'region':[0,0,1,1]}]
 group={**readonly,'kind':'component','bindings':bindings,'regions':[[0,0,1,1]]*2}
 w.edit_descriptor(group);assert w.canvas.read_only and len(w.edit_parts)==2
 w.add_to_composition(group);layer=w.layers[0];assert len(layer.bindings)==2
 w.edit_descriptor({**group,'origin':'stage:'+layer.uid});assert not w.canvas.read_only
 w.canvas.image.setPixelColor(0,0,QColor('red'));w.commit_canvas();assert decode(layer.files['0']).pixelColor(0,0)==QColor('red')
 output,_=compose([layer],w.vanilla,'1.21.11');assert decode(output[modern]).pixelColor(0,0)==QColor('red')
 output,_=compose([layer],w.vanilla,'1.8.9');assert modern in output
 target=Path(tmp)/'test.packstudio';save_project(target,[layer],'1.21.11');loaded,_=load_project(target);assert loaded[0].bindings==bindings
 from packstudio.adaptation import export_composition
 output,_=export_composition([layer],w.vanilla,'1.8.9','1.21.11');assert decode(output[icons]).pixelColor(52,0)==QColor('red')
 # High-resolution patches must enlarge low-resolution atlases, never be reduced.
 from packstudio.core import pixel_rect
 high=copy.deepcopy(shadow);high.files={'0':png(decode(high.files['0']).scaled(36,36))}
 result,_=compose([high],w.vanilla,'1.8.9');assert decode(result[icons]).width()==1024
 result,_=export_composition([high],w.vanilla,'1.21.11','1.8.9');assert decode(result[modern]).width()>=36
 # A low-resolution patch must also preserve an existing high-resolution destination.
 highbase=decode(w.vanilla.get('1.8.9',icons)).scaled(1024,1024)
 result,_=compose([shadow,Layer('HD base',{icons:png(highbase)})],w.vanilla,'1.8.9');assert decode(result[icons]).width()==1024
 w.dirty=False;w.close()
print('PASS semantic identities, Chinese search, source selector, atlas editing, shadow isolation, read-only originals, multi-file groups and cross-version overlay')
