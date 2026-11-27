"""Offscreen checks for sidebar, library search and swatch interactions."""
import os,sys,uuid
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor,QImage
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from packstudio.studio import StudioWindow
from packstudio.core import ROOT,Layer,png

root=ROOT/'.tmp'/('appearance-'+uuid.uuid4().hex);root.mkdir()
os.environ['PACKSTUDIO_SETTINGS_FILE']=str(root/'settings.ini')
app=QApplication([]);w=StudioWindow(root/'library',drafts=False);w.show();app.processEvents()
im=QImage(16,16,QImage.Format.Format_ARGB32);im.fill(QColor('red'))
w.sources=[Layer('Example pack',{'assets/minecraft/textures/blocks/stone.png':png(im),'assets/minecraft/textures/blocks/dirt.png':png(im)})]
w.refresh();w.search.setText('stone');app.processEvents()
assert set(w.docks)=={'library','project','editor','render'}
assert w.docks['project'].isAncestorOf(w.project_tree)
assert not w.stack.isVisible()
assert not w.version.isVisible()
w.docks['project'].hide();w.switch_mode(1);assert not w.docks['project'].isHidden()
w.layers=[Layer('First',dict(w.sources[0].files)),Layer('Second',dict(w.sources[0].files))];w.refresh()
w.project_tree.setCurrentItem(w.project_tree.topLevelItem(1))
assert [i.data(Qt.ItemDataRole.UserRole) for i in w.stack.selectedItems()]==[w.layers[1].uid]
w.project_tree.clearSelection();w.select_asset(w.project_tree.topLevelItem(0).data(0,Qt.ItemDataRole.UserRole))
assert w.project_tree.selectedItems()==[w.project_tree.topLevelItem(0)]
w.apply_order([w.layers[1].uid,w.layers[0].uid])
assert w.project_tree.topLevelItem(0).text(0)=='Second'
menu=w.resource_menu(w.project_tree.topLevelItem(0).data(0,Qt.ItemDataRole.UserRole))
assert not any('合成台' in action.text() for action in menu.actions())
menu.deleteLater()
items=[i for i in w.tree_items.values() if (i.data(0,Qt.ItemDataRole.UserRole) or {}).get('kind')=='png']
assert {i.text(0) for i in items if not i.isHidden()}=={'stone.png'}
w.search.clear();assert all(not i.isHidden() for i in w.tree_items.values())
swatch=w.palette_buttons[2]
with patch('packstudio.color_editor.choose_color',return_value=QColor('#88123456')) as dialog:
    QTest.mouseClick(swatch,Qt.MouseButton.LeftButton);assert not dialog.called
    QTest.mouseClick(swatch,Qt.MouseButton.RightButton);assert dialog.call_count==1
assert swatch.color==QColor('#123456')
QTest.mouseClick(swatch,Qt.MouseButton.LeftButton);assert w.canvas.color==swatch.color
with patch('packstudio.color_editor.choose_color',return_value=QColor()):
    QTest.mouseClick(swatch,Qt.MouseButton.RightButton)
assert swatch.color==QColor('#123456')
assert w.docks['library'].width()<310,w.docks['library'].width()
assert all(not b.icon().isNull() for b in w.tool_buttons.values())
w.grab().save(str(ROOT/'.tmp'/'appearance-preview.png'))
w.dirty=False;w.close()
again=StudioWindow(root/'library',drafts=False)
assert again.palette_buttons[2].color==QColor('#123456')
again.dirty=False;again.close()
print('PASS: unified project panel, selection sync, order, export entry, narrow sidebar, search and persistent swatches')
