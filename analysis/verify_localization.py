"""Language switching must change presentation, never resource identities or edits."""
import os,sys,json,tempfile,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QLabel,QAbstractButton,QLineEdit,QStyleOptionViewItem
from PySide6.QtGui import QColor,QAction,QFontDatabase,QFont
from PySide6.QtCore import Qt
from packstudio.core import import_pack
from packstudio.studio import StudioWindow
from packstudio.localization import text,item_text,CJK,NameDelegate
from packstudio.color_editor import ColorEditor
from packstudio.export_dialog import ExportDialog
from packstudio.selector_taxonomy import chinese_name,english_name
from packstudio.game_objects import entries
app=QApplication([])
for font in ('segoeui.ttf','msyh.ttc'):
 p=Path('C:/Windows/Fonts')/font
 if p.exists():QFontDatabase.addApplicationFont(str(p))
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='language-check-') as tmp:
 os.environ['PACKSTUDIO_SETTINGS_FILE']=tmp+'/settings.ini';os.environ['PACKSTUDIO_NAMING_FILE']=tmp+'/names.json'
 w=StudioWindow(Path(tmp)/'library',drafts=False);w.setFont(QFont('Segoe UI',9))
 try:
  source=import_pack(ROOT/'test/b1ue 128x.zip');source.source_version='1.8.9';source.name='我的材质包 方块'
  w.sources=[source];w.refresh();w.library_mode.setCurrentIndex(1)
  original_files=dict(source.files);original_rows=copy.deepcopy(entries(source,'1.8.9'))
  node=next(node for node in w.tree_items.values() if (node.data(0,Qt.ItemDataRole.UserRole) or {}).get('object_id','').endswith(':item/diamond_sword'))
  descriptor=node.data(0,Qt.ItemDataRole.UserRole);w.edit_descriptor(descriptor)
  w.canvas.selection_region=w.canvas.selection_region.united(w.canvas.image.rect()) if False else w.canvas.selection_region
  state=(w.current,dict(w.tree_items),w.model_key,w.dirty)
  w.language_actions[1].trigger();w.show();app.processEvents()
  assert w.lang=='en' and w.language_combo.currentIndex()==1 and w.language_actions[1].isChecked()
  assert w.docks['library'].windowTitle()=='Asset library' and w.window_menu.title()=='Window'
  assert w.library_mode.itemText(1)=='Selector' and w.selector_source.currentText()==source.name
  assert isinstance(w.tree.itemDelegate(),NameDelegate)
  assert item_text(node.text(0),'en',descriptor)=='Diamond Sword'
  assert (w.current,dict(w.tree_items),w.model_key,w.dirty)==state
  assert source.files==original_files and entries(source,'1.8.9')==original_rows
  remaining=[]
  for node in w.tree_items.values():
   value=item_text(node.text(0),'en',node.data(0,Qt.ItemDataRole.UserRole))
   if CJK.search(value):remaining.append(value)
  assert not remaining,remaining
  assert item_text(source.name,'en',{'kind':'root','origin':source.uid,'path':''})==source.name
  path='assets/minecraft/textures/items/diamond_sword.png'
  assert item_text('diamond_sword.png','en',{'kind':'png','path':path})=='diamond_sword.png'
  assert '盔甲' in chinese_name('models/armor/iron_layer_1','assets/minecraft/textures/models/armor/iron_layer_1.png')
  assert '云' in chinese_name('environment/clouds','assets/minecraft/textures/environment/clouds.png')
  assert english_name('minecraft:item/diamond_sword',path)=='Diamond Sword'
  for dialog in (ColorEditor(QColor('red'),w),ExportDialog(w)):
   dialog.show();app.processEvents()
   assert not CJK.search(dialog.windowTitle()),dialog.windowTitle()
   for widget in dialog.findChildren(QLabel)+dialog.findChildren(QAbstractButton):
    assert not CJK.search(widget.text()),widget.text()
   dialog.hide()
  # User-entered text and raw source configuration must never be translated.
  edit=QLineEdit(w);edit.setText('方块 我的文件');w.resource_rules.raw.setPlainText('{"name":"方块"}')
  w.language_actions[0].trigger();app.processEvents()
  assert w.docks['library'].windowTitle()=='素材库' and w.library_mode.itemText(1)=='选择器'
  assert edit.text()=='方块 我的文件' and w.resource_rules.raw.toPlainText()=='{"name":"方块"}'
  assert w.selector_source.currentText()==source.name
  w.language_combo.setCurrentIndex(1);app.processEvents()
  assert w.lang=='en' and w.language_actions[1].isChecked()
  w.grab().save(str(ROOT/'.tmp/v3-language-check.png'))
 finally:w.dirty=False;w.close();app.processEvents()
 # Persisted English startup and reverse switching on newly constructed controls.
 w=StudioWindow(Path(tmp)/'library2',drafts=False)
 try:
  assert w.lang=='en' and w.docks['library'].windowTitle()=='Asset library'
  w.language_changed(0);assert w.docks['library'].windowTitle()=='素材库'
  assert w.resource_rules.dock.windowTitle()=='材质规则与原始配置'
 finally:w.dirty=False;w.close();app.processEvents()
print('PASS globe/settings synchronization, persistent language, panels/dialogs, selector English, Chinese resource annotations, paths/user text/source preservation')
