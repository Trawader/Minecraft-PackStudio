"""Check that window docking uses the exact V1 native Qt interaction path."""
import ast,os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QMainWindow,QStyleOptionDockWidget,QStyle
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from packstudio.studio import StudioWindow

def methods(path):
 text=path.read_text('utf8').replace('影子','副本').replace('project shadows','project copies')
 tree=ast.parse(text)
 cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='StudioWindow')
 return {n.name:ast.dump(n,include_attributes=False) for n in cls.body if isinstance(n,ast.FunctionDef)}
current=methods(ROOT/'packstudio/studio.py')
reference=methods(ROOT/'output/PackEditorV1/source/packstudio/studio.py')
for name in ('setup_docks','make_dock'):assert current[name]==reference[name],name
for name in ('dragEnterEvent','dragMoveEvent','dragLeaveEvent','dropEvent'):assert name not in current
app=QApplication([])
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='native-dock-') as tmp:
 os.environ['PACKSTUDIO_SETTINGS_FILE']=str(Path(tmp)/'settings.ini')
 w=StudioWindow(Path(tmp)/'library',drafts=False);w.resize(1280,900);w.show();app.processEvents()
 assert w.isAnimated() and w.isDockNestingEnabled()
 assert w.dockOptions() & QMainWindow.DockOption.AllowTabbedDocks
 assert not w.dockOptions() & QMainWindow.DockOption.ForceTabbedDocks
 for dock in w.docks.values():
  assert dock.titleBarWidget() is None
  assert dock.cursor().shape()==Qt.CursorShape.ArrowCursor
 source=w.docks['render'];target=w.docks['library']
 option=QStyleOptionDockWidget();source.initStyleOption(option)
 title=source.style().subElementRect(QStyle.SubElement.SE_DockWidgetTitleBarText,option,source)
 QTest.mouseDClick(source,Qt.MouseButton.LeftButton,pos=title.center());app.processEvents()
 assert source.isFloating()
 source.setFloating(False);app.processEvents()
 w.splitDockWidget(target,source,Qt.Orientation.Horizontal);app.processEvents()
 assert source.geometry().left()>=target.geometry().right()
 w.splitDockWidget(target,source,Qt.Orientation.Vertical);app.processEvents()
 assert source.geometry().top()>=target.geometry().bottom()
 w.tabifyDockWidget(target,source);app.processEvents()
 assert source in w.tabifiedDockWidgets(target)
 w.dirty=False;w.close()
print('PASS V1 docking code parity, native title handling, arrow cursor, animated nested docks, horizontal/vertical/tab layouts')
