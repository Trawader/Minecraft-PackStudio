"""Regression checks for stable tree interaction and separate source/composition data."""
import sys,copy,json,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QImage,QColor
from PySide6.QtTest import QTest
from unittest.mock import patch
from packstudio.workspace import WorkspaceWindow
from packstudio.core import *

app=QApplication([]);window=WorkspaceWindow();window.resize(1500,950);window.show();app.processEvents()
errors=[]
def exception(kind,error,tb):errors.append(str(error))
sys.excepthook=exception
def image(color):
    im=QImage(16,16,QImage.Format.Format_ARGB32);im.fill(QColor(color));return png(im)
stone='assets/minecraft/textures/blocks/stone.png'
icons='assets/minecraft/textures/gui/icons.png'
a=Layer('Same pack',{stone:image('red'),icons:Vanilla().get('1.8.9',icons),'assets/custom/readme.txt':b'keep'},source='C:/samples/one/Same pack.zip')
b=Layer('Same pack',{stone:image('blue'),icons:Vanilla().get('1.8.9',icons)},source='C:/samples/two/Same pack.zip')
window.sources=[a,b];window.refresh()
def desc(source,path='',kind='root',regions=None):
    d={'origin':source.uid,'path':path,'kind':kind,'name':Path(path).name if path else source.name}
    if regions:d['regions']=regions
    return d
da=desc(a,stone,'png');db=desc(b,stone,'png');folder=desc(a,'assets/minecraft/textures','folder')
assert not window.layers and len(window.sources)==2
assert 'from C:/samples/one' in window.tree.topLevelItem(0).text(0)
assert 'from C:/samples/two' in window.tree.topLevelItem(1).text(0)
# Genuine mouse sequences: native double-click expansion and non-blocking context menus.
for loop in range(12):
    root=window.tree.topLevelItem(0) if loop%2==0 else window.tree_items[window.descriptor_key(folder)]
    parent=root.parent()
    while parent:parent.setExpanded(True);parent=parent.parent()
    window.tree.scrollToItem(root);app.processEvents();rect=window.tree.visualItemRect(root)
    QTest.mouseDClick(window.tree.viewport(),Qt.MouseButton.LeftButton,pos=rect.center());app.processEvents()
    QTest.mouseClick(window.tree.viewport(),Qt.MouseButton.RightButton,pos=rect.center());app.processEvents()
    window.show_resource_menu(rect.center());app.processEvents()
    if window.context_popup:window.context_popup.close()
    app.processEvents()
    window.refresh()
assert not errors,errors
window.edit_descriptor(da);assert window.canvas.image.pixelColor(0,0)==QColor('red')
window.edit_descriptor(db);assert window.canvas.image.pixelColor(0,0)==QColor('blue')
# Bad image input must not leave the previous canvas bound to a new target path.
bad='assets/minecraft/textures/blocks/broken.png';b.files[bad]=b'not a png'
try:window.edit_descriptor(desc(b,bad,'png'))
except ValueError:pass
else:raise AssertionError('Invalid image was accepted')
assert window.current is None and window.canvas.image.isNull()
b.files.pop(bad);window.edit_descriptor(db)
# Menu actions remain valid if the tree is rebuilt while a menu exists.
menu=window.resource_menu(da);window.refresh();menu.actions()[2].trigger()
assert window.selected_asset['files'][stone]==a.files[stone];menu.deleteLater()
for n in range(8):
    before=window.canvas.image.copy();current=window.current;zoom=window.canvas.zoom
    window.tabs.setCurrentIndex(n%2);app.processEvents()
    assert window.canvas.image==before and window.current==current and window.canvas.zoom==zoom
