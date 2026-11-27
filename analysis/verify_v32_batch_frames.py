"""Read-only real-pack frame checks; no QApplication or windows."""
import sys,json,zipfile,hashlib
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtGui import QRegion
from packstudio.core import decode
from packstudio.batch_recolor import plan,region_candidates,preview_files
from packstudio.recolor import Settings
rows=[]
for path in sorted((ROOT/'reference'/'V3.2').glob('*.zip')):
    before=hashlib.sha256(path.read_bytes()).hexdigest();checked=frames=candidates=0;skipped=[]
    with zipfile.ZipFile(path) as z:
        names=set(z.namelist())
        for meta in sorted(n for n in names if n.lower().endswith('.png.mcmeta')):
            pngpath=meta[:-7]
            if pngpath not in names:continue
            files={pngpath:z.read(pngpath),meta:z.read(meta)}
            units,baseline,metadata,errors=plan(SimpleNamespace(files=files,kind='pack'),{'kind':'png','path':pngpath})
            if errors:skipped.extend(errors);continue
            if not units or not units[0].animated:continue
            original=decode(baseline[pngpath])
            if original.width()*original.height()>1048576:continue
            for unit in units:
                frame=original.copy(*unit.rect)
                if frame.width()*frame.height()>512*512:continue
                choices=region_candidates(frame,unit.allowed)
                assert all(c.region.subtracted(unit.allowed).isEmpty() for c in choices)
                candidates+=len(choices);frames+=1
                unit.mask=QRegion(choices[0].region) if choices else QRegion()
                unit.reviewed=bool(choices);unit.included=bool(choices)
            if any(u.included and u.reviewed for u in units):
                # Exclude unreviewed large frames; no silent whole-frame fallback.
                for u in units:
                    if not u.reviewed:u.included=False
                output=preview_files(units,baseline,Settings(mode='adjust',saturation=-20))
                for key,raw in output.items():
                    result=decode(raw);mask=QRegion()
                    for u in units:
                        if u.included:mask=mask.united(u.mask.translated(u.rect[0],u.rect[1]))
                    for y in range(original.height()):
                        for x in range(original.width()):
                            a=original.pixelColor(x,y);b=result.pixelColor(x,y)
                            assert a.alpha()==b.alpha()
                            from PySide6.QtCore import QPoint
                            if not mask.contains(QPoint(x,y)):assert a==b
            checked+=1
            if checked>=3:break
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
    row=dict(pack=path.name,animations=checked,frames=frames,candidates=candidates,skipped=skipped,source_unchanged=True)
    rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
(ROOT/'analysis'/'v32-batch-frame-results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
