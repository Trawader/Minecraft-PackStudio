"""Real V3.2 input packs: two isolated import/edit/reopen/export workflows."""
import os, sys, json, hashlib, struct, time, traceback, zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtGui import QImage,QRegion
from packstudio.studio import StudioWindow
from packstudio.core import decode,import_pack,write_zip
from packstudio.export_dialog import defaults,prepare_files
from packstudio.batch_recolor import plan,preview_files,apply_batch,undo_batch
from packstudio.recolor import Settings
app=QApplication([])
OUT=Path(os.environ.get('PACKSTUDIO_WORKFLOW_RESULTS',str(ROOT/'analysis'/'v32-acceptance-20261118')));OUT.mkdir(exist_ok=True)
run=Path(os.environ['V32_RESUME']) if os.environ.get('V32_RESUME') else ROOT/'.tmp'/('v32-real-'+str(time.time_ns()));run.mkdir(exist_ok=True)
packs=sorted((ROOT/'reference'/'V3.2').glob('*.zip'))
assert len(packs)==7
hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in packs}
results=[];qt_errors=[]
if os.environ.get('V32_RESUME'):
    previous=json.loads((OUT/'real-workflows.json').read_text(encoding='utf-8'))
    results=[r for r in previous['results'] if r.get('step')=='import-edit-batch']
sys.excepthook=lambda k,e,t:(qt_errors.append(str(e)),traceback.print_exception(k,e,t))
def record(row):
    results.append(row)
    (OUT/'real-workflows.json').write_text(json.dumps({'workspace':str(run),'results':results,'qt_errors':qt_errors},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(row,ensure_ascii=False),flush=True)
for round_no in (1,2):
    folder=run/f'round-{round_no}';folder.mkdir(exist_ok=True)
    os.environ['PACKSTUDIO_SETTINGS_FILE']=str(folder/'settings.ini')
    w=StudioWindow(folder/'library',drafts=False);w.show();app.processEvents()
    cached=folder/'workflow.packstudio'
    if cached.exists():w.read_project(cached)
    for pack in ([] if cached.exists() else packs if round_no==1 else list(reversed(packs))):
        print(f'BEGIN round {round_no}: {pack.name}',flush=True)
        start=time.monotonic();w.add_pack(pack);source=w.sources[-1]
        w.add_to_composition({'origin':source.uid,'path':'','kind':'root','name':source.name})
        layer=w.layers[0];origin='stage:'+layer.uid;original=dict(layer.files)
        def desc(path):return {'origin':origin,'kind':'png','path':path,'name':Path(path).name}
        pngs=[p for p,b in layer.files.items() if p.lower().endswith('.png') and b.startswith(b'\x89PNG\r\n\x1a\n')]
        def pixels(path):
            a,b=struct.unpack('>II',layer.files[path][16:24]);return a*b
        ordinary=sorted([p for p in pngs if not p.endswith('pack.png') and p+'.mcmeta' not in layer.files],key=pixels)
        edited=[]
        candidates=ordinary[:1]
        skies=[p for p in pngs if '/sky/' in p.lower() and pixels(p)<=16*1024*1024]
        if skies:candidates.append(min(skies,key=pixels))
        for path in dict.fromkeys(candidates):
            print(f'  Edit {path} ({pixels(path)} pixels)',flush=True)
            with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):w.edit_descriptor(desc(path))
            before=QImage(w.canvas.image);assert not before.isNull() and not w.canvas.read_only
            panel=w.recolor_panel;panel.mode.setCurrentIndex(panel.mode.findData('adjust'))
            panel.controls['brightness'][1].setValue(13 if round_no==1 else -17)
            panel.preview();assert layer.files[path]==original[path]
            panel.invalidate();assert layer.files[path]==original[path]
            panel.preview();expected=QImage(panel.output);panel.apply()
            assert decode(layer.files[path])==expected
            if expected!=before:
                if before.width()*before.height()>4*1024*1024:
                    w.canvas.undo();assert decode(layer.files[path])==expected
                    assert w.operation_history.step(barriers=True)
                    assert decode(layer.files[path])==before
                    assert w.operation_history.step(redo=True,barriers=True)
                    assert decode(layer.files[path])==expected
                else:
                    w.canvas.undo();assert decode(layer.files[path])==before
                    w.canvas.redo();assert decode(layer.files[path])==expected
            assert expected.size()==before.size()
            assert expected.convertToFormat(QImage.Format.Format_RGBA8888).size()==before.size()
            edited.append(path)
        w.clear_editor()
        batchpaths=ordinary[:3]
        if batchpaths:
            units,baseline,metadata,errors=plan(layer,{'kind':'resource_group','origin':origin,'resource_paths':batchpaths})
            assert not errors and units
            output=preview_files(units,baseline,Settings(mode='adjust',saturation=-40,brightness=5))
            if output:
                apply_batch(w,origin,layer,baseline,metadata,output)
                assert all(layer.files[p]==raw for p,raw in output.items())
                undo_batch(w);assert all(layer.files[p]==raw for p,raw in baseline.items())
                apply_batch(w,origin,layer,baseline,metadata,output)
            edited+=list(output)
        assert source.files==original,'Project changes leaked into library'
        for p,raw in original.items():
            if not p.lower().endswith('.png'):assert layer.files[p]==raw,p
        record(dict(round=round_no,pack=pack.name,step='import-edit-batch',files=len(original),pngs=len(pngs),ogg=sum(p.endswith('.ogg') for p in original),edited=sorted(set(edited)),seconds=round(time.monotonic()-start,2)))
    project=folder/'workflow.packstudio';expected={l.uid:dict(l.files) for l in w.layers}
    w.write_project(project);w.dirty=False;w.close();app.processEvents()
    w=StudioWindow(folder/'library',drafts=False);w.read_project(project)
    assert len(w.layers)==7 and len(w.sources)==7
    for layer in w.layers:
        assert layer.files==expected[layer.uid]
        base=defaults([layer]);report=[]
        files=prepare_files([layer],w.vanilla,w.working_version,base,'unchanged',base['title'],base['body'],base['cover'],'keep',report)
        assert 'packstudio-conversion-report.json' not in files or 'packstudio-conversion-report.json' in layer.files
        assert not any(p.startswith(('.tmp/','analysis/')) or p.endswith(('.packstudio','.ini')) for p in files if p not in layer.files)
        reported={r['path'] for r in report if r.get('action')=='omitted'}
        omissions=[]
        for p,raw in layer.files.items():
            if p.endswith(('.ogg','.properties','.png.mcmeta')) and files.get(p)!=raw:
                assert p in reported,('UNREPORTED lost configuration/audio',p)
                omissions.append(p)
        export=folder/(layer.uid+'.zip');write_zip(export,files)
        with zipfile.ZipFile(export) as z:
            assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
            assert all(not n.startswith('/') and '..' not in Path(n).parts for n in z.namelist())
        imported=import_pack(export);assert imported.files==files
        (folder/(layer.uid+'-report.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        record(dict(round=round_no,pack=layer.name,step='reopen-export-reimport',files=len(files),zip=str(export),report_entries=len(report),configuration_omissions=omissions))
    assert not qt_errors,qt_errors
    w.dirty=False;w.close();app.processEvents()
assert all(hashlib.sha256(p.read_bytes()).hexdigest()==hashes[p.name] for p in packs)
record({'step':'complete','rounds':2,'source_zip_hashes_unchanged':True})