window.add_to_composition(da);window.add_to_composition(db)
assert len(window.layers)==2 and decode(window.result()[0][stone]).pixelColor(0,0)==QColor('blue')
assert '(from C:/samples/two/' in window.layers[0].name
# Source edits stay isolated from snapshots already staged.
window.edit_descriptor(db);window.canvas.image.setPixelColor(0,0,QColor('green'));window.commit_canvas()
assert decode(b.files[stone]).pixelColor(0,0)==QColor('green')
assert decode(window.result()[0][stone]).pixelColor(0,0)==QColor('blue')
window.select_asset(da);window.replace_with_selected(db)
assert decode(b.files[stone]).pixelColor(0,0)==QColor('red')
window.delete_resource(db);assert stone not in b.files
window.undo_resource();b=window.source(b.uid);assert stone in b.files
# Folder selection/remapping, PNG/component copy and source-only deletion.
window.select_asset(folder)
destination=desc(b,'assets/minecraft/textures','folder');window.replace_with_selected(destination)
assert b.files['assets/minecraft/textures/blocks/stone.png']==a.files[stone]
window.add_to_composition(folder)
assert all(p.startswith('assets/minecraft/textures/') for p in window.layers[0].files)
region=components(icons)[2][1]
window.add_to_composition(desc(a,icons,'component',region));assert window.layers[0].kind=='component'
# Deleting the entire imported source never removes already staged copies.
count=len(window.layers);window.delete_resource(desc(a));assert len(window.layers)==count
window.undo_resource();a=window.source(a.uid)
# Full selection merge uses visual top-to-bottom priority and preserves non-PNG data.
window.layers=[];window.add_to_composition(desc(a));window.add_to_composition(desc(b))
expected=window.result()[0]
window.stack.selectAll();window.merge_selected();assert window.result()[0]==expected
assert window.result()[0]['assets/custom/readme.txt']==b'keep'
# UUIDs and independent library/stage data survive saved project files.
target=ROOT/'.tmp'/'workspace-verify.packstudio';window.write_project(target)
saved_sources=[s.uid for s in window.sources];saved_layers=[l.uid for l in window.layers]
window.read_project(target);assert [s.uid for s in window.sources]==saved_sources and [l.uid for l in window.layers]==saved_layers
assert window.result()[0]==expected
with zipfile.ZipFile(target) as z:
    manifest=json.loads(z.read('project.json'));assert manifest['schema']==2 and manifest['sources']
# Legacy projects remain readable, retaining layers and independent browsable sources.
legacy=ROOT/'.tmp'/'workspace-legacy.packstudio'
write_zip(legacy,{'project.json':json.dumps({'schema':1,'version':'1.8.9','layers':[{'name':'legacy','kind':'png','target':'','regions':[],'enabled':True,'source':'','files':{stone:'old.png'}}]}).encode(),'old.png':image('yellow')})
layers,version,sources=load_project(legacy,include_sources=True);assert layers[0].files==sources[0].files and layers[0].uid!=sources[0].uid
assert not errors,errors
window.edit_descriptor(desc(window.sources[0],stone,'png'));window.tabs.setCurrentIndex(1);app.processEvents()
window.grab().save(str(ROOT/'.tmp'/'workspace-compose.png'))
window.tabs.setCurrentIndex(0);app.processEvents();window.grab().save(str(ROOT/'.tmp'/'workspace-preview.png'))
# Real reference packs: keep duplicate logical paths separate and browse without staging.
window.layers=[];window.sources=[];window.clear_editor();window.refresh()
for pattern in ('*Tsuki*.zip','! *Lemonade*.zip'):
    pack=next((ROOT/'reference').glob(pattern));window.add_pack(str(pack))
assert len(window.sources)==2 and not window.layers
for source in window.sources:
    d=desc(source,icons,'png');window.edit_descriptor(d)
    assert png(window.canvas.image)==png(decode(source.files[icons]))
    item=window.tree_items[window.descriptor_key(d)]
    parent=item.parent()
    while parent:parent.setExpanded(True);parent=parent.parent()
    window.tree.scrollToItem(item);app.processEvents();rect=window.tree.visualItemRect(item)
    for i in range(4):
        QTest.mouseDClick(window.tree.viewport(),Qt.MouseButton.LeftButton,pos=rect.center());QTest.qWait(100)
        window.show_resource_menu(rect.center());app.processEvents()
        window.context_popup.close();app.processEvents()
    window.add_to_composition(d)
assert not errors,errors
assert len(window.layers)==2
window.dirty=False;window.close()
print('PASS: repeated double-click/right-click, source isolation, replace/delete/undo, folder/component staging, merge precedence, shared canvas, project persistence and legacy migration')
