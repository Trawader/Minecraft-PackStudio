import os,sys,tempfile
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen';sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QColor
from packstudio.studio import StudioWindow
from packstudio.core import Layer,png,decode
app=QApplication([])
with tempfile.TemporaryDirectory() as t:
 os.environ['PACKSTUDIO_SETTINGS_FILE']=str(Path(t)/'s.ini');w=StudioWindow(Path(t)/'lib',drafts=False)
 im=QImage(16,16,QImage.Format.Format_ARGB32);im.fill(QColor('cyan'));path='assets/minecraft/textures/items/demo.png';owner=Layer('fixture',{path:png(im)});w.sources=[owner];w.refresh();d={'origin':owner.uid,'kind':'png','path':path,'name':'demo'}
 w.resource_editors.open_editor(d);dock,e=w.resource_editors.editors[(owner.uid,path)]
 print('TOOLS',sorted(e.tool_buttons))
 e.recolor_panel.mode.setCurrentIndex(e.recolor_panel.mode.findData('adjust'));e.recolor_panel.controls['brightness'][1].setValue(-30)
 e.recolor_panel.preview();e.recolor_panel.apply();assert decode(owner.files[path])!=im
 e.canvas.undo();assert decode(owner.files[path])==im
 print('PASS standalone recolor undo');dock.close();w.dirty=False;w.close()
