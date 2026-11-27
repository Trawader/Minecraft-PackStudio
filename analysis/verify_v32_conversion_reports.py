"""Conversion reports are out-of-band and reviewed before mutation; no GUI."""
import sys,json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtGui import QImage
from packstudio.core import Layer,Vanilla,decode,png
from packstudio.conversion import convert_pack,conversion_issues,review_conversion
from packstudio.layouts import confirm_layout
v=Vanilla();path='assets/minecraft/textures/gui/icons.png'
image=decode(v.get('1.8.9',path));tall=QImage(image.width(),image.height()*2,image.format());tall.fill(0)
source=Layer('custom atlas',{path:png(tall),'packstudio-conversion-report.json':b'ordinary user file, not JSON'},source_version='1.8.9')
confirm_layout(source,path,'1.8.9');before=dict(source.files);report=[]
converted=convert_pack(source,v,'1.20.6','1.8.9',report_out=report)
assert any(r['path']==path and r['action']=='omitted' for r in report),report
assert converted.files['packstudio-conversion-report.json']==before['packstudio-conversion-report.json']
assert source.files==before and source.source_version=='1.8.9'
issues=conversion_issues(converted,report);assert any(r['action']=='omitted' for r in issues)
print('PASS custom atlas omission reaches real conversion report; user file preserved')
source=Layer('model',{'assets/minecraft/models/block/stone.json':json.dumps({'textures':{'all':'minecraft:block/nonexistent_test_texture'}}).encode()},source_version='1.20.1')
report=[];converted=convert_pack(source,v,'1.20.1','1.8.9',report_out=report)
assert any('nonexistent_test_texture' in r['detail'] for r in conversion_issues(converted,report))
assert 'packstudio-conversion-report.json' not in converted.files
print('PASS final model missing reference detected without inserting report')
# Run the review decision handler with a minimal dialog substitute.
class Box:
    ButtonRole=NS(AcceptRole=1,RejectRole=2)
    proceed=False
    def __init__(self,*args):self.buttons={}
    def __getattr__(self,name):return lambda *args:None
    def addButton(self,label,role):self.buttons[role]=object();return self.buttons[role]
    def clickedButton(self):return self.buttons[1 if self.proceed else 2]
window=NS(tr=lambda zh,en:zh)
with patch('PySide6.QtWidgets.QMessageBox',Box):
    initial=list(report)
    assert not review_conversion(window,converted,report) and report==initial
    Box.proceed=True
    assert review_conversion(window,converted,report) and any(r.get('accepted') for r in report)
print('PASS return/continue decisions and accepted-issue recording')
