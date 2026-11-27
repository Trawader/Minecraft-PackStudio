"""Tonal anchors, gradients, GUI borders, preview transactions and animation masks."""
import os,sys,tempfile,json,colorsys
from dataclasses import replace
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QImage,QColor,QRegion,QPainter,QFont,QFontDatabase
from PySide6.QtWidgets import QApplication
from packstudio.recolor import Settings,anchor_level,render,gui_background,match_region,signature
from packstudio.smart_regions import analyze
from packstudio.core import Layer,png,decode,import_pack
from packstudio.studio import StudioWindow
app=QApplication([])
for font in ('segoeui.ttf','msyh.ttc'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
app.setFont(QFont('Microsoft YaHei',9))
levels=[(.1,.1,.1),(.3,.3,.3),(.5,.5,.5),(.7,.7,.7),(.9,.9,.9)]
assert abs(anchor_level(levels+[levels[0]]*100,'middle')[0]-.5)<.003
assert anchor_level(levels+[levels[0]]*100,'average')[0]<.13
assert abs(anchor_level([levels[0],levels[1]],'middle')[0]-.2)<.003
im=QImage(5,2,QImage.Format.Format_ARGB32);im.fill(Qt.GlobalColor.transparent)
for x,rgb in enumerate(levels):
    c=QColor.fromRgbF(*rgb);c.setAlpha(70+x*30);im.setPixelColor(x,0,c)
region=QRegion(0,0,5,2)
for mode in ('middle','average','dark','light','range','spatial','adjust'):
    out=render(im,region,Settings(mode=mode,first='#302060',last='#e0ccff'))
    assert [out.pixelColor(x,0).alpha() for x in range(5)]==[im.pixelColor(x,0).alpha() for x in range(5)]
    assert all(out.pixelColor(x,1).alpha()==0 for x in range(5))
    if mode not in ('spatial','adjust'):assert all(out.pixelColor(x,0).lightness()<=out.pixelColor(x+1,0).lightness() for x in range(4))
for mode,index in [('middle',2),('dark',0),('light',4)]:
    out=render(im,region,Settings(mode=mode,first='#AA96F8'))
    assert max(abs(a-b) for a,b in zip(out.pixelColor(index,0).getRgb()[:3],QColor('#AA96F8').getRgb()[:3]))<=2
endpoints=Settings(mode='spatial',first='#000000',last='#ffffff',direction='right')
out=render(im,region,endpoints);assert out.pixelColor(0,0).red()==0 and out.pixelColor(4,0).red()==255
out=render(im,region,replace(endpoints,smooth=0));assert {out.pixelColor(x,0).red() for x in range(5)}=={0,255}
out=render(im,region,replace(endpoints,direction='left'));assert out.pixelColor(0,0).red()==255
partial=render(im,QRegion(2,0,1,1),Settings(),{(2,0):128});assert partial.pixelColor(1,0)==im.pixelColor(1,0)
gui=QImage(32,32,QImage.Format.Format_ARGB32);gui.fill(QColor('#aaaaaa'));p=QPainter(gui)
p.setPen(QColor('#222222'));p.drawRect(0,0,31,31);p.drawRect(7,7,12,12);p.drawLine(0,24,31,24);p.end()
background=gui_background(gui,QRegion(gui.rect()));assert background.contains(QPoint(4,4))
assert not background.contains(QPoint(7,12)) and not background.contains(QPoint(12,24)) and not background.contains(QPoint(0,8))
transparent=render(gui,background,Settings(mode='opacity',opacity=50))
assert transparent.pixelColor(4,4).alpha()==128 and transparent.pixelColor(7,12).alpha()==255
print('PASS level median vs pixel average, anchors, monotonic shading, alpha/AA, gradient direction/smoothness, internal GUI borders')

visuals=[]
for pattern in ('*Tsuki*.zip','*Blue*.zip','Everest*.zip'):
    pack=import_pack(next((ROOT/'reference/V3.2').glob(pattern)))
    for stem in ('diamond_sword.png','diamond_helmet.png'):
        pth=next(p for p in pack.files if p.endswith('/'+stem));original=decode(pack.files[pth]);mask=analyze(original)[0].region
        modified=render(original,mask,Settings(first='#AA96F8'))
        for y in range(original.height()):
            for x in range(original.width()):
                assert modified.pixelColor(x,y).alpha()==original.pixelColor(x,y).alpha()
                if not mask.contains(QPoint(x,y)):assert modified.pixelColor(x,y)==original.pixelColor(x,y)
        visuals.append((pattern+' / '+stem,original,modified))
sheet=QImage(500,len(visuals)*180,QImage.Format.Format_ARGB32);sheet.fill(QColor('#333333'));p=QPainter(sheet)
try:
    for row,(label,before,after) in enumerate(visuals):
        p.setPen(QColor('white'));p.drawText(8,row*180+17,label)
        for x,picture in ((25,before),(280,after)):p.drawImage(x,row*180+28,picture.scaled(140,140,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation))
finally:p.end()
sheet.save(str(ROOT/'.tmp/v32-recolor-samples.png'))
print('PASS six real textures: outside-mask pixels and all alpha values preserved')

with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='recolor-') as tmp:
    os.environ['PACKSTUDIO_SETTINGS_FILE']=tmp+'/settings.ini';os.environ['PACKSTUDIO_NAMING_FILE']=tmp+'/names.json'
    w=StudioWindow(Path(tmp)/'library',drafts=False);w.show();app.processEvents()
    try:
        path='assets/minecraft/textures/item/fixture.png';source=Layer('fixture',{path:png(im)});w.sources=[source];w.refresh()
        def open_path(p):w.edit_descriptor({'origin':source.uid,'kind':'png','path':p,'name':Path(p).name})
        open_path(path);panel=w.recolor_panel;canvas=w.canvas;panel.toggle.setChecked(True)
        panel.mode.setCurrentIndex(panel.mode.findData('adjust'));panel.controls['contrast'][1].setValue(25)
        panel.preview();assert panel.output==render(im,QRegion(im.rect()),Settings(mode='adjust',contrast=25))
        panel.invalidate();panel.controls['contrast'][1].setValue(0);panel.mode.setCurrentIndex(0)
        canvas.selection_region=QRegion(1,0,3,1);canvas.sync_selection();original=dict(source.files);history=len(canvas.history)
        panel.preview();assert source.files==original and len(canvas.history)==history and canvas.color_preview is not None
        panel.invalidate();assert source.files==original and canvas.color_preview is None
        panel.preview();expected=QImage(panel.output);panel.apply();assert decode(source.files[path])==expected and len(canvas.history)==history+1
        canvas.undo();assert decode(source.files[path])==im
        canvas.redo();assert decode(source.files[path])==expected
        panel.preview();panel.controls['contrast'][1].setValue(10);assert panel.output is None
        panel.controls['contrast'][1].setValue(0)
        # Atlas operations only touch the actual component, never neighboring icons.
        source.files[path]=png(gui);w.load_canvas();canvas.set_atlas(canvas.image,[(7,7,12,12)],(source.uid,path));panel.scope.setCurrentIndex(1)
        panel.preview();panel.apply();after=decode(source.files[path]);assert after.pixelColor(2,2)==gui.pixelColor(2,2)
        canvas.undo();assert decode(source.files[path])==gui
        # The two moving colored regions occupy different coordinates.
        anim=QImage(16,32,QImage.Format.Format_ARGB32);anim.fill(Qt.GlobalColor.transparent);p=QPainter(anim)
        p.fillRect(1,1,4,4,QColor('#2277cc'));p.fillRect(10,18,4,4,QColor('#2277cc'))
        p.fillRect(1,7,3,3,QColor('#885522'));p.fillRect(10,25,3,3,QColor('#885522'));p.end()
        source.files[path]=png(anim);metadata=b'{"animation":{"frametime":2,"frames":[0,1,0]}}';source.files[path+'.mcmeta']=metadata
        w.clear_editor();open_path(path);canvas.selection_region=QRegion(1,1,4,4);canvas.sync_selection();panel.scope.setCurrentIndex(2);panel.prepare_frames()
        assert len(panel.frames)==2 and panel.frames[1]['mask'].contains(QPoint(11,3)) and not panel.frames[1]['mask'].contains(QPoint(2,2))
        try:panel.preview()
        except ValueError:pass
        else:raise AssertionError('Unreviewed frames applied')
        for index in range(len(panel.frames)):
            panel.frame_choice.setCurrentIndex(index);panel.review_frame()
        before=dict(source.files);history=len(canvas.history);panel.preview();assert source.files==before
        panel.apply();modified=decode(source.files[path]);assert len(canvas.history)==history+1
        assert modified.pixelColor(2,2)!=anim.pixelColor(2,2) and modified.pixelColor(11,19)!=anim.pixelColor(11,19)
        assert modified.pixelColor(2,8)==anim.pixelColor(2,8) and modified.pixelColor(11,26)==anim.pixelColor(11,26)
        assert source.files[path+'.mcmeta']==metadata and set(source.files)==set(before)
        canvas.undo();assert decode(source.files[path])==anim
        canvas.redo();assert decode(source.files[path])==modified
        # Real 19-frame mace preview, manual review simulated by test (not accuracy proof).
        pack=import_pack(ROOT/'reference/V3.2/重锤风弹动图.zip');real=next(p for p in pack.files if p.endswith('/mace.png'))
        source.files.update(pack.files);open_path(real);w.smart_region_panel.analyze();w.smart_region_panel.adopt()
        panel.scope.setCurrentIndex(2);panel.prepare_frames();assert len(panel.frames)==19
        for index in range(len(panel.frames)):
            panel.frame_choice.setCurrentIndex(index)
            if panel.frames[index]['mask'].isEmpty():panel.include.setChecked(False)
            else:panel.review_frame()
        panel.preview();app.processEvents();w.grab().save(str(ROOT/'.tmp/v32-recolor-ui.png'))
        assert source.files[real]==pack.files[real]
        # Existing semantic bindings keep related state patches in their own files.
        p1='assets/minecraft/textures/gui/sprites/hud/experience_bar_background.png'
        p2='assets/minecraft/textures/gui/sprites/hud/experience_bar_progress.png'
        source.files[p1]=png(gui);source.files[p2]=png(gui)
        bindings=[{'path':p1,'region':[0,0,.5,.5]},{'path':p2,'region':[.5,.5,.5,.5]}]
        group={'origin':source.uid,'kind':'component','path':p1,'name':'linked states','regions':[b['region'] for b in bindings],'bindings':bindings}
        w.edit_descriptor(group);panel.scope.setCurrentIndex(1);panel.preview();panel.apply()
        for pth in (p1,p2):assert decode(source.files[pth])!=gui
        assert decode(source.files[p1]).pixelColor(30,30)==gui.pixelColor(30,30)
        assert decode(source.files[p2]).pixelColor(1,1)==gui.pixelColor(1,1)
        canvas.undo();assert decode(source.files[p1])==gui and decode(source.files[p2])==gui
        w.add_to_composition(group);layer=w.layers[0];w.edit_descriptor({**group,'origin':'stage:'+layer.uid})
        panel.preview();panel.apply();assert source.files[p1]==png(gui) and source.files[p2]==png(gui)
        assert decode(layer.files['0'])!=gui.copy(0,0,16,16)
        canvas.undo();assert decode(layer.files['0'])==gui.copy(0,0,16,16)
        source.read_only=True;open_path(p1)
        try:panel.preview()
        except ValueError:pass
        else:raise AssertionError('Read-only recolor allowed')
        source.read_only=False
        print('PASS preview/cancel, apply undo-redo, stale controls, atlas boundary, independent moving-frame masks, metadata, real 19-frame preview')
        print('PASS multi-file component states, neighboring icons, project copy isolation and read-only guard')
    finally:w.dirty=False;w.close();app.processEvents()
