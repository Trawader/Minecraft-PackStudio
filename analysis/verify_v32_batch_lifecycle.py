"""Pure batch lifecycle checks: no GUI creation or source-pack writes."""
import sys
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from threading import Event
from concurrent.futures import Future
from collections import deque
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from packstudio.batch_recolor import apply_batch,undo_batch
from packstudio.batch_recolor_dialog import BatchRecolorDialog

def fixture():
    owner=NS(uid='source',files={'a.png':b'original','other':b'untouched'})
    w=NS(source=lambda origin:owner,is_builtin=lambda d:False,current_source=None,dirty=False,
         changed=lambda:None,refresh=lambda:None,setWindowModified=lambda v:None)
    return w,owner

def rejected(fn):
    try:fn()
    except (ValueError,OSError):return
    raise AssertionError('Expected rejection')

for failure in ('source','bytes','metadata','outside','save'):
    w,o=fixture();baseline={'a.png':b'original'};meta={'a.png.mcmeta':None};output={'a.png':b'edited'}
    if failure=='source':w.source=lambda origin:None
    if failure=='bytes':o.files['a.png']=b'newer'
    if failure=='metadata':o.files['a.png.mcmeta']=b'new metadata'
    if failure=='outside':output['unexpected.png']=b'bad'
    before=dict(o.files)
    with patch('packstudio.batch_recolor.persist',side_effect=OSError('disk failure') if failure=='save' else None):
        rejected(lambda:apply_batch(w,'source',o,baseline,meta,output))
    assert o.files==before and not getattr(w,'batch_recolor_history',[])
print('PASS rejected writes and save rollback')
w,o=fixture()
with patch('packstudio.batch_recolor.persist'):
    assert apply_batch(w,'source',o,{'a.png':b'original'},{'a.png.mcmeta':None},{'a.png':b'edited'})==1
    assert len(w.batch_recolor_history)==1
    o.files['a.png']=b'newer';rejected(lambda:undo_batch(w));assert o.files['a.png']==b'newer'
    o.files['a.png']=b'edited';assert undo_batch(w)==1
    assert o.files=={'a.png':b'original','other':b'untouched'} and not w.batch_recolor_history
print('PASS apply/undo and later-edit protection')
# Apply now calculates the batch only after explicit confirmation.
from PySide6.QtGui import QRegion
from packstudio.batch_recolor import Unit
from packstudio.recolor import Settings
button=NS(setEnabled=lambda value:None)
def dialog():
    return NS(busy=False,applying=False,revision=0,selected_paths=lambda:{'a.png'},
        units=[Unit('a.png',(0,0,1,1),QRegion(0,0,1,1))],controls=NS(settings=lambda:Settings()),
        baseline={'a.png':b'original'},metadata={'a.png.mcmeta':None},window=NS(),origin='source',owner=NS(),
        live=NS(cancel=Event(),closed=False),apply_button=button,display_preview=lambda:None,accept=lambda:None)
for answer in (False,True):
    state=dialog()
    with patch('packstudio.edit_confirmation.batch',return_value=answer),patch('packstudio.batch_recolor_dialog.run_progress',side_effect=InterruptedError) as work,patch('packstudio.batch_recolor_dialog.apply_batch') as commit:
        BatchRecolorDialog.apply(state);commit.assert_not_called();assert work.call_count==int(answer)
    assert not state.applying
print('PASS declined confirmation and canceled calculation never write')
state=dialog()
def confirm(*args):state.revision+=1;return True
with patch('packstudio.edit_confirmation.batch',side_effect=confirm),patch('packstudio.batch_recolor_dialog.apply_batch') as commit:
    rejected(lambda:BatchRecolorDialog.apply(state));commit.assert_not_called()
assert not state.applying
print('PASS confirmation revalidates scope and settings')
