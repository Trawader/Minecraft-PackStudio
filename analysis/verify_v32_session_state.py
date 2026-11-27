"""Project persistence and history boundary handlers; no GUI."""
import sys,tempfile,copy
from pathlib import Path
from types import SimpleNamespace as NS
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from packstudio.core import Layer,save_project,load_project
from packstudio.history_window import History
source=Layer('source',{'assets/demo/a.png':b'original'},source_version='1.20.6',selection={'paths':['assets/demo/a.png']})
layer=copy.deepcopy(source);layer.uid='composition-copy';layer.files={'assets/demo/a.png':b'edited'};layer.library_uid=source.uid
layer.layout_confirmations={'test':{'version':'1.20.6','stable':True}}
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='final-project-') as folder:
    for suffix in ('.MCPSD','.packstudio'):
        path=Path(folder)/('project'+suffix);save_project(path,[layer],'1.20.6',[source])
        layers,version,sources=load_project(path,include_sources=True)
        assert version=='1.20.6' and layers==[layer] and sources==[source]
        layers[0].files['assets/demo/a.png']=b'new edit';assert sources[0].files['assets/demo/a.png']==b'original'
print('PASS project save/reopen and source/copy isolation')
state=NS(done=[],future=[],busy=False,editors=[],flush=lambda:None)
for kind in ('batch','resource','group'):
    state.done=[{'kind':kind}]
    assert not History.available(state) and History.available(state,barriers=True)
    state.future=state.done;assert not History.available(state,redo=True) and History.available(state,redo=True,barriers=True)
state.done=[{'kind':'canvas'}];assert History.available(state)
state.done[-1]['barrier']=True;assert not History.available(state) and History.available(state,barriers=True)
state.done=[{'kind':'blocked'}];assert not History.available(state,barriers=True)
state.done=[{'kind':'canvas'},{'kind':'blocked'},{'kind':'canvas'}]
state.future=[];state.entries=lambda:History.entries(state)
assert not History.can_rollback(state,0) and History.can_rollback(state,1) and not History.can_rollback(state,2)
print('PASS global batch/resource/large-image barriers and rollback boundaries')
