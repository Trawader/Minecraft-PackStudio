"""Library editing, independent project shadows and destructive-reference prompts."""
import os,sys,uuid,hashlib
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QImage,QColor
from packstudio.core import ROOT,png,decode,write_zip,load_project
from packstudio.studio import StudioWindow

app=QApplication([])
root=ROOT/'.tmp'/('shadows-'+uuid.uuid4().hex);root.mkdir()
os.environ['PACKSTUDIO_SETTINGS_FILE']=str(root/'settings.ini')
w=StudioWindow(root/'library',drafts=False);w.show();app.processEvents()
stone='assets/minecraft/textures/blocks/stone.png';dirt=stone.replace('stone','dirt')
im=QImage(16,16,QImage.Format.Format_ARGB32);im.fill(QColor('red'))
original=root/'original.zip';write_zip(original,{stone:png(im),dirt:png(im)})
digest=hashlib.sha256(original.read_bytes()).digest()
w.add_pack(original);source=w.sources[0]
def desc(path='',kind='root',origin=None):
    return {'origin':origin or source.uid,'path':path,'kind':kind,'name':Path(path).name or source.name}
assert not w.layers
w.edit_descriptor(desc(stone,'png'));w.canvas.image.setPixelColor(0,0,QColor('blue'));w.commit_canvas()
assert not w.layers and decode(w.library_store.load()[0].files[stone]).pixelColor(0,0)==QColor('blue')
w.add_to_composition(desc());shadow=w.layers[0]
assert shadow.library_uid==source.uid and shadow.files is not source.files
w.edit_descriptor(desc(stone,'png','stage:'+shadow.uid));w.canvas.image.setPixelColor(0,0,QColor('green'));w.commit_canvas()
assert decode(source.files[stone]).pixelColor(0,0)==QColor('blue')
assert decode(shadow.files[stone]).pixelColor(0,0)==QColor('green')
assert not w.stack.isVisible() and w.project_tree.topLevelItemCount()==1
# Cancellation is a true no-op, including current editor and pending project bytes.
with patch.object(QMessageBox,'warning',return_value=QMessageBox.StandardButton.Cancel) as warning:
    w.delete_resource(desc())
    assert warning.called and source in w.sources and shadow in w.layers and w.current_source=='stage:'+shadow.uid
    assert warning.call_args.args[-1]==QMessageBox.StandardButton.Cancel
# Deleting just one library PNG prunes that resource, keeping other project files.
with patch.object(QMessageBox,'warning',return_value=QMessageBox.StandardButton.Yes):w.delete_resource(desc(stone,'png'))
assert stone not in shadow.files and dirt in shadow.files and dirt in source.files
assert stone not in w.library_store.load()[0].files
w.undo_resource();assert stone not in shadow.files
# Real tree order is the export order; child paths never get reparented.
w.add_to_composition(desc());second=w.layers[0];w.project_tree.setCurrentItem(w.project_tree.topLevelItem(0))
app.processEvents()
class Drop:
    accepted=False
    def source(self):return w.project_tree
    def position(self):return QPointF(10,w.project_tree.viewport().height()-1)
    def setDropAction(self,action):self.action=action
    def accept(self):self.accepted=True
    def ignore(self):self.accepted=False
event=Drop();w.project_tree.dropEvent(event);app.processEvents()
assert event.accepted and w.layers[-1].uid==second.uid
w.project_tree.topLevelItem(0).setCheckState(0,Qt.CheckState.Unchecked)
assert not w.layers[0].enabled
w.project_tree.topLevelItem(0).setCheckState(0,Qt.CheckState.Checked)
# Save only referenced library assets, and recover references in a different library.
project=root/'portable.packstudio';w.write_project(project)
saved,_,backing=load_project(project,include_sources=True);assert len(backing)==1 and all(w.layer_refs(l)=={source.uid} for l in saved)
other=StudioWindow(root/'other-library',drafts=False);other.read_project(project)
assert len(other.sources)==1 and all(other.layer_refs(l)=={source.uid} for l in other.layers)
other.dirty=False;other.close()
# A confirmed source deletion removes every shadow and clears its open canvas.
w.edit_descriptor(desc(dirt,'png','stage:'+shadow.uid));w.browse_layer(shadow.uid,True)
with patch.object(QMessageBox,'warning',return_value=QMessageBox.StandardButton.Yes):w.delete_resource(desc())
assert not w.layers and not w.sources and not w.library_store.load() and w.current is None and len(w.browsers)==1
assert hashlib.sha256(original.read_bytes()).digest()==digest
w.dirty=False;w.close()
print('PASS: library-only imports/edits, isolated shadows, cancel/confirm/prune references, tree ordering, enable, portable save, source preservation')
