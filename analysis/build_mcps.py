"""Build the current application package without personal data."""
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from check_distribution import check
if not check(ROOT):
    raise SystemExit('Complete the local runtime resources before building.')
output=ROOT/'output/McPackStudio'
if output.exists():
    raise FileExistsError(output)
staging=ROOT/'.tmp/mcps-build'
staging.mkdir(parents=True,exist_ok=True)
version=staging/'version.txt'
version.write_text("""VSVersionInfo(ffi=FixedFileInfo(filevers=(3,6,0,0),prodvers=(3,6,0,0),mask=0x3f,flags=0,OS=0x40004,fileType=0x1,subtype=0,date=(0,0)),kids=[StringFileInfo([StringTable('040904B0',[StringStruct('FileDescription','Minecraft PackStudio'),StringStruct('ProductName','Minecraft PackStudio'),StringStruct('FileVersion','3.6.0'),StringStruct('ProductVersion','3.6.0'),StringStruct('InternalName','MCPS'),StringStruct('OriginalFilename','MCPS.exe')])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])""",encoding='utf8')
command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed','--name','MCPS','--icon',str(ROOT/'packstudio/assets/mcps.ico'),'--version-file',str(version),'--contents-directory','_internal','--distpath',str(staging/'dist'),'--workpath',str(staging/'work'),'--specpath',str(staging)]
for source,target in [('packstudio/data','packstudio/data'),('packstudio/assets','packstudio/assets'),('docs/resource-identities.tsv','docs')]:
    command+=['--add-data',str(ROOT/source)+';'+target]
command.append(str(ROOT/'main.py'))
environment=os.environ.copy()
windows=Path(os.environ.get('SystemRoot','C:/Windows'))
environment['PATH']=os.pathsep.join(map(str,[Path(sys.executable).parent,Path(sys.base_prefix),Path(sys.base_prefix)/'DLLs',ROOT/'.venv/Lib/site-packages/PySide6',windows/'System32',windows]))
subprocess.run(command,cwd=ROOT,env=environment,check=True)
shutil.copytree(staging/'dist/MCPS',output)
shutil.copy2(ROOT/'README.md',output/'README.md')
shutil.copy2(ROOT/'THIRD_PARTY_NOTICES.md',output/'THIRD_PARTY_NOTICES.md')
manifest={p.relative_to(output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob('*') if p.is_file()}
(ROOT/'output/McPackStudio-artifacts.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
print(f'Built {output}: {len(manifest)} files',flush=True)
