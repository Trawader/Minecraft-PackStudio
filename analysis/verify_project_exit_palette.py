"""Save-choice/recovery ordering and palette derivation, without GUI windows."""
import sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from types import SimpleNamespace as NS
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from packstudio.ui import Window
from packstudio.studio import StudioWindow
from packstudio.derivation_reference import material_ramp,ramp_transfer
from PySide6.QtGui import QImage,QColor

class Box:
    Icon=NS(Question=1);ButtonRole=NS(AcceptRole=1,DestructiveRole=2,RejectRole=3)
    choice=1
    def __init__(self,*args):self.buttons={}
    def setWindowTitle(self,*args):pass
    def setText(self,*args):pass
    def setIcon(self,*args):pass
    def setDefaultButton(self,*args):pass
    def setEscapeButton(self,*args):pass
    def addButton(self,label,role):self.buttons[role]=object();return self.buttons[role]
    def exec(self):pass
    def clickedButton(self):return self.buttons.get(self.choice)
    @staticmethod
    def warning(*args):pass
for choice,outcome,expected in [(1,'ok',True),(1,'cancel',False),(1,'fail',False),(2,'unused',True),(3,'unused',False),(0,'unused',False)]:
    state=NS(dirty=True,tr=lambda zh,en:en);calls=[]
    def save():
        calls.append(1)
        if outcome=='fail':raise OSError('disk full')
        if outcome=='ok':state.dirty=False
    state.save=save;Box.choice=choice
    with patch('packstudio.ui.QMessageBox',Box):assert Window.discard_ok(state)==expected
    assert len(calls)==int(choice==1)
print('PASS save/discard/cancel/window-close, canceled save dialog, failed save')
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'Recovery-test.MCPSD';gate=Event();pool=ThreadPoolExecutor(max_workers=1)
    future=pool.submit(lambda:(gate.wait(),path.write_bytes(b'latest snapshot')))
    state=NS(draft_path=path,draft_timer=NS(stop=lambda:None),draft_revision=7,drafts_enabled=True,draft_executor=pool)
    StudioWindow.clear_recovery(state);gate.set();pool.shutdown(wait=True)
    assert not path.exists() and state.draft_saved_revision==7 and state.draft_path.suffix=='.MCPSD'
print('PASS recovery cleanup follows pending write; no recreation on clean exit')
im=QImage(8,1,QImage.Format.Format_RGBA8888)
for x in range(8):im.setPixelColor(x,0,QColor(30+x*25,30+x*25,30+x*25,127))
mask=bytearray([0,1,1,1,1,1,1,1]);original=im.copy();ramp=((60,25,0),(180,115,10),(255,235,150))
out=ramp_transfer(im,mask,ramp)
assert out.size()==im.size() and im==original and out.pixelColor(0,0)==im.pixelColor(0,0)
assert all(out.pixelColor(x,0).alpha()==127 for x in range(8))
assert all(out.pixelColor(x,0).red()<=out.pixelColor(x+1,0).red() for x in range(1,7))
assert ramp_transfer(im,mask,ramp,0)==im
ref=QImage(3,1,QImage.Format.Format_RGBA8888)
for x,c in enumerate(ramp):ref.setPixelColor(x,0,QColor(*c))
assert material_ramp(ref,bytes([1]*3))==ramp
assert ramp_transfer(im,mask,material_ramp(ref,bytes([1]*3))).size()==im.size()
print('PASS source detail ordering, alpha/mask/source isolation, zero strength, different reference resolution')
