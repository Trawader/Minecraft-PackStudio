"""Validate Test distribution without launching its GUI."""
import hashlib,json,types
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader
ROOT=Path(__file__).resolve().parents[1]
output=ROOT/'output/McPackStudioTest'
exe=output/'MCPSTest.exe'
archive=CArchiveReader(str(exe))
pyz=archive.open_embedded_archive('PYZ.pyz')
identity={}
exec(pyz.extract('packstudio.release'),identity)
assert identity['APP_TITLE']=='Minecraft Pack Studio Test'
assert identity['EXECUTABLE_NAME']=='MCPSTest'
assert identity['VERSION'].endswith('test')
modules=[]
for p in (ROOT/'packstudio').glob('*.py'):
    name='packstudio' if p.stem=='__init__' else 'packstudio.'+p.stem
    assert name in pyz.toc,name
    code=pyz.extract(name)
    expected=compile(p.read_bytes(),code.co_filename,'exec',optimize=0)
    def equivalent(a,b):
        if isinstance(a,types.CodeType):
            return isinstance(b,types.CodeType) and a.co_code==b.co_code and a.co_names==b.co_names and a.co_varnames==b.co_varnames and len(a.co_consts)==len(b.co_consts) and all(equivalent(x,y) for x,y in zip(a.co_consts,b.co_consts))
        return a==b
    assert equivalent(code,expected),name
    modules.append(name)
assets=0
for directory in ('data','assets'):
    for p in (ROOT/'packstudio'/directory).rglob('*'):
        if not p.is_file():continue
        target=output/'_internal'/p.relative_to(ROOT)
        assert target.is_file(),str(target)
        assert hashlib.sha256(p.read_bytes()).digest()==hashlib.sha256(target.read_bytes()).digest(),str(target)
        assets+=1
for name in ('library','projects','config','reference','.tmp'):
    assert not (output/name).exists(),name
readme=(output/'Readme-Test.txt').read_text(encoding='utf-8-sig')
assert 'MCPSTest.exe' in readme and 'ENGLISH GUIDE' in readme
assert '**' not in readme and 'V3.6' not in readme
report={'status':'passed','modules_match_current_source':len(modules),'assets_match':assets,'identity':'Test','personal_data':'absent','gui_launched':False,'bytes':sum(p.stat().st_size for p in output.rglob('*') if p.is_file())}
(ROOT/'analysis/test-packaged-static-check.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report,indent=2))
