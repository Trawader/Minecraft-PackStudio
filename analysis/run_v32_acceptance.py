"""Two serial regression rounds with durable logs (no release rebuild)."""
import json, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis' / 'v32-acceptance-20261118'
OUT.mkdir(exist_ok=True)
TESTS = ['v32_interaction','v32_modifiers','selection_history','pointer_zoom',
         'palette_fill','color_dialog','editor_layout','frontend_flow',
         'feature_contracts','pixel_tasks','task_progress','recolor',
         'batch_recolor','sky_editing','animation_editor','sounds',
         'detached_editor','studio','export_interactions','original_export',
         'export_priority','pack_conversion','added_versions']
results=[]
for round_no in (1,2):
    for name in TESTS:
        start=time.monotonic()
        log=OUT/f'round-{round_no}-{name}.log'
        with log.open('w',encoding='utf-8') as output:
            try:
                p=subprocess.run([sys.executable,str(ROOT/'analysis'/f'verify_{name}.py')],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,timeout=300)
                code=p.returncode
            except subprocess.TimeoutExpired:
                code='timeout'
        item=dict(round=round_no,test=name,exit_code=code,seconds=round(time.monotonic()-start,2),log=log.name)
        results.append(item)
        (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(item),flush=True)
print('COMPLETE',flush=True)
sys.exit(any(r['exit_code']!=0 for r in results))
