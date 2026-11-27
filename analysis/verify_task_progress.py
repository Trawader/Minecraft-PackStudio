import os,sys
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from threading import Event
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage,QColor,QRegion
from PySide6.QtWidgets import QApplication,QProgressDialog,QPushButton
from packstudio.recolor import render,Settings
from packstudio.task_progress import run_progress
app=QApplication([])
image=QImage(256,256,QImage.Format.Format_ARGB32);image.fill(QColor('#58aabb'))
original=QImage(image);events=[];ticks=[]
timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:ticks.append(1));timer.start()
def work(cancel,report):
    def progress(a,b):events.append(a/b);report(a,b)
    return render(image,QRegion(image.rect()),Settings(mode='adjust',saturation=-40),cancel=cancel,progress=progress)
result=run_progress(None,'调色检查',work)
assert result!=image and image==original and len(ticks)>2
assert events[-1]==1 and events==sorted(events) and any(0<v<1 for v in events)
cancelled=[]
def click_cancel():
    for widget in app.topLevelWidgets():
        if isinstance(widget,QProgressDialog) and widget.isVisible():
            buttons=widget.findChildren(QPushButton)
            if buttons:buttons[0].click();cancelled.append(True)
QTimer.singleShot(30,click_cancel)
try:run_progress(None,'取消检查',work);raise AssertionError('cancel ignored')
except InterruptedError:pass
assert cancelled and image==original
timer.stop()
for mode in ('adjust','middle','opacity'):
    stop=Event();values=[]
    def progress(a,b):
        values.append(a)
        if a>3:stop.set()
    try:render(image,QRegion(image.rect()),Settings(mode=mode),cancel=stop,progress=progress);raise AssertionError('cancel ignored')
    except InterruptedError:pass
    assert image==original
print('PASS intra-image monotonic progress, UI heartbeat, cancel button, cancellation in analysis/render, unchanged original')

from tempfile import TemporaryDirectory
from packstudio.core import import_pack,write_zip
with TemporaryDirectory() as temp:
    path=Path(temp)/'sample.zip';files={'pack.mcmeta':b'{"pack":{"pack_format":1,"description":"test"}}','assets/minecraft/a.txt':b'test'}
    events=[]
    run_progress(None,'写入检查',lambda cancel,report:write_zip(path,files,lambda a,b:(events.append((a,b)),report(a,b))),cancellable=False)
    assert events[-1][0]==events[-1][1]
    loaded=run_progress(None,'读取检查',lambda cancel,report:import_pack(path,cancel,report))
    assert loaded.files==files
    stop=Event();stop.set()
    try:import_pack(path,stop);raise AssertionError('import cancellation ignored')
    except InterruptedError:pass
    assert path.exists() and not path.with_name(path.name+'.writing').exists()
print('PASS import cancellation, progress-enabled ZIP round trip, atomic ZIP temporary cleanup')
