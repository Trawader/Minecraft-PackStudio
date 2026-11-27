"""Regression checks for dockable panels, persistent copies and last-item removal."""
import sys,uuid,hashlib,copy,traceback,os
if '--native' not in sys.argv:os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import Qt,QPoint,QPointF,QEvent
from PySide6.QtGui import QImage,QColor,QMouseEvent
from PySide6.QtTest import QTest
from unittest.mock import patch
from packstudio.core import *
from packstudio.studio import StudioWindow

app=QApplication([]);errors=[]
def report(kind,error,tb):errors.append(str(error));traceback.print_exception(kind,error,tb)
sys.excepthook=report
root=ROOT/'.tmp'/('studio-test-'+uuid.uuid4().hex);root.mkdir()
os.environ['PACKSTUDIO_SETTINGS_FILE']=str(root/'settings.ini')
stone='assets/minecraft/textures/blocks/stone.png';icons='assets/minecraft/textures/gui/icons.png'
image=QImage(16,16,QImage.Format.Format_ARGB32);image.fill(QColor('red'))
original=root/'original.zip';write_zip(original,{stone:png(image),icons:Vanilla().get('1.8.9',icons),'pack.mcmeta':b'{"pack":{"pack_format":1,"description":"original"}}'})
original_hash=hashlib.sha256(original.read_bytes()).hexdigest()
w=StudioWindow(root/'library',drafts=False);w.show();w.reset_layout();app.processEvents()
w.add_pack(original);assert not w.layers and len(w.sources)==1
w.add_to_composition({'origin':w.sources[0].uid,'path':'','kind':'root','name':'original'})
source=w.sources[0];layer=w.layers[0]
assert layer.uid!=source.uid and layer.library_uid==source.uid
assert (root/'library'/(source.uid+'.packstudio')).exists()
def descriptor(layer,path=stone,kind='png',regions=None):
    d={'origin':'stage:'+layer.uid,'path':path,'kind':kind,'name':Path(path).name}
    if regions:d['regions']=regions
    return d
w.edit_descriptor(descriptor(layer));assert w.canvas.tool=='mouse'
before=png(w.canvas.image);old_offset=QPointF(w.canvas.offset)
QTest.mousePress(w.canvas,Qt.MouseButton.LeftButton,pos=QPoint(30,30));QTest.mouseMove(w.canvas,QPoint(60,60));QTest.mouseRelease(w.canvas,Qt.MouseButton.LeftButton,pos=QPoint(60,60))
assert png(w.canvas.image)==before and w.canvas.offset!=old_offset
w.canvas.offset=QPointF(16,16);w.canvas.zoom=12;w.set_tool('pencil');w.set_color(QColor('blue'))
point=QPoint(16+3*12+6,16+2*12+6)
app.sendEvent(w.canvas,QMouseEvent(QEvent.Type.MouseMove,QPointF(point),QPointF(w.canvas.mapToGlobal(point)),Qt.MouseButton.NoButton,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier))
assert w.canvas.hover_pixel==(3,2) and w.preview.highlight[0]==(3,2),(w.canvas.hover_pixel,w.preview.highlight,w.canvas.offset,w.canvas.zoom,w.canvas.tool)
QTest.mousePress(w.canvas,Qt.MouseButton.LeftButton,pos=point)
# Wait for the throttled preview, rather than assuming a fixed 50 ms scheduler slot.
for _ in range(100):
    if w.preview.textures[stone].pixelColor(3,2)==QColor('blue'):break
    QTest.qWait(10)
