"""Equal palette slots and selection-bounded contiguous paint/erase."""
import os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QColor,QImage,QRegion
from PySide6.QtTest import QTest
from packstudio.canvas import Canvas
from packstudio.studio import StudioWindow
app=QApplication([])
image=QImage(9,6,QImage.Format.Format_ARGB32);image.fill(QColor('red'))
for y in range(6):image.setPixelColor(4,y,QColor('blue'))
def fixture(tool):
    c=Canvas();c.resize(300,200);c.set_image(image);c.offset=QPointF(20,20);c.zoom=10;c.set_tool(tool);return c
def click(c,x,y):QTest.mouseClick(c,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(25+x*10,25+y*10))
for tool in ('bucket','magic_eraser'):
    c=fixture(tool);c.color=QColor('green');click(c,1,1)
    expected=QColor('green') if tool=='bucket' else QColor(0,0,0,0)
    assert c.image.pixelColor(0,0)==expected and c.image.pixelColor(3,5)==expected
    assert c.image.pixelColor(4,0)==QColor('blue') and c.image.pixelColor(6,0)==QColor('red')
    assert len(c.history)==1;c.undo();assert c.image==image;c.redo();assert c.image.pixelColor(0,0)==expected
    c=fixture(tool);c.color=QColor('green');c.selection_region=QRegion(1,1,2,3);c.sync_selection();click(c,1,1)
    assert c.image.pixelColor(1,1)==expected and c.image.pixelColor(2,3)==expected
    assert c.image.pixelColor(0,1)==QColor('red') and c.image.pixelColor(3,2)==QColor('red')
    before=QImage(c.image);history=len(c.history);click(c,0,0);assert c.image==before and len(c.history)==history
c=fixture('magic_eraser');c.selection_region=QRegion(0,0,2,2);c.selection_weights={(0,0):128};c.sync_selection();click(c,0,0)
assert c.image.pixelColor(0,0).alpha()==127 and c.image.pixelColor(1,1).alpha()==0
c=fixture('bucket');c.color=QColor(0,255,0,0);click(c,1,1);assert c.image.pixelColor(1,1).alpha()==255
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='palette-') as tmp:
    os.environ['PACKSTUDIO_SETTINGS_FILE']=tmp+'/settings.ini';os.environ['PACKSTUDIO_NAMING_FILE']=tmp+'/names.json'
    w=StudioWindow(Path(tmp)/'library',drafts=False);w.show();app.processEvents()
    defaults=[b.color.name() for b in w.palette_buttons]
    assert defaults==['#ff5555','#ffaa00','#ffff55','#55cc55','#55dddd','#5555ff','#bb55ff','#ffffff']
    for i,b in enumerate(w.palette_buttons):
        b.click();assert w.canvas.color==b.color and w.active_palette_index==i
        assert [p.isChecked() for p in w.palette_buttons]==[j==i for j in range(8)]
        assert [p.color.name() for p in w.palette_buttons]==defaults
    w.palette_buttons[5].click();w.set_color(QColor('#123456'))
    assert w.palette_buttons[5].color.name()=='#123456' and w.palette_buttons[0].color.name()==defaults[0]
    w.set_tool('magic_eraser');assert w.tool_buttons['eraser'].active_mode=='magic_eraser' and w.tool_buttons['eraser'].menu_mark.isVisible()
    assert not w.color_button.isVisible()
    w.dirty=False;w.close();app.processEvents()
    again=StudioWindow(Path(tmp)/'library',drafts=False)
    assert again.active_palette_index==5 and again.canvas.color.name()=='#123456'
    again.dirty=False;again.close()
print('PASS independent 8-slot palette, active selection/persistence, contiguous bucket/magic erase, selection clipping, AA, undo/redo, opaque paint')
