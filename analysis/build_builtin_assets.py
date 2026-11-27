"""Build the supported-version offline resource store; identical bytes stored once."""
import sys,json,hashlib,zipfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from packstudio.versions import VERSIONS
from version_sources import source_directory
source=ROOT/'reference/各版本assets';target=ROOT/'packstudio/data/vanilla-assets.zip'
temporary=target.with_suffix('.building');manifest={'schema':1,'versions':{}};seen=set();total=0;unique=0
with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
 for version in VERSIONS:
  directory=source_directory(version)
  if not directory.is_dir():raise ValueError('Missing version: '+version)
  entries={}
  for path in sorted(directory.rglob('*')):
   if not path.is_file():continue
   raw=path.read_bytes();key=hashlib.sha256(raw).hexdigest();total+=len(raw)
   entries['assets/'+path.relative_to(directory).as_posix()]=key
   if key not in seen:
    archive.writestr('objects/'+key,raw);seen.add(key);unique+=len(raw)
  manifest['versions'][version]=entries;print(version,len(entries),flush=True)
 manifest['statistics']={'references':sum(map(len,manifest['versions'].values())),'unique_objects':len(seen),'original_bytes':total,'unique_bytes':unique}
 archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,separators=(',',':')))
temporary.replace(target)
# Bundle the existing preview geometry too; reference directories are build inputs.
import shutil
models=ROOT/'packstudio/data/models';models.mkdir(exist_ok=True)
for path in (ROOT/'reference/皮肤制作器中文版/Models').rglob('*.xml'):shutil.copy2(path,models/path.name)
(ROOT/'packstudio/data/vanilla-assets-summary.json').write_text(json.dumps({'versions':list(VERSIONS),**manifest['statistics'],'archive_bytes':target.stat().st_size},indent=2),'utf8')
print(manifest['statistics'],target.stat().st_size,flush=True)
