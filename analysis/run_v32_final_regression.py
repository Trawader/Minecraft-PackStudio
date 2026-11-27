"""Final regression runner; only explicitly reviewed non-GUI scripts."""
import ast,hashlib,json,subprocess,sys,time
from pathlib import Path
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis'/'final-regression-20261126';OUT.mkdir(exist_ok=True)
scripts=['verify_v3_algorithms.py','verify_v32_prerelease_core.py','verify_v32_session_state.py','verify_v32_batch_lifecycle.py','verify_v32_batch_frames.py','verify_v32_conversion_pairs.py','verify_v32_conversion_reports.py','verify_v32_model_references.py','verify_v32_mixed_order.py','verify_v32_derivation_flow.py','verify_v32_export_roundtrips.py']
for p in (ROOT/'packstudio').rglob('*.py'):ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p))
files=sorted((ROOT/'packstudio').rglob('*.py'))+[ROOT/'packstudio/data/ui_en.json']
fingerprint=hashlib.sha256(b''.join(str(p.relative_to(ROOT)).encode()+p.read_bytes() for p in files)).hexdigest()
report={'started':datetime.now().astimezone().isoformat(),'source_fingerprint':fingerprint,'gui_run':False,'syntax':'passed','results':[]}
for script in scripts:
    start=time.monotonic();print('RUN',script,flush=True)
    try:
        proc=subprocess.run([sys.executable,str(ROOT/'analysis'/script)],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
        output=proc.stdout;code=proc.returncode
    except subprocess.TimeoutExpired as error:output=(error.stdout or b'')+b'\nTIMEOUT';code=-1
    (OUT/(script+'.log')).write_bytes(output)
    row={'script':script,'exit_code':code,'status':'passed' if code==0 else 'failed','seconds':round(time.monotonic()-start,2)}
    report['results'].append(row);print(row,flush=True)
    (OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
report['finished']=datetime.now().astimezone().isoformat();report['passed']=sum(r['status']=='passed' for r in report['results']);report['failed']=len(scripts)-report['passed']
(OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('FINAL',report['passed'],'passed',report['failed'],'failed',flush=True)
sys.exit(bool(report['failed']))
