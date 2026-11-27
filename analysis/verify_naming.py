import os,sys,tempfile,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QMessageBox
from unittest.mock import patch
from packstudio import naming
from packstudio.semantics import describe,hidden_terms,parts,variant_id
app=QApplication([])
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='naming-check-') as directory:
 os.environ['PACKSTUDIO_NAMING_FILE']=str(Path(directory)/'names.json')
 os.environ['PACKSTUDIO_SETTINGS_FILE']=str(Path(directory)/'settings.ini')
 naming.reset_copy();path=naming.config_path();data=json.loads(path.read_text('utf8'))
 glint='assets/minecraft/textures/particle/glint.png';glow=glint.replace('glint','glow');stone='assets/minecraft/textures/block/stone.png'
 assert describe(glint)['name']=='闪光 / Glint' and '流星' in describe(glint)['search']
 assert describe(glow)['name']=='火花 / Glow' and '点' in describe(glow)['search']
 code=describe(stone)['code'];original=describe(stone)['name'];identity=variant_id(stone,'1.21.11')
 row=data['entries'][code];row['name']='我的石块';row['tags']=['建筑底座'];row['include_default_search']=False
 path.write_text(json.dumps(data,ensure_ascii=False),'utf8');assert naming.reload_copy()==0
 assert describe(stone)['name']=='我的石块' and '建筑底座' in describe(stone)['search'];assert variant_id(stone,'1.21.11')==identity
 data['entries']['particle/glint']['name']='流星火';data['entries']['particle/glint']['tags']=['天外来客']
 path.write_text(json.dumps(data,ensure_ascii=False),'utf8');naming.reload_copy()
 assert '天外来客' in hidden_terms('particle/glint')
 assert any(p['name']=='流星火' for p in parts('assets/minecraft/textures/particle/particles.png','1.8.9') if p['code']=='particle/glint')
 row['number']=data['entries']['particle/glow']['number'];path.write_text(json.dumps(data,ensure_ascii=False),'utf8');assert naming.reload_copy()==1
 assert describe(stone)['name']==original and variant_id(stone,'1.21.11')==identity
 path.write_text('{broken','utf8');assert naming.reload_copy()==1;assert describe(stone)['name']==original
 from packstudio.studio import StudioWindow
 w=StudioWindow(Path(directory)/'library',drafts=False)
 with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Cancel):w.reset_names_button.click();assert path.read_text('utf8')=='{broken'
 with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):w.reset_names_button.click()
 assert naming.reload_copy()==0 and describe(glint)['name']=='闪光 / Glint'
 w.dirty=False;w.close()
 del os.environ['PACKSTUDIO_NAMING_FILE'];naming.reload_copy()
print('PASS editable names/tags, legacy components, immutable IDs, tamper/malformed fallback, reset cancel/confirm')
