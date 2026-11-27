"""Small-window geometry, compact tools, popup gestures and frame replacement."""
import os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QFontDatabase,QFont,QColor,QImage
from PySide6.QtWidgets import QApplication,QPushButton
from PySide6.QtTest import QTest
from packstudio.studio import StudioWindow
from packstudio.core import import_pack,decode,png
from packstudio.editor_layout import mode_menu
app=QApplication([])
for name in ('segoeui.ttf','msyh.ttc'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
app.setFont(QFont('Microsoft YaHei',9))
def settle():
    for _ in range(6):app.processEvents()
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='layout-') as tmp:
    os.environ['PACKSTUDIO_SETTINGS_FILE']=tmp+'/settings.ini';os.environ['PACKSTUDIO_NAMING_FILE']=tmp+'/names.json'
    w=StudioWindow(Path(tmp)/'library',drafts=False);w.show();settle()
    try:
        source=import_pack(ROOT/'reference/V3.2/重锤风弹动图.zip');w.sources=[source];w.refresh()
        path=next(p for p in source.files if p.endswith('/mace.png'));w.edit_descriptor({'origin':source.uid,'kind':'png','path':path,'name':'mace'})
        recolor=w.recolor_panel;animation=w.animation_editor
        for width,height in ((1280,720),(1024,640),(1600,900)):
            w.resize(width,height);settle();recolor.toggle.setChecked(True);settle()
            assert w.width()<=width and w.height()<=height,(w.size(),width,height)
            scroll=w.recolor_window.scroll;scroll.ensureWidgetVisible(recolor.apply_button);settle()
            center=recolor.apply_button.mapTo(scroll.viewport(),recolor.apply_button.rect().center())
            assert scroll.viewport().rect().contains(center),(width,height,center,scroll.viewport().rect())
            assert w.recolor_window.isVisible() and not w.recolor_window.isModal()
            assert w.canvas.height()>=100 and w.canvas.width()>=100
            before=animation.cards.isVisible();recolor.toggle.setChecked(False);settle();assert animation.cards.isVisible()==before
            recolor.toggle.setChecked(True);scroll.ensureWidgetVisible(recolor.mode);settle()
            if width==1280:w.grab().save(str(ROOT/'.tmp/v32-compact-editor.png'))
        palette=w.canvas_palette.layout();assert palette.count()==8
        assert [palette.getItemPosition(i)[:2] for i in range(8)]==[(i//4,i%4) for i in range(8)]
        for key in ('wand','smart'):assert w.tool_buttons[key].isVisible() and w.tool_buttons[key].text()==''
        assert w.menuBar().height()<=28,w.menuBar().height()
        menu_actions=w.menuBar().actions()
        assert menu_actions.index(w.language_action)==menu_actions.index(w.settings_action)+1
        assert w.menuBar().cornerWidget(Qt.Corner.TopRightCorner) is None
        language_rect=w.menuBar().actionGeometry(w.language_action);window_rect=w.menuBar().actionGeometry(w.window_menu.menuAction())
        assert language_rect.left()>window_rect.right() and abs(language_rect.center().y()-window_rect.center().y())<=1
        for name in ('undo','redo','globe'):
            bitmap=QImage(str(ROOT/'packstudio/assets'/f'{name}-{16 if name=="globe" else 24}.png'))
            colors={bitmap.pixelColor(x,y).name() for y in range(bitmap.height()) for x in range(bitmap.width()) if bitmap.pixelColor(x,y).alpha()}
            assert colors=={'#cccccc'}
        for key in ('picker','select','wand','burn','lighten'):
            assert w.tool_buttons[key].menu_mark.isVisible()
            assert '右键' not in w.tool_buttons[key].toolTip()
        for key in ('mouse','pencil','eraser','bucket','picker','select','wand','smart','burn','dodge','lighten','darken'):
            bitmap=QImage(str(ROOT/'packstudio/assets'/f'tool-{key}-20.png'));assert not bitmap.isNull()
            pixels=[(x,y) for y in range(20) for x in range(20) if bitmap.pixelColor(x,y).alpha()]
            assert pixels
            assert all(bitmap.pixelColor(x,y).alpha()==0 for x,y in ((0,0),(19,0),(0,19),(19,19)))
            assert abs((min(x for x,y in pixels)+max(x for x,y in pixels))/2-9.5)<=.5
            assert abs((min(y for x,y in pixels)+max(y for x,y in pixels))/2-9.5)<=.5
        w.tool_scroll.grab().save(str(ROOT/'.tmp/v32-toolbar-detail.png'))
        for key in ('dodge','darken'):assert not w.tool_buttons[key].isVisible()
        assert all(button.text()=='' for button in w.history_buttons)
        original_pixels=png(w.canvas.image);history=len(w.canvas.history)
        center=QPointF(w.canvas.width()/2,w.canvas.height()/2)
        anchor=(center-w.canvas.offset)/w.canvas.zoom
        zoom=w.canvas_zoom_input;zoom.lineEdit().selectAll();QTest.keyClicks(zoom.lineEdit(),'1250');QTest.keyClick(zoom,Qt.Key.Key_Return)
        assert w.canvas.zoom==12.5 and zoom.value()==1250
        assert ((center-w.canvas.offset)/w.canvas.zoom-anchor).manhattanLength()<1e-8
        zoom.stepUp();assert w.canvas.zoom==12.75
        w.canvas.zoom_at(center,1);assert abs(zoom.value()-w.canvas.zoom*100)<=.051
        zoom.setValue(8000);assert w.canvas.zoom==80
        zoom.setValue(10);assert w.canvas.zoom==.1
        assert png(w.canvas.image)==original_pixels and len(w.canvas.history)==history
        zoom.setValue(800);settle()
        controls=w.history_buttons[-1].parentWidget()
        controls.grab().copy(controls.width()-200,controls.height()-34,200,34).save(str(ROOT/'.tmp/v32-zoom-controls.png'))
        button=w.tool_buttons['burn'];menu=mode_menu(w,button,[('burn','加深'),('dodge','减淡')])
        choices=[a.defaultWidget() for a in menu.actions()]
        choices[1].click();assert w.canvas.tool=='dodge' and button.active_mode=='dodge' and button.isChecked()
        assert button.toolTip()=='减淡'
        with patch.object(w,'tone_amount') as amount:
            choices[1].customContextMenuRequested.emit(QPoint());settle();amount.assert_called_once_with('dodge')
        menu.deleteLater()
        descriptor=animation.frame_descriptor(0);w.select_asset(descriptor)
        assert len(w.selected_asset['files'])==1
        patch_image=decode(next(iter(w.selected_asset['files'].values())));patch_image.fill(QColor('magenta'))
        w.selected_asset['files']={str(0):png(patch_image)}
        original=decode(source.files[path]);metadata=source.files[path+'.mcmeta'];animation.replace_frame(1)
        result=decode(source.files[path]);rect=animation.frames[1][1]
        assert result.copy(*rect)==patch_image and result.copy(*animation.frames[0][1])==original.copy(*animation.frames[0][1])
        assert source.files[path+'.mcmeta']==metadata
        w.canvas.undo();assert decode(source.files[path])==original
        with patch.object(w,'export_png') as export:w.export_png_action.trigger();export.assert_called_once()
        print('PASS 1024x640 / 1280x720 / 1600x900, reachable apply controls, independent collapse, 4x2 palette, grouped tool gestures, frame replace/undo, file export')
    finally:w.dirty=False;w.close();settle()
