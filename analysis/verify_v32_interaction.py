"""V3.2 A: input coordinates, color synchronization, selection and source integrity."""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QImage,QColor,QWheelEvent,QRegion,QFontDatabase,QFont
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from packstudio.canvas import Canvas
from packstudio.preview import Preview
from packstudio.color_editor import ColorEditor
from packstudio.wand import select

app=QApplication([])
for font in ('segoeui.ttf','msyh.ttc'):
    path=Path('C:/Windows/Fonts')/font
    if path.exists():QFontDatabase.addApplicationFont(str(path))
app.setFont(QFont('Microsoft YaHei',9))
alt=Qt.KeyboardModifier.AltModifier;shift=Qt.KeyboardModifier.ShiftModifier
def wheel(widget,delta,mod=alt):
    event=QWheelEvent(QPointF(80,90),QPointF(80,90),QPoint(),QPoint(0,delta),Qt.MouseButton.NoButton,mod,Qt.ScrollPhase.NoScrollPhase,False)
    QApplication.sendEvent(widget,event)
def click(canvas,x,y,mod=Qt.KeyboardModifier.NoModifier):
    QTest.mouseClick(canvas,Qt.MouseButton.LeftButton,mod,QPoint(x,y))

c=Canvas();im=QImage(128,128,QImage.Format.Format_ARGB32);im.fill(QColor('red'));c.set_image(im)
original=QImage(c.image);p=QPointF(80,90);anchor=(p-c.offset)/c.zoom;zoom=c.zoom
wheel(c,120);assert (anchor-(p-c.offset)/c.zoom).manhattanLength()<1e-9
wheel(c,-120);assert abs(c.zoom-zoom)<1e-9
wheel(c,0);assert abs(c.zoom-zoom)<1e-9
wheel(c,120,Qt.KeyboardModifier.NoModifier);assert abs(c.zoom-zoom)<1e-9
preview=Preview();wheel(preview,120);assert preview.zoom>1 and c.zoom==zoom
for _ in range(80):wheel(preview,120);wheel(c,120)
assert preview.zoom==8 and c.zoom==80
for _ in range(160):wheel(preview,-120);wheel(c,-120)
assert preview.zoom==.2 and c.zoom==.1 and c.image==original
print('PASS anchored Alt zoom, bounds, independent views, unchanged image')

d=ColorEditor(QColor(88,224,207,123));d.show();app.processEvents()
from packstudio.appearance import STYLE
d.setStyleSheet(STYLE)
d.hex.selectAll();QTest.keyClicks(d.hex,'#AA96F8');assert d.color.name()=='#aa96f8' and d.color.alpha()==123
QTest.mouseClick(d.plane,Qt.MouseButton.LeftButton,pos=QPoint(d.plane.width()-1,d.plane.height()-1));assert d.color.value()==0 and d.color.alpha()==123
d.choose_hue(.5,0);d.choose_sv(1,1);assert d.color.green()>250 and d.color.blue()>250 and d.color.alpha()==123
d.fields['RGBA'][3].setValue(77);d.choose_swatch(QColor('red'));assert d.color.alpha()==77 and d.hex.text()=='#FF0000'
assert d.comparison.original==QColor(88,224,207,123)
ROOT.joinpath('.tmp').mkdir(exist_ok=True);d.grab().save(str(ROOT/'.tmp/v32-color-editor.png'));d.reject()
print('PASS HEX, mouse plane, hue, RGBA/HSVA, alpha, original comparison')

im=QImage(6,4,QImage.Format.Format_ARGB32);im.fill(QColor('blue'))
for x,y in [(0,0),(1,0),(0,1),(4,0)]:im.setPixelColor(x,y,QColor('red'))
c.set_image(im);c.zoom=10;c.offset=QPointF();c.set_tool('wand');c.wand_tolerance=0
click(c,5,5);assert c.selection_region.contains(QPoint(1,0)) and not c.selection_region.contains(QPoint(4,0))
click(c,45,5,shift);assert c.selection_region.contains(QPoint(4,0))
c.set_tool('select');click(c,5,5,alt);assert not c.selection_region.contains(QPoint(0,0)) and c.selection_region.contains(QPoint(1,0))
click(c,45,5);assert c.selection==(4,0,1,1)
click(c,45,5);assert c.selection==(4,0,1,1) # repeated selection never toggles off
c.set_tool('wand');c.wand_contiguous=False;click(c,5,5);assert c.selection_region.contains(QPoint(4,0))
c.wand_antialias=True;click(c,5,5);assert c.selection_weights and c.image==im
c.set_tool('pencil');c.color=QColor('green');click(c,15,5)
assert c.image.pixelColor(1,0)!=im.pixelColor(1,0) and c.image.pixelColor(1,0)!=QColor('green')
assert c.image.pixelColor(2,0)==im.pixelColor(2,0);c.undo();assert c.image==im
c.set_tool('bucket');click(c,5,5);assert c.image.pixelColor(2,0)==im.pixelColor(2,0);c.undo();assert c.image==im
# Weighted movement is a preview until Enter, and undo restores original pixels.
c.set_tool('mouse');QTest.mousePress(c,Qt.MouseButton.LeftButton,pos=QPoint(15,5))
assert c.moved_view()==im
QTest.mouseMove(c,QPoint(15,25));QTest.mouseRelease(c,Qt.MouseButton.LeftButton,pos=QPoint(15,25))
assert c.image==im and c.move_delta==QPoint(0,2)
QTest.keyClick(c,Qt.Key.Key_Return);assert c.image!=im and c.selection is None
c.undo();assert c.image==im
c.set_tool('wand');click(c,5,5)
QTest.keyClick(c,Qt.Key.Key_Escape);assert c.selection is None and not c.selection_weights
c.set_atlas(im,[(0,0,2,2),(4,0,1,1)],'fixture');c.zoom=10;c.offset=QPointF();c.set_tool('wand');c.wand_antialias=False;click(c,5,5)
assert c.selection_region.contains(QPoint(0,2)) and not c.selection_region.contains(QPoint(1,2))
c.set_tool('pencil');c.color=QColor('yellow');click(c,5,25)
assert c.image.pixelColor(4,0)==QColor('yellow') and c.image.pixelColor(3,0)==im.pixelColor(3,0)
c.undo();assert c.image==im
# Invisible RGB should not fragment transparent areas; alpha separates opaque colors.
transparent=QImage(3,1,QImage.Format.Format_ARGB32);transparent.fill(QColor(255,0,0,0));transparent.setPixelColor(1,0,QColor(0,255,0,0));transparent.setPixelColor(2,0,QColor('red'))
region,_=select(transparent,(0,0),QRegion(0,0,3,1),0,True)
assert region.contains(QPoint(1,0)) and not region.contains(QPoint(2,0))
# Tolerance distinguishes similar shades without reaching an unrelated material.
shades=QImage(3,1,QImage.Format.Format_ARGB32)
for x,color in enumerate([QColor(100,80,70),QColor(110,85,75),QColor(200,80,70)]):shades.setPixelColor(x,0,color)
region,_=select(shades,(0,0),QRegion(0,0,3,1),12,True)
assert region.contains(QPoint(1,0)) and not region.contains(QPoint(2,0))
print('PASS wand contiguous/global/alpha, replace/add/subtract, AA clipped edits, undo and atlas writeback')