assert w.preview.textures[stone].pixelColor(3,2)==QColor('blue')
QTest.mouseRelease(w.canvas,Qt.MouseButton.LeftButton,pos=point)
assert decode(layer.files[stone]).pixelColor(3,2)==QColor('blue')
assert decode(source.files[stone]).pixelColor(3,2)==QColor('red')
w.set_tool('eraser');QTest.mouseClick(w.canvas,Qt.MouseButton.LeftButton,pos=point)
assert decode(layer.files[stone]).pixelColor(3,2).alpha()==0
w.canvas.undo();assert decode(layer.files[stone]).pixelColor(3,2)==QColor('blue')
# Atlas component highlighting maps local canvas pixels back into the full texture.
regions=next(regions for name,regions in components(icons) if 'experience_bar_background' in name);w.edit_descriptor(descriptor(layer,icons,'component',regions));w.canvas_hover((2,1))
assert w.preview.highlight[0]==(2,65)
w.model_hover((2,65));assert w.canvas.hover_pixel==(2,1)
w.edit_descriptor(descriptor(layer));w.set_tool('pencil');w.canvas_hover((3,2))
w.grab().save(str(ROOT/'.tmp'/'studio-populated.png'))
# Multiple browser windows share only project bytes; deletion does not alter library data.
w.browse_layer(layer.uid,True);w.browse_layer(layer.uid,True);assert len(w.browsers)==3
w.delete_resource(descriptor(layer,icons,'png'));assert icons not in layer.files and icons in source.files
w.undo_resource();layer=w.layers[0];assert icons in layer.files
# Drag/drop uses stable IDs and updates composition priority, not just visual order.
second=w.clone_layer(layer);second.uid=uuid.uuid4().hex;second.name='Second';w.layers.append(second);w.refresh()
ids=[second.uid,layer.uid];w.apply_order(ids);assert [l.uid for l in w.layers]==ids
assert [w.stack.item(i).data(Qt.ItemDataRole.UserRole) for i in range(w.stack.count())]==ids
w.remove_layers([second.uid]);layer=w.layers[0]
# Remove the LAST ZIP while it is open, with two browser views and a queued selection.
for repeat in range(12):
    if not w.layers:
        clone=w.clone_layer(source);clone.uid=uuid.uuid4().hex;clone.library_uid=source.uid;w.layers=[clone];w.refresh()
    layer=w.layers[0];w.edit_descriptor(descriptor(layer));w.browse_layer(layer.uid,True);w.browse_layer(layer.uid,True)
    w.pending_resource=descriptor(layer);w.selection_timer.start(90)
    w.project_tree.setCurrentItem(w.project_tree.topLevelItem(0));QTest.keyClick(w.project_tree,Qt.Key.Key_Delete);QTest.qWait(120)
    assert not w.layers and w.current is None and w.canvas.image.isNull()
    assert not w.preview.faces and not w.preview.textures and not w.preview.hit_faces
    assert len(w.browsers)==1 and w.project_tree.topLevelItemCount()==0
    assert len(w.sources)==1 and not errors,errors
# All panels float, hide and dock without destroying their data.
for key in w.docks:
    w.set_panel_mode(key,1);app.processEvents();assert w.docks[key].isFloating()
    w.set_panel_mode(key,2);assert w.docks[key].isHidden()
    w.set_panel_mode(key,0);assert not w.docks[key].isFloating()
w.reset_layout()
with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):w.close_project()
assert w.sources and not w.layers
assert hashlib.sha256(original.read_bytes()).hexdigest()==original_hash
w.dirty=False;w.close();app.processEvents()
# Persistent library survives closing the entire application window; no external source read.
original.rename(root/'moved-original.zip')
other=StudioWindow(root/'library',drafts=True);other.show();app.processEvents()
assert len(other.sources)==1 and not other.layers
source=other.sources[0];other.edit_descriptor({'origin':source.uid,'path':stone,'kind':'png','name':'stone.png'})
assert not other.layers and other.current_source==source.uid
assert other.canvas.image.pixelColor(3,2)==QColor('red')
other.add_to_composition({'origin':source.uid,'path':'','kind':'root','name':source.name})
target=root/'project.packstudio';other.write_project(target)
layers,version,sources=load_project(target,include_sources=True);assert layers and sources
other.changed();other.save_draft()
for attempt in range(40):
    QTest.qWait(100);other.check_draft()
    if other.draft_saved_revision==other.draft_revision:break
assert other.draft_path.exists() and load_project(other.draft_path)[0]
other.dirty=False;other.close();app.processEvents()
assert not errors,errors
print('PASS: default mouse, brush/eraser hover + live render, atlas mapping, persistent independent copies, multi-window project browsing, reorder, Delete last ZIP x12, dock modes, project save and draft recovery')
