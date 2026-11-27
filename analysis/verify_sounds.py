"""Sound composition, source integrity, UI playback wiring and real OGG decoding."""
import os,sys,json,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt,QBuffer,QByteArray,QIODevice,QEventLoop,QTimer
from PySide6.QtWidgets import QApplication,QDockWidget
from PySide6.QtGui import QFontDatabase,QFont
from PySide6.QtMultimedia import QAudioDecoder,QMediaPlayer
from PySide6.QtTest import QTest
from packstudio.core import Layer,Vanilla,import_pack,compose,save_project,load_project,write_zip
from packstudio.sounds import merge,parse,reference_issues
from packstudio.resource_graph import ResourceGraph
from packstudio.export_dialog import prepare_files,defaults
from packstudio.studio import StudioWindow
app=QApplication([]);v=Vanilla();definition='assets/minecraft/sounds.json'
for font in ('segoeui.ttf','msyh.ttc'):
    font_path=Path('C:/Windows/Fonts')/font
    if font_path.exists():QFontDatabase.addApplicationFont(str(font_path))
app.setFont(QFont('Microsoft YaHei',9))
def encoded(value):return json.dumps(value).encode()
packs=[import_pack(ROOT/'reference/V3.2'/name) for name in ('音效包1.zip','音效包2.zip')]
paths=[set(p.files) for p in packs];common=next(p for p in sorted(paths[0]&paths[1]) if p.endswith('.ogg') and packs[0].files[p]!=packs[1].files[p])
files,_=compose(packs,v,'1.8.9');assert files[common]==packs[0].files[common]
assert set(files)==paths[0]|paths[1]
for mode in ('unchanged','1.8.9','1.21.11'):
    base=defaults(packs);out=prepare_files(packs,v,'1.8.9',base,mode,base['title'],base['body'],base['cover'],'keep')
    assert all(out[p]==raw for p,raw in files.items() if p.endswith('.ogg'))
print('PASS real packs: 89/112 OGG, priority and no-loss exports across formats')

a='assets/minecraft/sounds/custom/a.ogg';b='assets/minecraft/sounds/custom/b.ogg';raw1=packs[0].files[common];raw2=packs[1].files[common]
low=Layer('low',{definition:encoded({'hit':{'sounds':['custom/a'],'replace':True},'low_only':{'sounds':['custom/a']}}),a:raw1})
high=Layer('high',{definition:encoded({'hit':{'sounds':[{'name':'custom/b','volume':.8}]},'high_only':{'sounds':['custom/b']}}),b:raw2})
out,_=compose([high,low],v,'1.8.9');data=parse(out[definition],definition)
assert set(data)=={'hit','low_only','high_only'} and len(data['hit']['sounds'])==2 and data['hit']['replace']
assert not reference_issues(out)
for mode in ('unchanged','1.8.9','1.21.11'):
    base=defaults([high,low]);exported=prepare_files([high,low],v,'1.8.9',base,mode,'','',None,'keep')
    assert parse(exported[definition],definition)==data and exported[a]==raw1 and exported[b]==raw2
replacement=encoded({'hit':{'replace':True,'sounds':['custom/b']}})
assert parse(merge(low.files[definition],replacement,definition),definition)['hit']['sounds']==['custom/b']
try:merge(encoded({'hit':{'subtitle':'a','sounds':[]}}),encoded({'hit':{'subtitle':'b','sounds':[]}}),definition)
except ValueError as e:assert 'hit' in str(e)
else:raise AssertionError('Unsafe conflict silently accepted')
malformed=Layer('opaque',{definition:b'not-json'})
assert compose([malformed],v,'1.8.9')[0][definition]==b'not-json' and reference_issues(malformed.files)
try:compose([high,malformed],v,'1.8.9')
except ValueError:pass
else:raise AssertionError('Malformed collision accepted')
high.enabled=False;assert compose([high,low],v,'1.8.9')[0]==low.files;high.enabled=True
graph=ResourceGraph(out).parse();selected,missing=graph.closure([a]);assert selected==set(out) and not missing
cycle={definition:encoded({'a':{'sounds':[{'name':'b','type':'event'}]},'b':{'sounds':[{'name':'a','type':'event'}]}})}
assert any('循环' in row['detail'] for row in reference_issues(cycle))
assert reference_issues({definition:encoded({'missing':{'sounds':['custom/missing']}})})
print('PASS definition union, replace semantics, unsafe/malformed conflicts, references and cycles')

