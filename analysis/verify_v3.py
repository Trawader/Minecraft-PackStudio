"""Isolated V3 interaction, resource integrity and performance regression checks."""
import os,sys,json,time,tempfile,traceback,cProfile,pstats,io
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt,QPointF,QPoint,QEvent
from PySide6.QtGui import QImage,QColor,QMouseEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from packstudio.canvas import Canvas
from packstudio.core import Layer,Vanilla,import_pack,png
from packstudio.game_objects import entries
from packstudio.color_editor import ColorEditor
from packstudio.studio import StudioWindow

app=QApplication([]);results=[];metrics={}
def check(name,fn):
    start=time.perf_counter()
    try:fn();result={'name':name,'status':'PASS'}
    except Exception:result={'name':name,'status':'FAIL','traceback':traceback.format_exc()}
    result['seconds']=round(time.perf_counter()-start,4);results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
def mouse(c,kind,point,button,buttons,modifiers=Qt.KeyboardModifier.NoModifier):
    event=QMouseEvent(kind,QPointF(point[0]+.5,point[1]+.5),QPointF(point[0]+.5,point[1]+.5),button,buttons,modifiers)
    QApplication.sendEvent(c,event)
def drag(c,a,b,button=Qt.MouseButton.LeftButton,modifiers=Qt.KeyboardModifier.NoModifier):
    mouse(c,QEvent.Type.MouseButtonPress,a,button,button,modifiers)
    mouse(c,QEvent.Type.MouseMove,b,Qt.MouseButton.NoButton,button,modifiers)
    mouse(c,QEvent.Type.MouseButtonRelease,b,button,Qt.MouseButton.NoButton,modifiers)
def canvas():
    c=Canvas();im=QImage(8,8,QImage.Format.Format_ARGB32);im.fill(QColor(100,120,140,255));c.set_image(im);c.zoom=1;c.offset=QPointF();return c
def selection():
    c=canvas();c.set_tool('select');drag(c,(0,0),(2,2));drag(c,(4,0),(5,1),modifiers=Qt.KeyboardModifier.ShiftModifier);drag(c,(1,1),(1,1),modifiers=Qt.KeyboardModifier.AltModifier)
    assert c.selection_region.contains(QPoint(4,1)) and not c.selection_region.contains(QPoint(1,1))
    assert sum(w*h for x,y,w,h in c.selection_rectangles())==12
    c.set_tool('pencil');c.color=QColor('red');drag(c,(0,1),(7,1))
    assert c.pixel((0,1))==QColor('red') and c.pixel((1,1))==QColor(100,120,140) and c.pixel((7,1))==QColor(100,120,140)
    c.set_tool('bucket');c.color=QColor('green');drag(c,(2,2),(2,2));assert c.pixel((7,7))==QColor(100,120,140)
    c.grab();c.set_image(c.image);assert c.selection is None
def movement():
    c=canvas();c.set_pixel((0,0),QColor('red'));c.set_pixel((1,0),QColor(0,0,0,0));c.set_tool('select');drag(c,(0,0),(1,0));c.set_tool('mouse');drag(c,(0,0),(3,2))
    assert c.pixel((0,0))==QColor('red') # pending drag does not mutate
    c.grab();QTest.keyClick(c,Qt.Key.Key_Return)
    assert c.pixel((3,2))==QColor('red') and c.pixel((4,2)).alpha()==0 and c.pixel((0,0)).alpha()==0 and c.selection is None
    c.undo();assert c.pixel((0,0))==QColor('red') and c.pixel((3,2))==QColor(100,120,140)
    c.set_tool('select');drag(c,(1,1),(2,2));QTest.mouseDClick(c,Qt.MouseButton.LeftButton,pos=QPoint(1,1));assert c.selection is not None
def tones():
    for tool in ('burn','dodge','lighten','darken'):
        c=canvas();c.set_tool('select');drag(c,(0,0),(0,0));c.set_tool(tool);drag(c,(0,0),(3,0))
        assert c.pixel((0,0))!=QColor(100,120,140) and c.pixel((0,0)).alpha()==255 and c.pixel((1,0))==QColor(100,120,140)
        c.undo();assert c.pixel((0,0))==QColor(100,120,140)
