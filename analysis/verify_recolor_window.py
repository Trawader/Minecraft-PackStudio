"""Modeless recolor lifecycle, quiet empty selection and cursor contracts."""
import os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from packstudio.core import Layer,png,decode
from packstudio.studio import StudioWindow
app=QApplication([])
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='recolor-window-') as tmp:
    os.environ['PACKSTUDIO_SETTINGS_FILE']=tmp+'/settings.ini'
    w=StudioWindow(Path(tmp)/'library',drafts=False);w.show();app.processEvents()
    try:
        w.smart_region_panel.analyze();assert not w.smart_region_panel.candidates
        w.frontend_flow.sync();assert w.tool_buttons['smart'].toolTip()=='智能区域'
        assert not w.tool_buttons['smart'].isEnabled()
        image=QImage(16,16,QImage.Format.Format_ARGB32);image.fill(QColor('#4488cc'))
        path='assets/minecraft/textures/blocks/stone.png'
        source=Layer('test',{path:png(image)});w.add_import(source)
        w.edit_descriptor({'origin':source.uid,'path':path,'kind':'png','name':'stone'})
        w.frontend_flow.sync();panel=w.recolor_panel;dialog=w.recolor_window
        panel.toggle.click();app.processEvents();assert dialog.isVisible() and not dialog.isModal()
        assert panel.toggle.text()=='' and not panel.toggle.icon().isNull()
        assert panel.parentWidget() is dialog.scroll.widget().parentWidget()
        panel.mode.setCurrentIndex(panel.mode.findData('adjust'));panel.controls['brightness'][1].setValue(-20)
        panel.preview();assert panel.output is not None and decode(source.files[path])==image
        QTest.keyClick(dialog,Qt.Key.Key_Escape);app.processEvents()
        assert not dialog.isVisible() and not panel.toggle.isChecked() and panel.output is None
        assert w.canvas.color_preview is None and decode(source.files[path])==image
        panel.toggle.click();dialog.resize(320,220);app.processEvents()
        dialog.scroll.ensureWidgetVisible(panel.apply_button);app.processEvents()
        assert dialog.scroll.viewport().rect().contains(panel.apply_button.mapTo(dialog.scroll.viewport(),panel.apply_button.rect().center()))
        panel.preview();panel.apply();changed=decode(source.files[path]);assert changed!=image
        dialog.close();assert decode(source.files[path])==changed
        w.canvas.undo();assert decode(source.files[path])==image
        w.canvas.redo();assert decode(source.files[path])==changed
        for tool in ('mouse','select','pencil','bucket'):
            w.set_tool(tool);assert w.canvas.cursor().shape()==Qt.CursorShape.ArrowCursor
        assert w.preview.cursor().shape()==Qt.CursorShape.ArrowCursor
        assert all(h.timer.interval()==180 for h in w.tool_hints)
        panel.toggle.click();w.clear_editor();w.frontend_flow.sync()
        assert not dialog.isVisible() and not panel.toggle.isChecked()
        w.smart_region_panel.analyze()
        print('PASS floating resize, Escape/close rollback, apply persistence, undo/redo, empty no-op, arrow cursors, 180ms hints')
    finally:w.dirty=False;w.close();app.processEvents()
