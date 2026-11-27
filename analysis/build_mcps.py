"""Build the current application package without personal data."""
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,default=ROOT/'output/McPackStudio')
output=parser.parse_args().output.resolve()
if output.exists():
    raise FileExistsError(output)
staging=ROOT/'.tmp/mcps-build'
staging.mkdir(parents=True,exist_ok=True)
command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed','--name','MCPS','--icon',str(ROOT/'packstudio/assets/mcps.ico'),'--contents-directory','_internal','--distpath',str(staging/'dist'),'--workpath',str(staging/'work'),'--specpath',str(staging)]
for source,target in [('packstudio/data','packstudio/data'),('packstudio/assets','packstudio/assets'),('docs/resource-identities.tsv','docs')]:
    command+=['--add-data',str(ROOT/source)+';'+target]
command.append(str(ROOT/'main.py'))
environment=os.environ.copy()
windows=Path(os.environ.get('SystemRoot','C:/Windows'))
environment['PATH']=os.pathsep.join(map(str,[Path(sys.executable).parent,Path(sys.base_prefix),Path(sys.base_prefix)/'DLLs',ROOT/'.venv/Lib/site-packages/PySide6',windows/'System32',windows]))
subprocess.run(command,cwd=ROOT,env=environment,check=True)
shutil.copytree(staging/'dist/MCPS',output)
shutil.copy2(ROOT/'README.md',output/'README.md')
manifest={p.relative_to(output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob('*') if p.is_file()}
(ROOT/'output/McPackStudio-artifacts.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
print(f'Built {output}: {len(manifest)} files',flush=True)
