"""Offscreen regression for explicit selection, drag imports and export metadata."""
import os,sys,json,uuid,zipfile
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QFileDialog
from PySide6.QtCore import Qt,QPoint,QPointF,QMimeData
from PySide6.QtGui import QImage,QColor
from PySide6.QtTest import QTest
from packstudio.core import ROOT,Layer,png,decode,Vanilla
from packstudio.studio import StudioWindow
from packstudio.panels import ASSET_MIME
from packstudio.export_dialog import defaults,prepare_files,ExportDialog,CropView,zip_name

app=QApplication([]);root=ROOT/'.tmp'/('export-ui-'+uuid.uuid4().hex);root.mkdir()
os.environ['PACKSTUDIO_SETTINGS_FILE']=str(root/'settings.ini')
w=StudioWindow(root/'library',drafts=False);w.show();app.processEvents()
image=QImage(16,16,QImage.Format.Format_ARGB32);image.fill(QColor('red'))
path='assets/minecraft/textures/blocks/stone.png'
bottom=Layer('Bottom',{path:png(image),'pack.mcmeta':b'{"pack":{"pack_format":1,"description":"Bottom title\\nBody"},"extra":42}'},source='bottom.zip')
top=Layer('Top',{path:png(image),'pack.png':png(image),'pack.mcmeta':b'{"pack":{"pack_format":1,"description":"Top"}}'},source='top.zip')
w.add_import(bottom);w.add_import(top);assert not w.layers
d={'origin':bottom.uid,'path':'','kind':'root','name':'Bottom'}
item=w.tree_items[w.descriptor_key(d)];w.tree.scrollToItem(item);app.processEvents()
was=item.isExpanded();QTest.mouseClick(w.tree.viewport(),Qt.MouseButton.LeftButton,pos=w.tree.visualItemRect(item).center())
assert item.isExpanded()!=was and not item.isSelected() and not w.layers
menu=w.resource_menu(d);assert not next(a for a in menu.actions() if a.text()=='直接编辑素材').isEnabled();menu.deleteLater()
w.select_asset(d);assert item.isSelected() and w.selected_asset
w.select_asset(d);assert not item.isSelected() and w.selected_asset is None
w.select_asset(d);QTest.keyClick(w.tree,Qt.Key.Key_Escape);assert not item.isSelected() and w.selected_asset is None
file_d={'origin':bottom.uid,'path':path,'kind':'png','name':'stone.png'}
file_item=w.tree_items[w.descriptor_key(file_d)];parent=file_item.parent()
while parent:parent.setExpanded(True);parent=parent.parent()
w.tree.scrollToItem(file_item);app.processEvents()
QTest.mouseClick(w.tree.viewport(),Qt.MouseButton.LeftButton,pos=w.tree.visualItemRect(file_item).center())
assert w.current_source==bottom.uid and not file_item.isSelected() and not w.layers
w.refresh();assert not w.tree.selectedItems()
# Same source is reordered in the library without changing its bytes or resource paths.
w.move_library_asset({'origin':top.uid,'path':'','kind':'root','name':'Top'},d);w.refresh()
assert w.tree.topLevelItem(0).text(0)=='Top'
class Drop:
    accepted=False
    pos=QPointF(10,10)
    def __init__(self):
        self.mime=QMimeData();self.mime.setData(ASSET_MIME,json.dumps({'role':'library','asset':d}).encode())
    def mimeData(self):return self.mime
    def position(self):return self.pos
    def source(self):return w.tree
    def setDropAction(self,action):self.action=action
    def accept(self):self.accepted=True
    def acceptProposedAction(self):self.accepted=True
    def ignore(self):self.accepted=False
event=Drop();w.project_tree.dropEvent(event);app.processEvents()
assert event.accepted and len(w.layers)==1 and w.layers[0].library_uid==bottom.uid
assert w.layers[0].files is not bottom.files
first=w.layers[0].uid;event.pos=QPointF(10,w.project_tree.viewport().height()-1)
w.project_tree.dragMoveEvent(event);assert w.project_tree.drop_line is not None
w.project_tree.dropEvent(event);app.processEvents()
assert w.project_tree.drop_line is None and len(w.layers)==2 and w.layers[0].uid==first
w.project_tree.dragMoveEvent(event);w.project_tree.dragLeaveEvent(event);assert w.project_tree.drop_line is None
# Bottom-up independent fallbacks and metadata preservation.
w.layers=[top,bottom];base=defaults(w.layers)
assert base['title']=='Bottom title' and base['body']=='Body' and base['filename']=='bottom' and base['cover']==top.files['pack.png']
out=prepare_files(w.layers,w.vanilla,'1.8.9',base,'unchanged',base['title'],base['body'],base['cover'])
assert out['pack.mcmeta']==bottom.files['pack.mcmeta']
out=prepare_files(w.layers,w.vanilla,'1.8.9',base,'1.7.10','§aTitle','§bBody',base['cover'])
meta=json.loads(out['pack.mcmeta']);assert meta['extra']==42 and meta['pack']['description']=='§aTitle\n§bBody'
# Crop is always square; tiny selections scale with nearest-neighbour pixels.
small=QImage(3,5,QImage.Format.Format_ARGB32);small.fill(QColor('blue'));view=CropView(small)
assert view.cropped().size().width()==8 and view.cropped().size().height()==8
view=CropView(image);view.set_side(10);view.move_crop(QPointF(view.width()-1,view.height()-1));assert view.x==6 and view.y==6 and view.cropped().width()==10
from packstudio.core import VERSIONS
dialog=ExportDialog(w);assert dialog.version.currentIndex()==-1 and dialog.version.count()==len(VERSIONS)+1
assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Save).isEnabled()
dialog.version.setCurrentIndex(dialog.version.findData('unchanged'));dialog.filename.setText('§aExport');dialog.title.setText('Title');dialog.body.setPlainText('Body')
dialog.insert_code(dialog.title,'c');assert '§c' in dialog.title.text()
with patch.object(QFileDialog,'getExistingDirectory',return_value=str(root)):dialog.save()
assert (root/'§aExport.zip').exists()
with zipfile.ZipFile(root/'§aExport.zip') as z:
    assert '§c' in json.loads(z.read('pack.mcmeta'))['pack']['description'];assert z.read('pack.png')==top.files['pack.png']
for name in ('../bad','CON','bad.','bad/name'):
    try:zip_name(name);raise AssertionError(name)
    except ValueError:pass
w.dirty=False;w.close();print('PASS: explicit selection, folder/PNG activation, library order, drag shadow, bottom-up metadata, crop, version placeholder and exported ZIP')
