"""Current Help: sky edits, read-only guards, related state cards and cancellation."""
import os,sys,tempfile
from unittest.mock import patch
from pathlib import Path
from threading import Event
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QImage,QRegion
from PySide6.QtWidgets import QApplication
from packstudio.core import Layer,png,decode
from packstudio.studio import StudioWindow
from packstudio.recolor import Settings,render

app=QApplication([])
(ROOT/'.tmp').mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='help-ui-') as tmp:
    os.environ['PACKSTUDIO_SETTINGS_FILE']=tmp+'/settings.ini';os.environ['PACKSTUDIO_NAMING_FILE']=tmp+'/names.json'
    w=StudioWindow(Path(tmp)/'library',drafts=False)
    try:
        path='assets/minecraft/optifine/sky/world0/sky1.png';config=path.replace('.png','.properties')
        image=QImage(96,64,QImage.Format.Format_ARGB32);image.fill(QColor(70,130,200,138))
        image.setPixelColor(0,0,QColor(1,2,3,0))
        source=Layer('test',{path:png(image),config:b'source=./sky1.png\nblend=add\n'})
        original=dict(source.files);w.sources=[source];w.refresh()
        def descriptor(p):return {'kind':'png','origin':source.uid,'path':p,'name':Path(p).name}
        w.edit_descriptor(descriptor(path));panel=w.recolor_panel
        controls=panel.shared_controls;controls.mode.setCurrentIndex(controls.mode.findData('opacity'));controls.alpha.setValue(50)
        panel.preview();assert source.files==original and w.preview.sky_image!=image
        panel.invalidate();assert w.preview.sky_image==image
        panel.preview();panel.apply();edited=decode(source.files[path])
        assert edited.pixelColor(1,1).alpha()==69 and edited.pixelColor(0,0).alpha()==0
        assert source.files[config]==original[config]
        assert w.preview.sky_image.convertToFormat(edited.format())==edited
        w.canvas.undo();assert decode(source.files[path])==image
        source.read_only=True;w.edit_descriptor(descriptor(path));w.frontend_flow.sync()
        assert w.canvas.read_only and not panel.body.isEnabled() and not panel.preview_button.isEnabled()
        try:panel.preview();raise AssertionError('read-only source accepted recolor')
        except ValueError:pass
        assert source.files==original
        source.read_only=False
        states=['assets/minecraft/textures/item/bow.png']+['assets/minecraft/textures/item/bow_pulling_'+str(i)+'.png' for i in range(3)]
        for p in states:source.files[p]=png(image.copy(0,0,16,16))
        w.edit_descriptor(descriptor(states[0]));strip=w.resource_editors
        assert w.animation_editor.isHidden() and not w.animation_editor.timer.isActive()
        assert set(strip.paths)==set(states) and strip.cards.count()==4
        item=next(strip.cards.item(i) for i in range(4) if strip.cards.item(i).data(Qt.ItemDataRole.UserRole)['path']==states[2])
        with patch.object(w,'run',side_effect=lambda fn:fn()):strip.pick(item)
        assert w.current[0]==states[2]
        before=dict(source.files)
        for language,title in ((1,'Asset library'),(0,'素材库')):
            w.language_changed(language);app.processEvents()
            assert w.docks['library'].windowTitle()==title and source.files==before
        assert w.resource_rules.dock.windowTitle()=='配置规则'
        print('PASS shared opacity controls, sky preview/cancel/apply/undo, alpha/config preservation, read-only UI/backend guards, single state strip switching, language preserves files.')
    finally:w.dirty=False;w.close();app.processEvents()

image=QImage(64,64,QImage.Format.Format_ARGB32);image.fill(QColor('#58aabb'));before=QImage(image)
for settings in (Settings(mode='range'),Settings(mode='color'),Settings(mode='opacity',opacity=50)):
    stop=Event()
    def progress(a,b):
        if a>3:stop.set()
    try:render(image,QRegion(image.rect()),settings,cancel=stop,progress=progress);raise AssertionError('cancel ignored')
    except InterruptedError:pass
    assert image==before
stop=Event();stop.set()
try:render(image,QRegion(image.rect()),Settings(mode='opacity',opacity=100),cancel=stop);raise AssertionError('pre-cancel ignored')
except InterruptedError:pass
assert render(image,QRegion(image.rect()),Settings(mode='opacity',opacity=100))==image
print('PASS cancellation in current recolor modes, unchanged original, neutral opacity shortcut and pre-cancel.')
