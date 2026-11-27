"""Algorithm and handler checks only: no QApplication or widget construction."""
import ast
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QImage, QColor, QRegion
from packstudio.canvas import Canvas
from packstudio.batch_recolor_dialog import BatchRecolorDialog
from packstudio.batch_recolor import Unit, preview_files
from packstudio.core import png, decode
from packstudio.recolor import Settings, render


def verify_adjustment_dispatch():
    for tool in ('recolor',):
        calls = []
        selection = QRegion(1, 1, 2, 2)
        state = SimpleNamespace(
            task_running=False, show_rulers=False, tool=tool, read_only=False,
            setFocus=lambda: None, pos=lambda event: (1, 1), valid=lambda p: True,
            selection_region=selection, selection_weights={(1, 1): 128},
            adjustmentRequested=SimpleNamespace(emit=lambda: calls.append('preview')),
        )
        event = SimpleNamespace(position=lambda: QPointF(10, 10),
                                button=lambda: Qt.MouseButton.LeftButton,
                                accept=lambda: calls.append('accepted'))
        # Missing stroke/history methods deliberately fail if dispatch falls through.
        Canvas.mousePressEvent(state, event)
        assert calls == ['preview', 'accepted']
        assert state.selection_region == selection and state.selection_weights == {(1, 1): 128}
        state.read_only = True
        calls.clear()
        Canvas.mousePressEvent(state, event)
        assert calls == ['accepted']


def verify_gradient_drag():
    calls=[];selection=QRegion(1,1,2,2)
    state=SimpleNamespace(task_running=False,show_rulers=False,tool='gradient',read_only=False,
        image=QImage(5,5,QImage.Format.Format_ARGB32),gradient_drag=None,
        setFocus=lambda:None,pos=lambda event:event.point,update=lambda:None,
        selection_region=selection,gradientRequested=SimpleNamespace(emit=lambda a,b:calls.append((a,b))))
    def event(point):
        return SimpleNamespace(point=point,position=lambda:QPointF(*point),
            button=lambda:Qt.MouseButton.LeftButton,accept=lambda:None)
    Canvas.mousePressEvent(state,event((-2,0)))
    assert calls==[] and state.gradient_drag==((-2,0),(-2,0))
    Canvas.mouseMoveEvent(state,event((3,4)))
    assert calls==[] and state.gradient_drag==((-2,0),(3,4))
    Canvas.mouseReleaseEvent(state,event((4,3)))
    assert calls==[((-2,0),(4,3))] and state.gradient_drag is None
    assert state.selection_region==selection
    calls.clear()
    Canvas.mousePressEvent(state,event((1,1)));Canvas.mouseReleaseEvent(state,event((1,1)))
    assert calls==[]
    state.read_only=True
    Canvas.mousePressEvent(state,event((1,1)))
    assert state.gradient_drag is None


def verify_gradients():
    original = QImage(5, 5, QImage.Format.Format_ARGB32)
    original.fill(QColor(30, 60, 90, 123))
    region = QRegion(1, 1, 3, 3)
    endpoints = {
        'down': ((1, 1), (1, 3)), 'up': ((1, 3), (1, 1)),
        'right': ((1, 1), (3, 1)), 'left': ((3, 1), (1, 1)),
        'diagonal': ((1, 1), (3, 3)), 'reverse_diagonal': ((3, 1), (1, 3)),
    }
    for direction, (start, end) in endpoints.items():
        output = render(original, region, Settings(mode='spatial', first='#000000', last='#ffffff', direction=direction))
        assert output.pixelColor(*start).red() == 0
        assert output.pixelColor(*end).red() == 255
        for y in range(5):
            for x in range(5):
                assert output.pixelColor(x, y).alpha() == 123
                if not region.contains(QPoint(x, y)):
                    assert output.pixelColor(x, y) == original.pixelColor(x, y)
        assert original.pixelColor(2, 2) == QColor(30, 60, 90, 123)
    for region in (QRegion(original.rect()),QRegion(1,1,3,3)):
        config=Settings(mode='spatial',first='#000000',last='#ffffff',start=(1,1),end=(3,1))
        output=render(original,region,config)
        assert [output.pixelColor(x,1).red() for x in (1,2,3)]==[0,128,255]
        for y in range(5):
            for x in range(5):
                assert output.pixelColor(x,y).alpha()==123
                if not region.contains(QPoint(x,y)):assert output.pixelColor(x,y)==original.pixelColor(x,y)


