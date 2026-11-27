"""Main-canvas animation views, source boundaries, history and state files."""
import os,sys,tempfile,json
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QDockWidget
from PySide6.QtGui import QColor,QImage,QFontDatabase,QFont
from packstudio.core import Layer,import_pack,decode,png
from packstudio.studio import StudioWindow
from packstudio.animation_editor import state_paths
from packstudio.texture_animation import timeline
app=QApplication([])
for name in ('segoeui.ttf','msyh.ttc'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
app.setFont(QFont('Microsoft YaHei',9))
sample=import_pack(ROOT/'reference/V3.2/重锤风弹动图.zip')
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='animation-') as tmp:
    os.environ['PACKSTUDIO_SETTINGS_FILE']=tmp+'/settings.ini';os.environ['PACKSTUDIO_NAMING_FILE']=tmp+'/names.json'
    w=StudioWindow(Path(tmp)/'library',drafts=False);w.show();app.processEvents()
    try:
        w.sources=[sample];w.refresh();dock_count=len(w.findChildren(QDockWidget))
        panel=w.animation_editor
        def open_path(path):w.edit_descriptor({'origin':sample.uid,'kind':'png','path':path,'name':Path(path).name})
        for path in [p for p in sample.files if p.endswith('.png.mcmeta')]:
            path=path[:-7];original=dict(sample.files);open_path(path)
            frames,_=timeline(sample.files[path+'.mcmeta'],w.canvas.image.width(),w.canvas.image.height())
            assert panel.frames==frames and panel.isVisible() and w.canvas.regions==[frames[0][1]]
            assert sample.files==original
            app.processEvents();w.grab().save(str(ROOT/'.tmp/v32-animation-preview.png'))
            index=min(2,len(frames)-1);panel.cards.setCurrentRow(index)
            x,y,fw,fh=frames[index][1];before=QImage(w.canvas.image)
            w.canvas.checkpoint();w.canvas.image.setPixelColor(x,y,QColor('#fe0155'));w.canvas.changed.emit()
            expected=QImage(before);expected.setPixelColor(x,y,QColor('#fe0155'))
            assert decode(sample.files[path])==expected
            assert sample.files[path+'.mcmeta']==original[path+'.mcmeta'] and set(sample.files)==set(original)
            panel.mode.setCurrentIndex(1);assert w.canvas.view_size()==before.size()
            w.canvas.undo();assert decode(sample.files[path])==before
            w.canvas.redo();assert decode(sample.files[path])==expected
            panel.play.setChecked(True);assert w.canvas.read_only and panel.timer.interval()==frames[index][2]*50
            panel.advance();assert panel.cards.currentRow()==(index+1)%len(frames)
            panel.hide();assert not panel.timer.isActive() and not w.canvas.read_only
            print('PASS real animation',Path(path).name,before.width(),before.height(),len(frames))
        path='assets/minecraft/textures/item/test.png'
        im=QImage(4,12,QImage.Format.Format_ARGB32);im.fill(QColor('red'));sample.files[path]=png(im)
        open_path(path);assert not panel.frames and w.canvas.regions is None and panel.manual.isVisible()
        before=dict(sample.files)
        with patch('packstudio.animation_editor.QInputDialog.getInt',side_effect=[(4,True),(4,True)]):panel.manual_split()
        assert len(panel.frames)==3 and sample.files==before and panel.cards.isVisible()
        with patch('packstudio.animation_editor.QInputDialog.getInt',return_value=(4,False)):panel.manual_split()
        assert sample.files==before
        sample.files[path+'.mcmeta']=b'{broken';open_path(path);assert not panel.frames and '无法解析' in panel.note.text()
        sample.files[path+'.mcmeta']=json.dumps({'animation':{'frames':[2,{'index':0,'time':7},2],'frametime':3,'interpolate':True},'unknown':42}).encode()
        open_path(path);assert [f[0] for f in panel.frames]==[2,0,2]
        assert [f[2] for f in panel.frames]==[3,7,3] and '插值' in panel.note.text()
        metadata=sample.files[path+'.mcmeta'];panel.cards.setCurrentRow(1);panel.play.setChecked(True)
        assert panel.timer.interval()==350
        states=['assets/minecraft/textures/item/bow_'+n+'.png' for n in ('standby','pulling_0','pulling_1','pulling_2')]
        for p in states:sample.files[p]=png(im.copy(0,0,4,4))
        open_path(states[0]);assert panel.states==sorted(states) and not panel.timer.isActive() and not panel.play.isVisible()
        panel.cards.setCurrentRow(panel.states.index(states[2]));assert w.current[0]==states[2]
        assert sample.files[path+'.mcmeta']==metadata and len(w.findChildren(QDockWidget))==dock_count
        assert not state_paths({'assets/minecraft/textures/item/custom_01.png':b'', 'assets/minecraft/textures/item/custom_02.png':b''},'assets/minecraft/textures/item/custom_01.png')
        w.clear_editor();assert not panel.isVisible() and panel.descriptor is None
        print('PASS timeline order/durations, invalid metadata, no guessing, state source switching, no new docks')
    finally:w.dirty=False;w.close();app.processEvents()
