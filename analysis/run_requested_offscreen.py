"""Run the TXT workflow checks with isolated settings and retained logs."""
import json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis' / ('requested-offscreen-' + time.strftime('%Y%m%d-%H%M%S'))
OUT.mkdir()
env = dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONIOENCODING='utf-8',
           PACKSTUDIO_SETTINGS_FILE=str(OUT / 'settings.ini'),
           PACKSTUDIO_WORKFLOW_RESULTS=str(OUT))
tests = [
    'verify_v32_prerelease_core', 'verify_v32_session_state',
    'verify_project_exit_palette', 'verify_derivation_interaction',
    'verify_v32_tool_context', 'verify_v32_batch_lifecycle',
    'verify_v32_batch_frames', 'verify_v32_derivation_flow',
    'verify_v32_conversion_pairs', 'verify_v32_conversion_reports',
    'verify_v32_mixed_order', 'verify_v32_model_references',
    'verify_v3_algorithms', 'verify_v32_export_roundtrips',
    'verify_v32_real_workflows',
]
rows = []
print(OUT, flush=True)
for name in tests:
    start = time.monotonic()
    print('BEGIN', name, flush=True)
    with (OUT / (name + '.log')).open('w', encoding='utf-8') as log:
        try:
            result = subprocess.run([sys.executable, str(ROOT / 'analysis' / (name + '.py'))],
                                    cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600)
            status = 'passed' if result.returncode == 0 else 'failed'
            code = result.returncode
        except subprocess.TimeoutExpired:
            status, code = 'timeout', None
    rows.append(dict(test=name, status=status, returncode=code, seconds=round(time.monotonic()-start, 2)))
    (OUT / 'results.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    print(rows[-1], flush=True)
print('DONE', flush=True)
