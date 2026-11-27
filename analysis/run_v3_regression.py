"""Run compatible legacy and V3 checks in isolated processes, with bounded timeouts."""
import os,sys,json,subprocess,tempfile,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]
(ROOT/'.tmp').mkdir(exist_ok=True)
NAMES=['verify_v3_algorithms','verify_v3','verify_v21_performance','verify_editor','verify_workspace','verify_studio','verify_shadows',
       'verify_export_interactions','verify_export_priority','verify_original_export','verify_models','verify_lazy_components',
       'verify_source_filter','verify_naming','verify_versions','verify_pack_conversion','verify_builtin_assets']
def run(name):
    start=time.perf_counter()
    with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='v3-suite-') as tmp:
        env=os.environ.copy();env.update(QT_QPA_PLATFORM='offscreen',PACKSTUDIO_SETTINGS_FILE=str(Path(tmp)/'settings.ini'),PACKSTUDIO_NAMING_FILE=str(Path(tmp)/'names.json'),PYTHONIOENCODING='utf-8')
        try:
            p=subprocess.run([sys.executable,str(ROOT/'analysis'/f'{name}.py')],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
            row={'test':name,'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
        except subprocess.TimeoutExpired as e:row={'test':name,'exit_code':-1,'stdout':str(e.stdout),'stderr':'TIMEOUT (120 seconds)'}
    row['seconds']=round(time.perf_counter()-start,3);print(name+': '+str(row['exit_code']),flush=True);return row
with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(run,NAMES))
(ROOT/'analysis/v3-suite-results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),'utf8')
sys.exit(any(row['exit_code'] for row in rows))
