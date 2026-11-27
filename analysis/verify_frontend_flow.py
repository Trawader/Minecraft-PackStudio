import os,sys,tempfile
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QColor
from packstudio.core import Layer,png
from packstudio.studio import StudioWindow
from packstudio.batch_recolor_dialog import BatchRecolorDialog
app=QApplication([])
with tempfile.TemporaryDirectory() as temp:
    os.environ['PACKSTUDIO_SETTINGS_FILE']=str(Path(temp)/'settings.ini')
    w=StudioWindow(Path(temp)/'library',drafts=False);w.show();app.processEvents();flow=w.frontend_flow
    try:
        flow.sync();assert flow.library_hint.isVisible() and flow.project_hint.isVisible()
        assert not w.export_png_action.isEnabled() and not w.undo_batch_action.isEnabled()
        assert not any(b.isEnabled() for b in w.history_buttons)
        assert not any(a.isEnabled() for a in flow.export_buttons)
        image=QImage(16,16,QImage.Format.Format_ARGB32);image.fill(QColor('#50aabb'))
        path='assets/minecraft/textures/items/diamond_sword.png';source=Layer('review',{path:png(image)})
        w.sources=[source];w.refresh();d={'origin':source.uid,'kind':'png','path':path,'name':'diamond_sword.png'}
        w.edit_descriptor(d);flow.sync()
        assert w.export_png_action.isEnabled() and w.tool_buttons['pencil'].isEnabled()
        assert w.tool_buttons['pencil'].accessibleName()
        assert not flow.canvas_hint.isVisible()
        menu=w.resource_menu(d);assert not menu.actions()[3].isEnabled()
        w.select_asset(d);menu=w.resource_menu(d);assert menu.actions()[3].isEnabled()
        w.canvas.checkpoint();w.canvas.image.setPixelColor(0,0,QColor('blue'));w.canvas.changed.emit();flow.sync();assert w.history_buttons[0].isEnabled()
        w.canvas.undo();flow.sync();assert w.history_buttons[1].isEnabled()
        w.canvas.read_only=True;flow.sync();assert not w.tool_buttons['bucket'].isEnabled() and not w.recolor_panel.toggle.isEnabled()
        assert w.tool_buttons['select'].isEnabled()
        w.large_view_only=True;flow.sync();assert not w.export_png_action.isEnabled() and not w.tool_buttons['smart'].isEnabled()
        w.large_view_only=False;w.canvas.read_only=False
        layer=Layer('copy',{path:png(image)});w.layers=[layer];w.remember();w.layers=[];w.refresh();flow.sync()
        assert flow.project_undo.isEnabled() and not flow.export_buttons[0].isEnabled()
        flow.project_undo.trigger();flow.sync();assert w.layers and flow.export_buttons[0].isEnabled()
        dialog=BatchRecolorDialog(w,dict(d));dialog.show();app.processEvents()
        assert dialog.first.isHidden() and dialog.fields['opacity'].isHidden() and dialog.direction.isHidden()
        assert dialog.review.isHidden() and not dialog.cancel_button.isEnabled()
        dialog.set_included(False);assert not any(u.included for u in dialog.units)
        dialog.set_included(True);assert all(u.included for u in dialog.units)
        dialog.mode.setCurrentIndex(dialog.mode.findData('opacity'));assert not dialog.fields['opacity'].isHidden() and dialog.fields['saturation'].isHidden()
        dialog.mode.setCurrentIndex(dialog.mode.findData('spatial'));assert not dialog.last.isHidden() and not dialog.direction.isHidden()
        dialog.close()
        w.clear_editor();flow.sync();assert not w.export_png_action.isEnabled()
        print('PASS empty/loaded/readonly/large-view action parity, replacement prerequisites, canvas history, last-project removal undo, batch mode controls and inclusion')
    finally:w.dirty=False;w.close();app.processEvents()
