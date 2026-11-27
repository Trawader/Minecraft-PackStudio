"""Native visual checks on an isolated copy of a real V3.2 pack."""
import os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
folder=ROOT/'.tmp'/('v32-native-'+str(time.time_ns()));folder.mkdir()
os.environ['PACKSTUDIO_SETTINGS_FILE']=str(folder/'settings.ini')
from PySide6.QtWidgets import QApplication
from packstudio.studio import StudioWindow
app=QApplication([])
w=StudioWindow(folder/'library',drafts=False);w.resize(1280,800);w.show()
w.add_pack(next((ROOT/'reference'/'V3.2').glob('*Blue*.zip')))
s=w.sources[0];p=next(p for p in s.files if p.endswith('/diamond_helmet.png'))
w.edit_descriptor({'origin':s.uid,'path':p,'kind':'png','name':'diamond_helmet.png'})
w.setWindowTitle('MCPS V3.2 验收测试（独立副本）')
sys.exit(app.exec())
