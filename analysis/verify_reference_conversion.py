"""Read-only conversion smoke check against the supplied Tsuki/Pink samples."""
import os,sys,hashlib,json,collections
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from packstudio.core import ROOT,Vanilla,import_pack
from packstudio.export_dialog import defaults,prepare_files
from packstudio.layouts import inspect_atlases,LayoutReviewRequired
app=QApplication([]);vanilla=Vanilla()
for index,path in enumerate(sorted((ROOT/'reference').glob('*.zip'))):
    digest=hashlib.sha256(path.read_bytes()).digest();layer=import_pack(path);original=dict(layer.files);base=defaults([layer])
    pending=[row for row in inspect_atlases(layer) if not row['chosen']]
    for target in ('1.7.10','1.20.6','26.2'):
        try:result=prepare_files([layer],vanilla,'1.8.9',base,target,base['title'],base['body'],base['cover'])
        except LayoutReviewRequired:
            assert pending and layer.files==original
            print(index,target,'REVIEW REQUIRED:',len(pending),'ambiguous atlases (no mutation)',flush=True)
            continue
        assert not pending
        report=json.loads(result.get('packstudio-conversion-report.json',b'[]'))
        assert 'pack.mcmeta' in result and original==layer.files
        print(index,target,len(result),'files',dict(collections.Counter(x['action'] for x in report)),flush=True)
    assert hashlib.sha256(path.read_bytes()).digest()==digest
print('PASS: supplied ZIPs convert or require layout review without changing source bytes')
