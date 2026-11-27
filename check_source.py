"""Check a source distribution without opening windows or writing user data."""
import argparse,hashlib,json,sys,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def check(files_only=False,strict=False):
 manifest=json.loads((ROOT/'source-manifest.json').read_text(encoding='utf-8'))
 errors=[];changed=[]
 for name,expected in manifest.items():
  path=ROOT/name
  if not path.is_file():errors.append('Missing: '+name)
  elif hashlib.sha256(path.read_bytes()).hexdigest()!=expected:changed.append('Changed: '+name)
 if strict:errors.extend(changed)
 if errors:raise RuntimeError('\n'.join(errors))
 if changed and not strict:print(f'NOTICE: {len(changed)} files changed since export; local edits allowed.')
 for path in (ROOT/'packstudio').glob('*.py'):compile(path.read_bytes(),str(path),'exec')
 with zipfile.ZipFile(ROOT/'packstudio/data/vanilla-assets.zip') as archive:
  versions=json.loads(archive.read('manifest.json'))['versions']
  keys={key for values in versions.values() for key in values.values()}
  for key in keys:
   assert hashlib.sha256(archive.read('objects/'+key)).hexdigest()==key,key
 for path in (ROOT/'packstudio/data').rglob('*.json'):json.loads(path.read_text(encoding='utf-8'))
 models=list((ROOT/'packstudio/data/models').glob('*.xml'))
 for path in models:ET.parse(path)
 if not files_only:
  sys.path.insert(0,str(ROOT))
  from PySide6.QtGui import QImageReader
  for path in (ROOT/'packstudio/assets').iterdir():
   if path.suffix.lower() in ('.png','.ico'):assert not QImageReader(str(path)).read().isNull(),str(path)
  import main
  from packstudio.core import Vanilla
  from packstudio.versions import VERSIONS
  from packstudio.models import ModelLibrary
  assert Path(main.__file__).resolve()==ROOT/'main.py'
  vanilla=Vanilla()
  for version in VERSIONS:assert vanilla.paths(version)==set(versions[version]),version
  assert len(ModelLibrary(vanilla).xml)>=48
 print(f'PASS: {len(manifest)} files; {len(versions)} vanilla versions; {len(keys)} resource objects; {len(models)} XML models; runtime imports={not files_only}')
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--files-only',action='store_true');parser.add_argument('--strict',action='store_true')
 args=parser.parse_args();check(args.files_only,args.strict)
