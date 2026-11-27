"""Current Help contracts: independent copies, save-as-copy and history preview."""
import os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QImage
from PySide6.QtWidgets import QApplication,QFileDialog
from packstudio.core import Layer,png,decode,load_project
from packstudio.studio import StudioWindow

app=QApplication([])
(ROOT/'.tmp').mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='help-contract-') as tmp:
    os.environ['PACKSTUDIO_SETTINGS_FILE']=tmp+'/settings.ini';os.environ['PACKSTUDIO_NAMING_FILE']=tmp+'/names.json'
    w=StudioWindow(Path(tmp)/'library',drafts=False)
    try:
        image=QImage(16,16,QImage.Format.Format_ARGB32);image.fill(QColor('blue'))
        path='assets/minecraft/textures/item/diamond_sword.png';source=Layer('test',{path:png(image)},source_version='1.20.1')
        w.add_import(source);d={'origin':source.uid,'path':path,'kind':'png','name':'Sword'}
        w.add_to_composition(d);project=w.layers[0];initial=source.files[path]
        w.edit_descriptor(d);h=w.operation_history;h.reset()
        for color in ('red','green'):
            w.canvas.checkpoint();w.canvas.image.setPixelColor(0,0,QColor(color));w.canvas.changed.emit();h.flush()
        assert project.files[path]==initial and source.files[path]!=initial
        w.library_store.flush();assert w.library_store.load()[0].files[path]==source.files[path]
        h.show();h.list.setCurrentRow(0);app.processEvents()
        assert w.canvas.image.pixelColor(0,0)==QColor('red')
        assert decode(source.files[path]).pixelColor(0,0)==QColor('green')
        h.dialog.hide();app.processEvents()
        assert w.canvas.image.pixelColor(0,0)==QColor('green') and h.list.currentRow()==-1
        h.show();h.list.setCurrentRow(0);h.rollback()
        assert len(h.done)==1 and decode(source.files[path]).pixelColor(0,0)==QColor('red')
        h.dialog.hide()
        saved=Path(tmp)/'original.MCPSD';w.write_project(saved);before=saved.read_bytes()
        project.files[path]=source.files[path];w.changed();assert w.dirty
        copy=Path(tmp)/'copy.MCPSD'
        actions=w.menuBar().actions()[0].menu().actions()
        assert not any('保存项目副本' in a.text() or 'Save project copy' in a.text() for a in actions)
        action=next(a for a in actions if a.shortcut().toString()=='Ctrl+Shift+S')
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(copy),'Project file (*.MCPSD)')):action.trigger()
        assert w.project_path==saved and w.dirty and saved.read_bytes()==before
        assert load_project(copy)[0][0].files[path]==project.files[path]
        w.save();assert not w.dirty and load_project(saved)[0][0].files[path]==project.files[path]
        print('PASS library/project isolation and persistence; history preview does not write, closes cleanly, rollback keeps selected operation; Save As copies without changing active project or dirty state.')
    finally:w.dirty=False;w.close();app.processEvents()