def verify_batch_events():
    state=SimpleNamespace(leaves={'a.png':SimpleNamespace(checkState=lambda column:Qt.CheckState.Checked),'b.png':SimpleNamespace(checkState=lambda column:Qt.CheckState.Unchecked)})
    assert BatchRecolorDialog.selected_paths(state)=={'a.png'}
    image = QImage(2, 2, QImage.Format.Format_ARGB32)
    image.fill(QColor(20, 40, 80, 150))
    included = Unit('a.png', (0, 0, 2, 2), QRegion(0, 0, 2, 2), mask=QRegion(0, 0, 2, 2))
    excluded = Unit('b.png', (0, 0, 2, 2), QRegion(0, 0, 2, 2), reviewed=False, included=False)
    baseline = {'a.png': png(image), 'b.png': png(image)}
    output = preview_files([included, excluded], baseline, Settings(mode='opacity', opacity=50))
    assert set(output) == {'a.png'} and decode(output['a.png']).pixelColor(0, 0).alpha() == 75
    assert decode(baseline['a.png']).pixelColor(0, 0).alpha() == 150


def verify_batch_scopes():
    from unittest.mock import patch
    image=QImage(5,3,QImage.Format.Format_ARGB32);image.fill(QColor(40,80,120,200))
    baseline={'atlas.png':png(image)}
    units=[Unit('atlas.png',(0,0,5,3),QRegion(0,0,5,3),mask=QRegion(x,1,2,1)) for x in (0,1)]
    for order in (units,list(reversed(units))):
        result=decode(preview_files(order,baseline,Settings(mode='opacity',opacity=50))['atlas.png'])
        for y in range(3):
            for x in range(5):assert result.pixelColor(x,y).alpha()==(100 if y==1 and x<3 else 200)


def verify_scoped_candidates():
    from packstudio.batch_recolor import region_candidates
    image=QImage(8,8,QImage.Format.Format_ARGB32);image.fill(QColor('red'))
    for x in (3,4):
        for y in (3,4):image.setPixelColor(x,y,QColor('blue'))
    allowed=QRegion(3,3,2,2)
    choices=region_candidates(image,allowed)
    assert choices and choices[0].region==allowed
    assert all(c.region.subtracted(allowed).isEmpty() for c in choices)
    assert image.pixelColor(0,0)==QColor('red')


def verify_brush_rgba():
    from packstudio.ui import Window
    stored={};swatches=[SimpleNamespace(setChecked=lambda value:None,set_color=lambda c:None)]
    canvas=SimpleNamespace()
    window=SimpleNamespace(canvas=canvas,color_button=swatches[0],palette_buttons=swatches,
        active_palette_index=0,settings=SimpleNamespace(setValue=lambda k,v:stored.update({k:v})))
    chosen=QColor(240,50,80,96)
    Window.set_color(window,chosen)
    assert canvas.color==chosen and QColor(stored['palette-v2/0'])==chosen
    image=QImage(8,8,QImage.Format.Format_ARGB32);image.fill(QColor(10,20,30,180))
    original=QImage(image);allowed=QRegion(1,1,4,4)
    state=SimpleNamespace(read_only=False,tool='pencil',brush_size=3,brush_opacity=255,color=chosen,
        selection_weights={(1,1):128},selection_visited=set(),amounts={},
        editable=lambda p:allowed.contains(QPoint(*p)),pixel=lambda p:image.pixelColor(*p),
        set_pixel=lambda p,c:image.setPixelColor(*p,c),update_pixels=lambda r:None,
        strokeUpdated=SimpleNamespace(emit=lambda:None))
    state.paint_pixel=lambda p,c:Canvas.paint_pixel(state,p,c)
    Canvas.stroke(state,(-1,-1),(3,3))
    assert image.pixelColor(3,3)==chosen
    soft=QColor(image.pixelColor(1,1))
    Canvas.stroke(state,(3,3),(1,1))
    assert image.pixelColor(1,1)==soft  # No repeated soft-mask blending within a stroke.
    assert decode(png(image))==image
    for y in range(8):
        for x in range(8):
            if not allowed.contains(QPoint(x,y)):assert image.pixelColor(x,y)==original.pixelColor(x,y)
    for brush_alpha in (0,128,255):
        state.brush_opacity=brush_alpha
        Canvas.stroke(state,(3,3),(3,3))
        assert image.pixelColor(3,3).alpha()==round(96*brush_alpha/255)
        assert state.color==chosen  # Brush alpha never overwrites the palette alpha.


