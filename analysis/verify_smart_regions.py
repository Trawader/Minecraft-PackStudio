"""Candidate masks, review/cancel/adopt, history, real assets and frame isolation."""
import os,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QImage,QColor,QPainter,QRegion,QFont,QFontDatabase
from PySide6.QtWidgets import QApplication,QDockWidget
from packstudio.smart_regions import analyze
from packstudio.core import Layer,import_pack,png,decode
from packstudio.studio import StudioWindow
app=QApplication([])
for font in ('segoeui.ttf','msyh.ttc'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
app.setFont(QFont('Microsoft YaHei',9))
im=QImage(16,16,QImage.Format.Format_ARGB32);im.fill(Qt.GlobalColor.transparent)
p=QPainter(im);p.fillRect(6,1,5,8,QColor('#2277cc'));p.fillRect(6,1,1,6,QColor('#5588dd'))
p.fillRect(8,2,1,2,QColor('#ffffff'));p.fillRect(7,10,3,5,QColor('#825522'));p.fillRect(5,9,7,1,QColor('#161616'));p.end()
candidates=analyze(im);blue=next(c for c in candidates if c.region.contains(QPoint(7,3)))
assert not blue.region.contains(QPoint(8,12)) and not blue.region.contains(QPoint(5,9))
assert not blue.region.contains(QPoint(8,2)) and blue.highlights.contains(QPoint(8,2))
assert any(c.region.contains(QPoint(8,2)) for c in candidates if '白色' in c.label)
assert not analyze(QImage())
white=QImage(im);p=QPainter(white);p.fillRect(6,1,5,8,QColor('#eeeeee'));p.end()
assert analyze(white)[0].region.contains(QPoint(8,4))
faint=QImage(16,16,QImage.Format.Format_ARGB32);faint.fill(QColor(255,255,255,1))
assert not analyze(faint)
for c in candidates:
    for y in range(16):
        for x in range(16):
            if c.region.contains(QPoint(x,y)):assert im.pixelColor(x,y).alpha()>0
print('PASS colored material/handle separation, dark edge protection, optional highlights, white candidates, transparent exclusion')

samples=[]
for name in ('*Tsuki*.zip','Everest*.zip','*Blue*.zip'):
    pack=import_pack(next((ROOT/'reference/V3.2').glob(name)))
    for stem in ('diamond_sword.png','diamond_helmet.png'):
        path=next((p for p in pack.files if p.endswith('/'+stem)),None)
        if path:samples.append((pack.name+' / '+stem,decode(pack.files[path])))
sheet=QImage(560,len(samples)*190,QImage.Format.Format_ARGB32);sheet.fill(QColor('#303030'));p=QPainter(sheet)
try:
    for index,(name,image) in enumerate(samples):
        start=time.perf_counter();found=analyze(image);assert found
        for candidate in found:
            for y in range(image.height()):
                for x in range(image.width()):
                    if candidate.region.contains(QPoint(x,y)):assert image.pixelColor(x,y).alpha()>=16
        print('SAMPLE',name,image.width(),image.height(),len(found),'candidates',round(time.perf_counter()-start,3),'s')
        overlay=QImage(image);q=QPainter(overlay);q.setClipRegion(found[0].region);q.fillRect(image.rect(),QColor(0,210,235,120));q.end()
        y=index*190;p.setPen(QColor('white'));p.drawText(8,y+17,name[:68]);p.drawText(285,y+37,found[0].label)
        p.drawImage(20,y+40,image.scaled(144,144,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation))
        p.drawImage(300,y+40,overlay.scaled(144,144,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation))
finally:p.end()
sheet.save(str(ROOT/'.tmp/v32-smart-region-samples.png'))

with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='smart-region-') as tmp:
    os.environ['PACKSTUDIO_SETTINGS_FILE']=tmp+'/settings.ini';os.environ['PACKSTUDIO_NAMING_FILE']=tmp+'/names.json'
    w=StudioWindow(Path(tmp)/'library',drafts=False);w.show();app.processEvents()
    try:
        path='assets/minecraft/textures/item/diamond_sword.png';source=Layer('candidate fixture',{path:png(im)})
        w.sources=[source];w.refresh();w.edit_descriptor({'origin':source.uid,'kind':'png','path':path,'name':'sword'})
        panel=w.smart_region_panel;canvas=w.canvas;count=len(w.findChildren(QDockWidget));original=dict(source.files)
        canvas.selection_region=QRegion(7,11,1,1);canvas.sync_selection();previous=QRegion(canvas.selection_region)
        history=len(canvas.history);panel.analyze()
        assert canvas.selection_region==previous and len(canvas.history)==history and source.files==original
        without=QRegion(canvas.candidate_region);panel.protect.setChecked(False)
        assert canvas.candidate_region.contains(QPoint(8,2)) and canvas.candidate_region!=without
        panel.protect.setChecked(True);assert canvas.candidate_region==without
        panel.reset();assert canvas.selection_region==previous and canvas.candidate_region.isEmpty()
        panel.analyze();chosen=QRegion(canvas.candidate_region);panel.adopt()
        assert canvas.selection_region==chosen and len(canvas.history)==history+1 and source.files==original
        canvas.undo();assert canvas.selection_region==previous
        canvas.redo();assert canvas.selection_region==chosen
        canvas.undo();future=len(canvas.future);panel.analyze();panel.reset();assert len(canvas.future)==future
        canvas.redo()
        panel.analyze();canvas.set_atlas(canvas.image,[(0,0,8,8)],(source.uid,path));assert not panel.candidates and canvas.candidate_region.isEmpty()
        panel.analyze();assert all(c.region.boundingRect().right()<8 and c.region.boundingRect().bottom()<8 for c in panel.candidates)
        panel.manual_selection();assert canvas.tool=='select' and not panel.candidates
        w.edit_descriptor({'origin':source.uid,'kind':'png','path':path,'name':'sword'});w.load_canvas();panel.analyze()
        app.processEvents();w.grab().save(str(ROOT/'.tmp/v32-smart-region-ui.png'))
        assert len(w.findChildren(QDockWidget))==count
        panel.analyze();canvas.changed.emit();assert not panel.candidates and canvas.candidate_region.isEmpty()
        w.clear_editor();assert not panel.candidates
        print('PASS preview/cancel non-destructive, adoption undo/redo, atlas isolation, view invalidation, manual entry, no new dock')
    finally:w.dirty=False;w.close();app.processEvents()
