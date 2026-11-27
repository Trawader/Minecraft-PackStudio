import os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from packstudio.studio import StudioWindow
from packstudio.core import Layer,decode
from packstudio.layouts import tag_import
app=QApplication([])
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='source-filter-') as tmp:
 os.environ['PACKSTUDIO_SETTINGS_FILE']=str(Path(tmp)/'settings.ini')
 os.environ['PACKSTUDIO_NAMING_FILE']=str(Path(tmp)/'names.json')
 w=StudioWindow(Path(tmp)/'library',drafts=False)
 path='assets/minecraft/textures/gui/icons.png'
 raw=w.vanilla.get('1.8.9',path)
 low=Layer('low',{path:raw},source_version='1.8.9')
 high=Layer('high',{path:raw},source_version='1.20.1')
 unknown=Layer('unknown',{'custom.png':raw});tag_import(unknown);assert unknown.source_version==''
 w.sources=[low,high,unknown];w.defaults.setChecked(False);w.refresh()
 assert w.vanilla_version.currentData()=='all'
 def visible_origins():
  origins=set();todo=[(w.tree.topLevelItem(i),True) for i in range(w.tree.topLevelItemCount())]
  while todo:
   item,parent_visible=todo.pop();visible=parent_visible and not item.isHidden();d=item.data(0,Qt.ItemDataRole.UserRole) or {}
   if visible and d.get('origin')!='@category':origins.add(d.get('origin'))
   todo.extend((item.child(i),visible) for i in range(item.childCount()))
  return origins
 for mode in [0]:
  w.library_mode.setCurrentIndex(mode)
  w.vanilla_version.setCurrentIndex(0);assert {low.uid,high.uid,unknown.uid}<=visible_origins()
  w.vanilla_version.setCurrentText('1.8.9');assert visible_origins()=={low.uid}
  w.search.setText('icons');assert visible_origins()=={low.uid};w.search.clear()
  w.vanilla_version.setCurrentText('1.20.1');assert visible_origins()=={high.uid}
 # V3 selector shows one complete pack, never standalone unknown resources.
 for source in (low,high):source.files['pack.mcmeta']=b'{"pack":{"pack_format":1,"description":"fixture"}}'
 w.library_mode.setCurrentIndex(1);w.refresh()
 for source in (low,high):
  index=w.selector_source.findData(source.uid);assert index>=0
  w.selector_source.setCurrentIndex(index);assert visible_origins()=={source.uid}
 assert w.selector_source.findData(unknown.uid)<0
 # Built-ins in All versions keep their own origin when previewing or copying.
 w.library_mode.setCurrentIndex(0);w.vanilla_version.setCurrentIndex(0);w.defaults.setChecked(True);w.refresh()
 origins=visible_origins();assert '@vanilla:1.8.9' in origins and '@vanilla:1.21.11' in origins
 modern='assets/minecraft/textures/gui/sprites/hud/heart/full.png'
 d={'origin':'@vanilla:1.21.11','path':modern,'kind':'png','name':'heart'}
 snapshot=w.snapshot(d);assert snapshot['version']=='1.21.11' and snapshot['files'][modern]==w.vanilla.get('1.21.11',modern)
 assert w.is_builtin(d)
 w.vanilla_version.setCurrentText('1.8.9');assert '@vanilla:1.21.11' not in visible_origins()
 assert w.defaults.text()=='显示原版资源'
 w.dirty=False;w.close()
print('PASS All versions, exact source filtering, unknown exclusion, both tree modes, search, built-in origin and copy version')