with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='sounds-') as tmp:
    os.environ['PACKSTUDIO_SETTINGS_FILE']=tmp+'/settings.ini';os.environ['PACKSTUDIO_NAMING_FILE']=tmp+'/names.json'
    w=StudioWindow(Path(tmp)/'library',drafts=False);w.show();app.processEvents()
    try:
        source=Layer('sounds fixture',dict(out));w.sources=[source];w.refresh()
        dock_count=len(w.findChildren(QDockWidget));menu_count=len(w.window_menu.actions())
        descriptor={'origin':source.uid,'kind':'file','path':a,'name':'a.ogg'}
        w.edit_descriptor(descriptor);panel=w.audio_preview;panel.output.setMuted(True)
        assert panel.descriptor['path']==a and panel.buffer.isOpen()
        assert w.preview_stack.currentWidget() is panel and not w.preview_panel.isVisible()
        assert w.docks['render'].isAncestorOf(panel) and not panel.isWindow()
        assert len(w.findChildren(QDockWidget))==dock_count and len(w.window_menu.actions())==menu_count
        states=[];panel.player.playbackStateChanged.connect(states.append);panel.play()
        deadline=time.monotonic()+5
        while time.monotonic()<deadline and QMediaPlayer.PlaybackState.PlayingState not in states:
            QTest.qWait(20)
        assert QMediaPlayer.PlaybackState.PlayingState in states,panel.player.errorString()
        panel.stop();assert panel.player.playbackState()==QMediaPlayer.PlaybackState.StoppedState
        w.add_to_composition(descriptor);shadow=w.layers[0];before=dict(shadow.files)
        assert a in shadow.files and b in shadow.files and definition in shadow.files
        panel.replace_bytes(raw2);assert source.files[a]==raw2 and shadow.files==before
        assert set(source.files)==set(out)
        panel.stop();w.edit_descriptor({'origin':source.uid,'kind':'root','path':'','name':source.name})
        assert panel.player.playbackState()==panel.player.PlaybackState.StoppedState
        assert w.preview_stack.currentWidget() is w.preview_panel and not panel.isVisible()
        save_project(Path(tmp)/'sound.packstudio',w.layers,'1.8.9');restored,_=load_project(Path(tmp)/'sound.packstudio');assert restored[0].files==before
        write_zip(Path(tmp)/'sound.zip',before);assert import_pack(Path(tmp)/'sound.zip').files==before
        # Detached project audio edit preserves the library source and target path.
        w.edit_descriptor({**descriptor,'origin':'stage:'+shadow.uid});panel.replace_bytes(raw1)
        assert source.files[a]==raw2 and shadow.files[a]==raw1
        # File tree, selector category and project context menu all expose audio.
        source.files['pack.mcmeta']=encoded({'pack':{'pack_format':1,'description':'sound fixture'}})
        w.library_mode.setCurrentIndex(1);w.refresh()
        assert any(item.text(0)=='音效' for item in w.tree_items.values())
        assert any((item.data(0,Qt.ItemDataRole.UserRole) or {}).get('path')==a for item in w.tree_items.values())
        w.selected_asset={'files':{b:raw2},'kind':'pack'};w.replace_with_selected({**descriptor,'origin':'stage:'+shadow.uid})
        assert shadow.files[a]==raw2
        app.processEvents();w.grab().save(str(ROOT/'.tmp/v32-sound-preview.png'))
        # Hide/show and reset operate on the same pre-existing preview dock.
        w.docks['render'].hide();assert panel.player.playbackState()==QMediaPlayer.PlaybackState.StoppedState
        w.docks['render'].show();assert w.preview_stack.currentWidget() is panel
        w.reset_layout();assert len(w.findChildren(QDockWidget))==dock_count
        texture='assets/minecraft/textures/blocks/stone.png';source.files[texture]=v.get('1.8.9',texture)
        w.edit_descriptor({'origin':source.uid,'kind':'png','path':texture,'name':'stone.png'})
        assert w.preview_stack.currentWidget() is w.preview_panel and w.preview_panel.isVisible() and not panel.isVisible()
        model=w.model_key;zoom=w.preview.zoom
        w.edit_descriptor(descriptor);w.edit_descriptor({'origin':source.uid,'kind':'png','path':texture,'name':'stone.png'})
        assert w.model_key==model and w.preview.zoom==zoom and len(w.findChildren(QDockWidget))==dock_count
    finally:w.dirty=False;w.close();app.processEvents()
print('PASS preview UI, source/project independence, replacement paths, project and ZIP roundtrip')

for pack in packs:
    raw=next(raw for path,raw in pack.files.items() if path.endswith('.ogg'))
    device=QBuffer();device.setData(QByteArray(raw));device.open(QIODevice.OpenModeFlag.ReadOnly)
    decoder=QAudioDecoder();decoder.setSourceDevice(device);loop=QEventLoop();decoded=[];errors=[]
    decoder.bufferReady.connect(lambda:decoded.append(decoder.read().byteCount()))
    decoder.finished.connect(loop.quit);decoder.error.connect(lambda error:(errors.append(decoder.errorString()),loop.quit()))
    timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(loop.quit);timer.start(10000)
    decoder.start();loop.exec();decoder.stop();timer.stop()
    assert decoded and sum(decoded)>0 and not errors,errors
print('PASS both supplied OGG packs decoded to PCM without audio output')