def colors():
    d=ColorEditor(QColor(200,100,50,123));d.fields['HSVA'][0].setValue(120);assert d.color.green()>d.color.red() and d.color.alpha()==123
    d.choose_swatch(QColor('blue'));assert d.fields['RGBA'][2].value()==255 and d.color.alpha()==123
    d.show();app.processEvents();assert not d.grab().isNull();d.close()

ROOT.joinpath('.tmp').mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='v3-check-') as tmp:
    os.environ['PACKSTUDIO_SETTINGS_FILE']=str(Path(tmp)/'settings.ini');os.environ['PACKSTUDIO_NAMING_FILE']=str(Path(tmp)/'names.json')
    check('selection_mask_and_clipped_paint',selection);check('move_transparency_enter_undo_doubleclick',movement);check('four_tone_tools',tones);check('rgba_hsva_palette',colors)
    w=StudioWindow(Path(tmp)/'library',drafts=False);v=Vanilla()
    try:
        def objects():
            global sample
            sample=import_pack(ROOT/'test/b1ue 128x.zip');sample.source_version='1.8.9';w.sources=[sample]
            original=dict(sample.files);profile=cProfile.Profile();profile.enable();start=time.perf_counter();rows=entries(sample,'1.8.9');metrics['selector_cold_ms']=(time.perf_counter()-start)*1000;profile.disable()
            stream=io.StringIO();pstats.Stats(profile,stream=stream).sort_stats('cumulative').print_stats(22);(ROOT/'analysis/v3-profile.txt').write_text(stream.getvalue(),'utf8')
            start=time.perf_counter();assert entries(sample,'1.8.9') is rows;metrics['selector_cached_ms']=(time.perf_counter()-start)*1000
            assert all('elytra' not in row['id'] for row in rows)
            assert sample.files==original
            assert all(set(row['paths'])<=sample.files.keys() for row in rows)
            assert any('羊毛家族' in row['category'] for row in rows)
            shelf=next(row for row in rows if row['id']=='minecraft:block/bookshelf');assert not shelf['resolved_states']
            start=time.perf_counter();w.library_mode.setCurrentIndex(1);w.refresh();metrics['selector_widgets_ms']=(time.perf_counter()-start)*1000
            assert any((item.data(0,Qt.ItemDataRole.UserRole) or {}).get('kind')=='component' for item in w.tree_items.values())
            w.show();app.processEvents();assert not w.grab().isNull()
        check('selector_real_pack_integrity_and_widgets',objects)
        def preview():
            from packstudio.object_catalog import object_entity_paths
            from packstudio.selector_taxonomy import category
            names=['assets/minecraft/textures/items/leather_helmet.png','assets/minecraft/textures/models/armor/leather_layer_1.png','assets/minecraft/textures/items/boat.png','assets/minecraft/textures/entity/boat.png']
            owner=Layer('fixture',{p:v.get('1.8.9',p) for p in names if v.get('1.8.9',p)},source_version='1.8.9');w.sources=[owner]
            assert 'assets/minecraft/textures/entity/boat.png' in object_entity_paths(owner,'item/oak_boat')
            row=next(r for r in entries(owner,'1.8.9') if r['id']=='minecraft:item/leather_helmet')
            d={'origin':owner.uid,'kind':'game_object','path':'@object/'+row['id'],'object_id':row['id'],'name':row['name'],'object_paths':row['paths'],'preview_path':row['preview']}
            w.edit_descriptor(d);assert '/item/' in w.model_key
            armor=names[1];w.edit_descriptor({'origin':owner.uid,'kind':'png','path':armor,'name':'armor','_object_context':d})
            assert w.model_key=='armor:helmet' and len(w.preview.faces)==6
            assert w.resource_editors.object_descriptor['object_id']==d['object_id']
            assert category('item/bow',names[0])[:2]==('战斗','武器')
            assert w.docks['editor'].widget().isAncestorOf(w.resource_editors.dock)
            w.reset_layout();assert w.resource_editors.dock.isHidden()
        check('object_links_armor_preview_and_embedded_strip',preview)
    finally:w.dirty=False;w.close();app.processEvents()
report={'checks':results,'metrics':metrics,'status':'PASS' if all(r['status']=='PASS' for r in results) else 'FAIL'}
(ROOT/'analysis/v3-regression.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
print(json.dumps(metrics,ensure_ascii=False),flush=True)
sys.exit(0 if report['status']=='PASS' else 1)
