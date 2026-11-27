"""Atomic cascading deletion, identity retention, cancellation and invalid barriers."""
import os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtGui import QImage,QColor
from packstudio.core import Layer,png,decode
from packstudio.studio import StudioWindow
app=QApplication([])
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='history-changes-') as temp:
    os.environ['PACKSTUDIO_SETTINGS_FILE']=temp+'/settings.ini'
    w=StudioWindow(Path(temp)/'library',drafts=False);w.show();app.processEvents()
    try:
        h=w.operation_history;im=QImage(16,16,QImage.Format.Format_ARGB32);im.fill(QColor('red'))
        a='assets/minecraft/textures/blocks/stone.png';b='assets/minecraft/textures/blocks/dirt.png'
        s=Layer('original',{a:png(im),b:png(im)},source_version='1.8.9');w.add_import(s)
        assert h.done[-1]['kind']=='group'
        h.step(barriers=True);assert w.source(s.uid) is None
        h.step(redo=True,barriers=True);s=w.source(s.uid);assert s is not None
        root=dict(origin=s.uid,path='',kind='root',name=s.name)
        w.add_to_composition(root);layer=w.layers[0];layer.files[b]=b'independent copy'
        before=w.clone_layer(layer);source_before=w.clone_layer(s);n=len(h.done)
        with patch.object(QMessageBox,'warning',return_value=QMessageBox.StandardButton.Cancel):w.delete_resource(root)
        assert len(h.done)==n and w.source(s.uid)==source_before
        with patch.object(QMessageBox,'warning',return_value=QMessageBox.StandardButton.Yes):w.delete_resource(root)
        assert w.source(s.uid) is None and not w.layers and len(h.done)==n+1
        assert h.done[-1]['kind']=='group' and not h.available()
        assert h.step(barriers=True);assert w.source(s.uid)==source_before and w.layers[0]==before
        assert any(x.uid==s.uid for x in w.library_store.load())
        assert h.step(redo=True,barriers=True) and w.source(s.uid) is None and not w.layers
        h.step(barriers=True);s=w.source(s.uid)
        # Multi-file deletion is one entry, including linked project content.
        ds=[dict(root,path=p,kind='png') for p in (a,b)];n=len(h.done)
        with patch.object(QMessageBox,'warning',return_value=QMessageBox.StandardButton.Yes):w.delete_descriptors(ds)
        assert len(h.done)==n+1 and not s.files
        put=w.library_store.put;failed=[False]
        def restore_failure(value):
            if not failed[0]:failed[0]=True;raise OSError('simulated restore failure')
            return put(value)
        with patch.object(w.library_store,'put',side_effect=restore_failure):
            try:h.step(barriers=True);raise AssertionError('expected restore failure')
            except OSError:pass
        assert len(h.done)==n+1 and not s.files and not h.done[-1].get('invalid')
        h.step(barriers=True);assert w.source(s.uid)==source_before and w.layers[0]==before
        # A failed persistence step restores source and project together.
        put=w.library_store.put;calls=[0]
        def fail_once(value):
            calls[0]+=1
            if calls[0]==1:raise OSError('simulated write failure')
            return put(value)
        n=len(h.done)
        with patch.object(QMessageBox,'warning',return_value=QMessageBox.StandardButton.Yes),patch.object(w.library_store,'put',side_effect=fail_once):
            try:w.delete_resource(ds[0]);raise AssertionError('expected failure')
            except OSError:pass
        assert len(h.done)==n and w.source(s.uid)==source_before and w.layers[0]==before
        # Earlier canvas history remains valid after delete/restore of its owner.
        extra=Layer('editable',{a:png(im)},source_version='1.8.9');w.add_import(extra)
        ed=dict(origin=extra.uid,path=a,kind='png',name='stone')
        w.edit_descriptor(ed);w.canvas.checkpoint();w.canvas.image.setPixelColor(0,0,QColor('blue'));w.canvas.changed.emit();h.flush()
        w.delete_resource(dict(ed,path='',kind='root'))
        h.step(barriers=True);assert decode(w.source(extra.uid).files[a]).pixelColor(0,0)==QColor('blue')
        h.step();assert decode(w.source(extra.uid).files[a])==im
        w.source(extra.uid).name='renamed';assert w.source(extra.uid).uid==extra.uid
        # Budget overflow keeps other records and creates an explicit boundary.
        with patch('packstudio.history_changes.LIMIT',1),patch.object(QMessageBox,'warning',return_value=QMessageBox.StandardButton.Yes):w.delete_resource(root)
        assert h.done[-1]['kind']=='blocked' and len(h.done)>1 and not h.available(barriers=True)
        other=Layer('new',{a:png(im)},source_version='1.8.9');w.add_import(other)
        assert h.step(barriers=True) and w.source(other.uid) is None
        assert not h.available(barriers=True)
        # Same filename with another UID must never revive the old deletion target.
        other=Layer('original',{a:png(im)},source_version='1.8.9');w.add_import(other)
        other.files[a]=b'external change';n=len(h.done)
        try:h.step(barriers=True);raise AssertionError('expected conflict')
        except ValueError:pass
        assert len(h.done)==n and h.done[-1]['invalid'] and other.files[a]==b'external change'
        h.show();assert not h.can_rollback(0) and not h.rollback_button.isEnabled()
        print('PASS import undo, UID retention, linked deletion undo/redo, cancelled delete, grouped multi-delete, persistence rollback, budget boundary, conflict invalidation')
    finally:w.dirty=False;w.close();app.processEvents()
