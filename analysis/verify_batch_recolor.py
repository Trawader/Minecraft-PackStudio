"""Batch scopes, atomic preview/apply/undo, frame and source isolation."""
import os,sys,tempfile,json,time
from pathlib import Path
from threading import Event
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QImage,QColor,QRegion,QPainter,QFont,QFontDatabase
from PySide6.QtWidgets import QApplication
from packstudio.core import Layer,png,decode,import_pack
from packstudio.recolor import Settings
from packstudio.batch_recolor import targets,plan,preview_files,apply_batch,undo_batch
from packstudio.batch_recolor_dialog import BatchRecolorDialog
from packstudio.studio import StudioWindow
app=QApplication([])
for font in ('segoeui.ttf','msyh.ttc'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
app.setFont(QFont('Microsoft YaHei',9))
image=QImage(16,16,QImage.Format.Format_ARGB32);image.fill(QColor('#2288cc'));image.setPixelColor(0,0,QColor(40,80,180,70));image.setPixelColor(15,15,QColor(12,34,56,0))
a='assets/minecraft/textures/block/glass.png';b='assets/minecraft/textures/block/glass_pane_top.png';c='assets/minecraft/textures/item/sword.png';other='assets/minecraft/textures/blocks-extra/untouched.png'
files={a:png(image),b:png(image),c:png(image),other:png(image),'pack.mcmeta':b'{"pack":{"pack_format":15}}','assets/minecraft/models/block/glass.json':b'{"textures":{"all":"minecraft:block/glass"}}','assets/minecraft/sounds/a.ogg':b'OggS unchanged'}
source=Layer('fixture',files);root={'origin':source.uid,'kind':'root','path':'','name':'fixture'}
folder={**root,'kind':'folder','path':'assets/minecraft/textures/block'}
assert set(targets(source,folder))=={a,b}
family={**root,'kind':'resource_group','resource_paths':[a,a,b,'assets/minecraft/models/block/glass.json']}
assert set(targets(source,family))=={a,b}
settings=Settings(mode='adjust',saturation=-50,contrast=10)
units,baseline,metadata,errors=plan(source,family);assert len(units)==2 and not errors
before=dict(files);output=preview_files(units,baseline,settings);assert source.files==before and set(output)=={a,b}
for path,raw in output.items():
    changed=decode(raw)
    for y in range(16):
        for x in range(16):assert changed.pixelColor(x,y).alpha()==image.pixelColor(x,y).alpha()
cancel=Event();cancel.set()
try:preview_files(units,baseline,settings,cancel)
except InterruptedError:pass
else:raise AssertionError('Cancelled preview continued')
binding={**root,'kind':'component','bindings':[{'path':a,'region':[0,0,.5,.5]},{'path':a,'region':[0,0,.5,.5]}]}
parts,base,meta,_=plan(source,binding);assert len(parts)==1
changed=decode(preview_files(parts,base,settings)[a]);assert changed.pixelColor(10,10)==image.pixelColor(10,10)
animation=QImage(16,32,QImage.Format.Format_ARGB32);animation.fill(Qt.GlobalColor.transparent);p=QPainter(animation)
p.fillRect(1,1,4,4,QColor('#2288cc'));p.fillRect(10,18,4,4,QColor('#2288cc'));p.fillRect(1,7,3,3,QColor('#884422'));p.fillRect(10,25,3,3,QColor('#884422'));p.end()
source.files[c]=png(animation);source.files[c+'.mcmeta']=b'{"animation":{"frames":[0,1,0],"frametime":3}}'
frames,base,meta,_=plan(source,{**root,'kind':'png','path':c});assert len(frames)==2 and not frames[1].reviewed
try:preview_files(frames,base,settings)
except ValueError:pass
else:raise AssertionError('Unreviewed frames processed')
frames[0].mask=QRegion(1,1,4,4);frames[1].mask=QRegion(10,2,4,4)
for frame in frames:frame.reviewed=True
changed=decode(preview_files(frames,base,Settings())[c]);assert changed.pixelColor(11,19)!=animation.pixelColor(11,19)
assert changed.pixelColor(11,26)==animation.pixelColor(11,26) and source.files[c+'.mcmeta']==meta[c+'.mcmeta']
print('PASS folder boundary, family dedup, config/audio/alpha preservation, cancellation, component union and independently masked frames')

with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='batch-') as tmp:
    os.environ['PACKSTUDIO_SETTINGS_FILE']=tmp+'/settings.ini';os.environ['PACKSTUDIO_NAMING_FILE']=tmp+'/names.json'
    w=StudioWindow(Path(tmp)/'library',drafts=False);w.show();app.processEvents()
    try:
        w.sources=[source];w.refresh();original=dict(source.files)
        units,baseline,metadata,_=plan(source,family);output=preview_files(units,baseline,settings)
        with patch.object(w.library_store,'put',side_effect=OSError('write failed')):
            try:apply_batch(w,source.uid,source,baseline,metadata,output)
            except OSError:pass
            else:raise AssertionError('Failed save ignored')
        assert source.files==original and not getattr(w,'batch_recolor_history',[])
        assert apply_batch(w,source.uid,source,baseline,metadata,output)==2
        assert all(source.files[p]==raw for p,raw in original.items() if p not in (a,b))
        source.files[a]=png(image.copy(0,0,8,8))
        try:undo_batch(w)
        except ValueError:pass
        else:raise AssertionError('Undo overwrote later edit')
        source.files[a]=output[a];assert undo_batch(w)==2 and source.files==original
        source.files[a+'.mcmeta']=b'{"texture":{}}'
        try:apply_batch(w,source.uid,source,baseline,metadata,output)
        except ValueError:pass
        else:raise AssertionError('Stale metadata accepted')
        del source.files[a+'.mcmeta']
        project=Layer('copy',dict(source.files));w.layers=[project]
        units,base,meta,_=plan(project,family);result=preview_files(units,base,settings)
        assert apply_batch(w,'stage:'+project.uid,project,base,meta,result)==2 and source.files==original
        assert undo_batch(w)==2 and project.files==original
        for descriptor in (root,folder,family,{**root,'kind':'game_object','object_paths':[a,b]},binding):
            menu=w.resource_menu(descriptor);assert any(action.text()=='批量调色…' for action in menu.actions());menu.deleteLater()
        dialog=BatchRecolorDialog(w,family);dialog.show();dialog.fields['saturation'].setValue(-50);dialog.generate()
        deadline=time.monotonic()+10
        while dialog.future and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
        assert dialog.output and dialog.apply_button.isEnabled() and source.files==original
        available=dialog.screen().availableGeometry()
        assert dialog.width()<=available.width()-16 and dialog.height()<=available.height()-40,(dialog.size(),available)
        assert dialog.rect().contains(dialog.apply_button.mapTo(dialog,dialog.apply_button.rect().center()))
        dialog.list.setCurrentRow(1);assert dialog.canvas.color_preview is not None
        dialog.show_original.setChecked(True);assert dialog.canvas.color_preview is None
        dialog.show_original.setChecked(False);dialog.grab().save(str(ROOT/'.tmp/v32-batch-preview.png'))
        from PySide6.QtWidgets import QMessageBox
        with patch.object(QMessageBox,"question",return_value=QMessageBox.StandardButton.Cancel):
            dialog.apply();assert source.files==original and dialog.output
        with patch.object(QMessageBox,"question",return_value=QMessageBox.StandardButton.Yes):dialog.apply()
        assert source.files[a]!=original[a];undo_batch(w);assert source.files==original
        dialog=BatchRecolorDialog(w,{**root,'kind':'png','path':c});dialog.show()
        assert dialog.units[0].animated and not dialog.units[0].reviewed and not dialog.units[0].mask.isEmpty()
        dialog.confirm_region();assert dialog.row==1;dialog.confirm_region();dialog.fields['saturation'].setValue(-40);dialog.generate()
        deadline=time.monotonic()+10
        while dialog.future and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
        assert dialog.output and source.files==original;dialog.reject()
        print('PASS atomic persistence failure, whole undo, later-edit/stale metadata guards, project isolation, all menu scopes, async dialog preview and frame review')
    finally:w.dirty=False;w.close();app.processEvents()

pack=import_pack(next((ROOT/'reference/V3.2').glob('*Blue*.zip')))
group={'kind':'folder','path':'assets/minecraft/textures/items'}
real,raw,meta,errors=plan(pack,group)
if not real:real,raw,meta,errors=plan(pack,{'kind':'root'})
sample=real[:8]
for unit in sample:
    if unit.animated:unit.included=False
out=preview_files(sample,raw,Settings(mode='adjust',saturation=-25))
assert out and all(pack.files[p]==raw[p] for p in out)
print('PASS real Blue pack batch preview',len(out),'PNGs; original pack unchanged')
