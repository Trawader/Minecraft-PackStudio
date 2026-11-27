import os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from packstudio.studio import StudioWindow
from packstudio.core import Layer
from packstudio.semantics import describe
app=QApplication([])
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='browser-layout-') as directory:
 os.environ['PACKSTUDIO_SETTINGS_FILE']=str(Path(directory)/'settings.ini')
 w=StudioWindow(Path(directory)/'library',drafts=False);w.resize(1280,900);w.show();app.processEvents()
 assert describe('assets/minecraft/textures/particle/footprint.png')['name'].startswith('脚印')
 assert '足迹' in describe('assets/minecraft/textures/particle/footprint.png')['search']
 files={}
 for p in w.vanilla.paths('1.8.9'):
  if '/particle/' in p or '/gui/title/' in p or p.endswith('/gui/options_background.png'):files[p]=w.vanilla.get('1.8.9',p)
 for name in ['heart','angry','glint','effect_0','effect_1']:
  path='assets/minecraft/textures/particle/'+name+'.png';files[path]=w.vanilla.get('1.21.11',path)
 files={p:raw for p,raw in files.items() if raw};source=Layer('mixed',files,source_version='1.8.9');w.sources=[source];w.library_mode.setCurrentIndex(1);w.refresh()
 subsets=w.tree.topLevelItem(1);particle=next(subsets.child(i) for i in range(subsets.childCount()) if subsets.child(i).text(0).startswith('粒子'))
 root=particle.child(0)
 assert all(root.child(i).data(0,Qt.ItemDataRole.UserRole)['kind']=='folder' for i in range(root.childCount()))
 assert root.child(root.childCount()-1).text(0).startswith('完整图集')
 backgrounds=[];todo=[subsets]
 while todo:
  item=todo.pop()
  for i in range(item.childCount()):
   child=item.child(i);todo.append(child)
   if child.text(0).startswith('背景与光影'):
    backgrounds.append(child);assert not child.isExpanded();assert i==item.childCount()-1
 assert backgrounds
 # Complete packs and subsets share categories without mixing same-named packs.
 source.files['pack.mcmeta']=b'{"pack":{"pack_format":1,"description":"test"}}'
 other=Layer('mixed',{'pack.mcmeta':source.files['pack.mcmeta'],
  'assets/minecraft/textures/particle/heart.png':next(iter(files.values()))},source_version='1.8.9')
 w.sources.append(other);w.refresh()
 from packstudio.browser_icons import COLOR_ROLE,shulker_icon,RAINBOW
 packs=w.tree.topLevelItem(0)
 assert packs.childCount()==2
 for i in range(2):
  pack=packs.child(i);assert pack.data(0,COLOR_ROLE)=='purple'
  assert pack.child(0).data(0,COLOR_ROLE)=='red'
  origin=pack.data(0,Qt.ItemDataRole.UserRole)['origin'];todo=[pack]
  while todo:
   item=todo.pop();d=item.data(0,Qt.ItemDataRole.UserRole) or {}
   assert d.get('origin') in (origin,'@category')
   todo.extend(item.child(j) for j in range(item.childCount()))
 assert len({shulker_icon(w,color).pixmap(32,32).toImage().pixelColor(16,8).rgba() for color in RAINBOW})==7
 # Rebuild repeatedly: stale Qt tree references must not survive in descriptors.
 for _ in range(3):w.refresh();app.processEvents()
 # Sticky parent remains clickable after scrolling deeply into a long source.
 w.library_mode.setCurrentIndex(0);w.defaults.setChecked(True);w.tree.expandAll();app.processEvents()
 w.tree.verticalScrollBar().setValue(w.tree.verticalScrollBar().maximum()//2);app.processEvents();w.tree.update_sticky()
 assert w.tree.sticky_parent.isVisible() and w.tree.sticky_index.isValid()
 parent=w.tree.itemFromIndex(w.tree.sticky_index);w.tree.sticky_parent.click();assert not parent.isExpanded()
 w.tree.clear();w.tree.update_sticky();assert not w.tree.sticky_parent.isVisible()
 w.dirty=False;w.close()
print('PASS naming, particle hierarchy, collapsed backgrounds, same-name pack isolation, rainbow shulkers, repeated refresh, sticky collapse')