def verify_transitions():
    from packstudio.gradient_transition import transition_value as value
    import math
    curve=((0.,0.),(.2,.05),(.7,.9),(1.,1.))
    for mode in ('linear','smooth','steps','curve'):
        for midpoint in (1,30,50,99):
            for width in (0,20,100):
                samples=[value(i/1000,midpoint,width,mode,5,curve) for i in range(1001)]
                assert samples[0]==0 and samples[-1]==1
                assert all(math.isfinite(v) and 0<=v<=1 for v in samples)
                assert samples==sorted(samples)
    assert value(.3,30)==.5
    assert value(.25,mode='smooth')<.25 and value(.75,mode='smooth')>.75
    assert len(set(value(i/1000,mode='steps',steps=5) for i in range(1001)))==5
    image=QImage(9,3,QImage.Format.Format_ARGB32);image.fill(QColor(10,20,30,96))
    region=QRegion(1,1,7,1)
    for mode in ('linear','smooth','steps','curve'):
        config=Settings(mode='spatial',start=(1,1),end=(7,1),transition=mode,midpoint=30,smooth=60,curve=curve)
        output=render(image,region,config)
        for y in range(3):
            for x in range(9):
                assert output.pixelColor(x,y).alpha()==96
                if not region.contains(QPoint(x,y)):assert output.pixelColor(x,y)==image.pixelColor(x,y)




def verify_resource_thumbnail_cache():
    from unittest.mock import patch
    from packstudio.resource_editors import ResourceEditors
    descriptor={'origin':'source','path':'item.png'};icons=[];decoded=[]
    item=SimpleNamespace(data=lambda role:descriptor,setIcon=icons.append)
    manager=SimpleNamespace(thumbnail_bytes={})
    with patch('packstudio.sky_view.thumbnail',side_effect=lambda raw,size:decoded.append(raw) or raw), \
         patch('packstudio.resource_editors.QPixmap',SimpleNamespace(fromImage=lambda value:value)), \
         patch('packstudio.resource_editors.QIcon',side_effect=lambda value=None:value):
        ResourceEditors.decorate_card(manager,item,b'original')
        ResourceEditors.decorate_card(manager,item,b'original')
        ResourceEditors.decorate_card(manager,item,b'edited')
        ResourceEditors.decorate_card(manager,item,b'original')  # Undo must refresh too.
    assert decoded==[b'original',b'edited',b'original'] and icons==decoded







def verify_single_canvas_routing():
    from packstudio.resource_editors import ResourceEditors
    calls=[]
    descriptor={'origin':'source','path':'item.png'}
    window=SimpleNamespace(source=lambda origin:SimpleNamespace(files={'item.png':b'png'}),edit_descriptor=calls.append)
    manager=SimpleNamespace(window=window)
    item=SimpleNamespace(data=lambda role:descriptor,icon=lambda:SimpleNamespace(isNull=lambda:False))
    ResourceEditors.pick(manager,item)
    assert calls==[descriptor]
    module=ast.parse((ROOT/'packstudio/resource_editors.py').read_text(encoding='utf-8'))
    assert {node.name for node in module.body if isinstance(node,ast.ClassDef)}=={'ResourceStrip','ResourceEditors','ResourceCards'}
    dock_source=(ROOT/'packstudio/dock_chrome.py').read_text(encoding='utf-8')
    assert 'cloneOnDrag' not in dock_source and 'detach_main' not in dock_source
    assert not (ROOT/'packstudio/editor_preview.py').exists()


def verify_material_reset():
    original=QImage(4,4,QImage.Format.Format_ARGB32);original.fill(QColor('red'))
    edited=QImage(original);edited.fill(QColor('blue'))
    for regions in (None,[(1,1,2,2)]):
        events=[]
        state=SimpleNamespace(read_only=False,drawing=False,task_running=False,image=QImage(edited),reset_image=original,regions=regions,
            checkpoint=lambda **kw:events.append('checkpoint'),clear_selection=lambda **kw:None,
            changed=SimpleNamespace(emit=lambda:events.append('changed')),update=lambda:None,color_preview=None)
        Canvas.reset_current(state)
        assert events==['checkpoint','changed']
        assert state.image.pixelColor(1,1)==QColor('red')
        assert state.image.pixelColor(0,0)==QColor('blue' if regions else 'red')
        Canvas.reset_current(state)
        assert events==['checkpoint','changed']


if __name__ == '__main__':
    for path in (ROOT / 'packstudio').glob('*.py'):
        ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    for check in (verify_adjustment_dispatch, verify_gradient_drag, verify_gradients, verify_batch_events, verify_batch_scopes, verify_scoped_candidates, verify_brush_rgba, verify_transitions, verify_resource_thumbnail_cache, verify_single_canvas_routing, verify_material_reset):
        check()
        print('PASS', check.__name__)
