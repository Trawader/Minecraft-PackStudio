"""Global barriers apply across unrelated textures and independent editors."""
import os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QColor,QRegion,QFontDatabase,QFont
from packstudio.studio import StudioWindow
from packstudio.core import Layer,png,decode
from packstudio.batch_recolor import plan,preview_files,apply_batch
from packstudio.recolor import Settings
app=QApplication([])
QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc');app.setFont(QFont('Microsoft YaHei',9))
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='history-') as tmp:
    os.environ['PACKSTUDIO_SETTINGS_FILE']=tmp+'/settings.ini'
    w=StudioWindow(Path(tmp)/'library',drafts=False);w.show();app.processEvents()
    try:
        im=QImage(16,16,QImage.Format.Format_ARGB32);im.fill(QColor('#4488cc'))
        a='assets/minecraft/textures/blocks/stone.png';b='assets/minecraft/textures/blocks/dirt.png'
        source=Layer('history',{a:png(im),b:png(im)},source_version='1.8.9');w.add_import(source)
        def d(path):return dict(origin=source.uid,path=path,kind='png',name=path)
        h=w.operation_history
        h.reset()  # Treat fixture import as the starting point for this scenario.
        def edit(path,color):
            w.edit_descriptor(d(path));w.canvas.checkpoint();w.canvas.image.setPixelColor(0,0,QColor(color));w.canvas.changed.emit();h.flush()
        edit(a,'red');assert len(h.done)==1
        units,base,meta,errors=plan(source,d(b));assert not errors
        output=preview_files(units,base,Settings(mode='adjust',brightness=-20));apply_batch(w,source.uid,source,base,meta,output)
        assert h.done[-1]['kind']=='batch' and not h.available()
        w.canvas.undo();assert decode(source.files[a]).pixelColor(0,0)==QColor('red')
        assert not w.history_buttons[0].isEnabled()
        edit(a,'green');w.canvas.undo();assert decode(source.files[a]).pixelColor(0,0)==QColor('red') and not h.available()
        assert h.available(redo=True)
        assert h.step(barriers=True);assert decode(source.files[b])==im
        assert h.available() and not h.available(redo=True)
        w.canvas.undo();assert decode(source.files[a])==im
        w.canvas.redo();assert decode(source.files[a]).pixelColor(0,0)==QColor('red')
        assert not h.available(redo=True);assert h.step(redo=True,barriers=True)
        w.canvas.redo();assert decode(source.files[a]).pixelColor(0,0)==QColor('green')
        h.show();h.list.setCurrentRow(0);h.rollback();assert not h.done and decode(source.files[a])==im and decode(source.files[b])==im
        assert h.step(redo=True,barriers=True)
        edit(b,'yellow');assert not h.future
        # Project actions reuse conflict-checked resource rollback and redo.
        w.add_to_composition(dict(origin=source.uid,path='',kind='root',name='history'))
        assert h.done[-1]['kind']=='resource' and not h.available()
        assert h.step(barriers=True) and not w.layers
        assert h.step(redo=True,barriers=True) and len(w.layers)==1
        assert h.step(barriers=True)
        # Conflict does not consume the timeline entry or overwrite external content.
        changed=QImage(im);changed.fill(QColor('black'));source.files[b]=png(changed);count=len(h.done)
        try:h.step(barriers=True);raise AssertionError('conflict ignored')
        except ValueError:pass
        assert len(h.done)==count and decode(source.files[b])==changed
        # Independent editor joins the same timeline, with the same global barrier.
        source.files[b]=h.done[-1]['raw_after']
        w.resource_editors.open_editor(d(a));dock,e=next(iter(w.resource_editors.editors.values()))
        assert e.canvas.timeline is h
        e.canvas.checkpoint();e.canvas.image.setPixelColor(1,1,QColor('white'));e.canvas.changed.emit();h.flush()
        assert h.done[-1]['key']==(source.uid,a)
        e.canvas.undo();assert decode(source.files[a]).pixelColor(1,1)!=QColor('white')
        e.canvas.checkpoint(e.canvas.snapshot(pixel_edit=False));e.canvas.selection_region=QRegion(1,1,3,3);e.canvas.sync_selection();h.flush()
        assert h.done[-1]['label'].startswith('选区')
        e.canvas.undo();assert e.canvas.selection_region.isEmpty()
        e.canvas.redo();assert not e.canvas.selection_region.isEmpty()
        dock.close()
        assert w.menuBar().actions().index(w.language_action)==w.menuBar().actions().index(w.settings_action)+1
        h.show();app.processEvents();h.dialog.grab().save(str(ROOT/'.tmp/operation-history.png'))
        w.language_changed(1);app.processEvents();w.localizer.refresh()
        assert h.action.text()=='History…' and h.dialog.windowTitle()=='History'
        assert h.rollback_button.text()=='Roll back selected and later actions'
        print('PASS global cross-texture barrier, normal undo/redo, batch and project rollback/redo, branch discard, conflict safety, independent editor, menu order')
    finally:w.dirty=False;w.close();app.processEvents()
