"""Windows Alt-wheel X-axis regression and cursor-anchored view-only zoom."""
import os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QImage,QColor,QWheelEvent,QRegion
from PySide6.QtWidgets import QApplication,QScrollArea
from packstudio.studio import StudioWindow
app=QApplication([]);none=Qt.KeyboardModifier.NoModifier;alt=Qt.KeyboardModifier.AltModifier
def wheel(widget,point,angle,pixels=QPoint(),keys=alt):
    event=QWheelEvent(point,widget.mapToGlobal(point),pixels,angle,Qt.MouseButton.NoButton,keys,Qt.ScrollPhase.NoScrollPhase,False)
    QApplication.sendEvent(widget,event);return event
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='pointer-zoom-') as tmp:
    os.environ['PACKSTUDIO_SETTINGS_FILE']=tmp+'/settings.ini';os.environ['PACKSTUDIO_NAMING_FILE']=tmp+'/names.json'
    w=StudioWindow(Path(tmp)/'library',drafts=False);w.show();app.processEvents()
    try:
        c=w.canvas;im=QImage(128,128,QImage.Format.Format_ARGB32)
        for y in range(128):
            for x in range(128):im.setPixelColor(x,y,QColor(x*2,y*2,100,128 if x%2 else 255))
        c.set_image(im);c.selection_region=QRegion(10,10,30,20);c.sync_selection();selection=QRegion(c.selection_region)
        signals=[];c.changed.connect(lambda:signals.append(True));w.set_tool('mouse');w.search.setFocus()
        preview_zoom=w.preview.zoom
        with patch('packstudio.pointer_input.QGuiApplication.queryKeyboardModifiers',return_value=none):
            for axis in ('windows-alt-x','vertical-y','pixel-only'):
                c.zoom=2.;c.offset=QPointF(31.25,25.5)
                point=c.offset+QPointF(33.25,41.75)*c.zoom
                anchor=(point-c.offset)/c.zoom;before_offset=QPointF(c.offset)
                angle=QPoint(120,0) if axis=='windows-alt-x' else QPoint(0,120) if axis=='vertical-y' else QPoint()
                pixels=QPoint(0,40) if axis=='pixel-only' else QPoint()
                scrolls=w.docks['editor'].findChildren(QScrollArea)
                positions=[(s.horizontalScrollBar().value(),s.verticalScrollBar().value()) for s in scrolls]
                event=wheel(c,point,angle,pixels)
                assert event.isAccepted() and c.zoom==2.5,(axis,c.zoom)
                assert ((point-c.offset)/c.zoom-anchor).manhattanLength()<1e-10
                assert w.canvas_zoom_label.text()=='250.0%'
                assert positions==[(s.horizontalScrollBar().value(),s.verticalScrollBar().value()) for s in scrolls]
                wheel(c,point,-angle,-pixels)
                assert c.zoom==2 and (c.offset-before_offset).manhattanLength()<1e-10
                assert c.image==im and c.selection_region==selection and not c.history and not signals
            point=QPointF(90,100)
            # Windows Alt-wheel must not disappear merely because angleDelta.y()==0.
            wheel(c,point,QPoint(120,0));assert c.zoom==2.5
            wheel(c,point,QPoint(-120,0));assert c.zoom==2
            # Fine wheel increments and two-axis reports must not zoom twice.
            wheel(c,point,QPoint(60,0));wheel(c,point,QPoint(60,0));assert abs(c.zoom-2.5)<1e-10
            c.zoom=2;wheel(c,point,QPoint(120,120));assert c.zoom==2.5
            for tool in ('pencil','select','wand','eraser','bucket','picker'):
                w.set_tool(tool);old=c.zoom;wheel(c,point,QPoint(120,0));assert c.zoom==old
            w.set_tool('mouse');old=c.zoom;wheel(c,point,QPoint(120,0),keys=none);assert c.zoom==old
            wheel(c,point,QPoint());assert c.zoom==old
            c.zoom=80;assert wheel(c,point,QPoint(120,0)).isAccepted() and c.zoom==80
            c.zoom=.1;assert wheel(c,point,QPoint(-120,0)).isAccepted() and c.zoom==.1
            assert w.preview.zoom==preview_zoom
            wheel(w.preview,QPointF(40,40),QPoint(120,0));assert w.preview.zoom>preview_zoom and c.zoom==.1
            # The source atlas and selection stay intact when zooming a component view.
            c.set_atlas(im,[(16,16,32,32)],'zoom-atlas');c.zoom=3;c.offset=QPointF(20,20)
            point=QPointF(35,35);anchor=(point-c.offset)/c.zoom;wheel(c,point,QPoint(120,0))
            assert c.image==im and c.regions==[(16,16,32,32)] and ((point-c.offset)/c.zoom-anchor).manhattanLength()<1e-10
        print('PASS Windows Alt X / vertical Y / pixel-only wheel, pointer-only gate, anchored zoom, direction, limits, unfocused canvas, parent scroll, zoom readout and unchanged pixels/selection/history')
    finally:w.dirty=False;w.close();app.processEvents()
