"""Full real-pack export round trips, no QApplication and no source writes."""
import sys,json,hashlib,zipfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from packstudio.core import import_pack,Vanilla,write_zip
from packstudio.export_dialog import defaults,prepare_files
from packstudio.export_integrity import protected_paths,reference_issues
from packstudio.layouts import LayoutReviewRequired,tag_import
v=Vanilla();outdir=ROOT/'.tmp'/'v32-export-audit';outdir.mkdir(exist_ok=True);rows=[]
def save():
    (ROOT/'analysis'/'v32-export-roundtrips.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
packs=sorted((ROOT/'reference'/'V3.2').glob('*.zip'))
for i,path in enumerate(packs):
    digest=hashlib.sha256(path.read_bytes()).hexdigest();layer=import_pack(path);tag_import(layer);original=dict(layer.files)
    base=defaults([layer]);targets=['unchanged']
    if i in (0,1):targets.append('1.20.6' if layer.source_version!='1.20.6' else '1.12.2')
    for target in targets:
        print('BEGIN',i,target,flush=True);report=[];start=time.monotonic()
        try:
            files=prepare_files([layer],v,'1.8.9',base,target,base['title'],base['body'],base['cover'],fill_policy='keep',report_out=report)
            protected=protected_paths([layer]);assert all(files.get(p)==original[p] for p in protected if p in original)
            if 'packstudio-conversion-report.json' not in original:assert 'packstudio-conversion-report.json' not in files
            dest=outdir/(str(i)+'-'+target+'.zip');write_zip(dest,files)
            with zipfile.ZipFile(dest) as z:assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
            reopened=import_pack(dest);assert reopened.files==files
            issues=reference_issues(files,target if target!='unchanged' else layer.source_version)
            row=dict(pack=path.name,target=target,result='passed',files=len(files),omitted=sum(r['action']=='omitted' for r in report),reference_issues=len(issues),seconds=round(time.monotonic()-start,2))
        except LayoutReviewRequired as e:row=dict(pack=path.name,target=target,result='explicit_layout_review_required',detail=str(e))
        assert layer.files==original and hashlib.sha256(path.read_bytes()).hexdigest()==digest
        rows.append(row);save();print(json.dumps(row,ensure_ascii=False),flush=True)
print('DONE',len(rows),flush=True)
