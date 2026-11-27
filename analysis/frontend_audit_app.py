import os,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
folder=ROOT/'.tmp'/('frontend-audit-'+uuid.uuid4().hex);folder.mkdir()
os.environ['PACKSTUDIO_SETTINGS_FILE']=str(folder/'settings.ini')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from packstudio.studio import StudioWindow
app=QApplication(sys.argv);app.setWindowIcon(QIcon(str(ROOT/'packstudio/assets/mcps.ico')))
w=StudioWindow(folder/'library',drafts=False);w.resize(1280,800);w.setWindowTitle('MCPS 前端审查（独立测试资料）');w.show()
sys.exit(app.exec())
