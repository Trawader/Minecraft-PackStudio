import os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen';sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtGui import QImage,QColor,QRegion
from packstudio.core import Layer,png,decode
from packstudio.studio import StudioWindow
from packstudio.batch_recolor import plan,preview_files
from packstudio.recolor import Settings
app=QApplication([])
with tempfile.TemporaryDirectory() as temp:
    os.environ['PACKSTUDIO_SETTINGS_FILE']=str(Path(temp)/'settings.ini')
    w=StudioWindow(Path(temp)/'library',drafts=False);w.show();app.processEvents()
    try:
        p='assets/minecraft/optifine/sky/world0/sky1.png';config=p.replace('.png','.properties')
        sky=QImage(96,64,QImage.Format.Format_ARGB32);sky.fill(QColor(70,130,200,137));sky.setPixelColor(0,0,QColor(1,2,3,0))
        source=Layer('sky',{p:png(sky),config:b'source=./sky1.png\nstartFadeIn=06:00\nblend=add\n'})
        original=dict(source.files);w.sources=[source];w.refresh();d={'kind':'png','origin':source.uid,'path':p,'name':'sky1.png'}
        w.edit_descriptor(d);w.frontend_flow.sync()
        assert not w.canvas.read_only and not w.large_view_only and w.canvas.image==sky
        assert w.sky_edit_key==(source.uid,p) and w.preview.sky_layout=='cube'
        for tool in ('pencil','eraser','magic_eraser','bucket','picker','select','wand','burn','dodge','lighten','darken'):
            w.set_tool(tool);assert w.canvas.tool==tool
        panel=w.recolor_panel;assert panel.toggle.toolTip()=='调色'
        panel.mode.setCurrentIndex(panel.mode.findData('adjust'));panel.controls['saturation'][1].setValue(-50)
        panel.preview();assert w.preview.sky_image!=sky and source.files==original
        panel.invalidate();assert w.preview.sky_image==sky
        panel.preview();expected=QImage(panel.output);panel.apply()
        assert decode(source.files[p])==expected and source.files[config]==original[config]
        assert w.preview.sky_image==expected and expected.pixelColor(0,0).alpha()==0 and expected.pixelColor(1,1).alpha()==137
        w.canvas.undo();assert decode(source.files[p])==sky and w.preview.sky_image==sky
        w.canvas.redo();assert decode(source.files[p])==expected and w.preview.sky_image==expected
        w.canvas.undo()
        w.canvas.checkpoint();w.canvas.image.setPixelColor(3,4,QColor('red'));w.canvas.changed.emit()
        assert decode(source.files[p]).pixelColor(3,4)==QColor('red') and w.preview.sky_image.pixelColor(3,4)==QColor('red')
        w.canvas.undo();assert decode(source.files[p])==sky
        source.read_only=True;w.edit_descriptor(d);w.frontend_flow.sync();assert w.canvas.read_only and not panel.toggle.isEnabled()
        source.read_only=False
        large=QImage(3072,1536,QImage.Format.Format_ARGB32);large.fill(QColor(50,100,200,127))
        lp=p.replace('sky1','sky2');source.files[lp]=png(large);ld=dict(d,path=lp)
        before=w.current
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Cancel) as ask:
            w.edit_descriptor(ld);assert ask.call_count==1 and w.current==before and w.canvas.image==sky
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes) as ask:
            w.edit_descriptor(ld);assert ask.call_count==1
        assert w.canvas.image.size()==large.size() and w.preview.sky_image.width()==2048 and w.preview.sky_layout=='panorama'
        w.canvas.selection_region=QRegion(2,2,8,8);w.canvas.sync_selection()
        panel.mode.setCurrentIndex(panel.mode.findData('adjust'));panel.controls['saturation'][1].setValue(-70)
        panel.preview();panel.apply();edited=decode(source.files[lp])
        assert edited.size()==large.size() and edited.pixelColor(3,3)!=large.pixelColor(3,3)
        assert edited.pixelColor(0,0)==large.pixelColor(0,0) and edited.pixelColor(3,3).alpha()==127
        w.canvas.undo();assert decode(source.files[lp])==edited
        w.operation_history.step(barriers=True);assert decode(source.files[lp])==large
        units,base,meta,errors=plan(source,ld);assert not errors and units
        units[0].mask=QRegion(2,2,2,2);out=preview_files(units,base,Settings(mode='adjust',brightness=10))
        assert decode(out[lp]).size()==large.size()
        w.clear_editor()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Cancel) as ask:
            w.resource_editors.open_editor(ld);assert ask.call_count==1 and not w.resource_editors.editors
        cp='assets/minecraft/textures/items/demo.png';source.files[cp]=png(sky)
        w.edit_descriptor(dict(d,path=cp));assert w.sky_edit_key is None and w.preview.sky_image is None
        print('PASS sky tools, recolor preview/cancel/apply/undo/redo, live sky projection, alpha/config preservation, readonly sources, >4Mi-pixel original-size single/batch editing and large-image confirm/cancel')
    finally:w.dirty=False;w.close();app.processEvents()
