"""Precompute local IDs and exact-version availability from the installed references."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from packstudio.semantics import build_identities,DATA
paths,versions=build_identities()
data={'schema':1,'paths':paths,'versions':{k:sorted(v) for k,v in versions.items()}}
(DATA/'semantic_index.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),'utf-8')
print(len(paths),'version paths;',len(versions),'local IDs')
