"""Bounded asynchronous single-image previews, independent of canvas selections."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from PySide6.QtCore import Qt,QObject,QTimer,Signal
from PySide6.QtGui import QRegion
from .core import decode
from .recolor import render

class PreviewRenderer:
    def __init__(self):self.raw=None;self.image=None
    def render(self,raw,settings,cancel):
        if cancel.is_set():raise InterruptedError()
        if raw is not self.raw:
            image=decode(raw)
            if max(image.width(),image.height())>512:image=image.scaled(512,512,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation)
            if cancel.is_set():raise InterruptedError()
            self.raw=raw;self.image=image
        return render(self.image,QRegion(self.image.rect()),settings,cancel=cancel)

class LivePreview(QObject):
    ready=Signal(object)
    failed=Signal(str)
    def __init__(self,parent):
        super().__init__(parent);self.renderer=PreviewRenderer();self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='recolor-preview')
        self.future=None;self.pending=None;self.revision=0;self.closed=False;self.cancel=Event()
        self.delay=QTimer(self);self.delay.setSingleShot(True);self.delay.timeout.connect(self.launch)
        self.poll=QTimer(self);self.poll.setInterval(40);self.poll.timeout.connect(self.collect)
    def request(self,raw,settings):
        if self.closed:return
        self.revision+=1;self.cancel.set();self.pending=(self.revision,raw,settings);self.delay.start(100)
    def launch(self):
        if self.closed or self.pending is None:return
        if self.future is not None:self.delay.start(40);return
        self.job_revision,raw,settings=self.pending;self.pending=None;self.cancel=Event()
        self.future=self.pool.submit(self.renderer.render,raw,settings,self.cancel);self.poll.start()
    def collect(self):
        if self.future is None or not self.future.done():return
        future=self.future;self.future=None;self.poll.stop()
        try:result=future.result()
        except InterruptedError:return
        except Exception as error:
            if not self.closed and self.job_revision==self.revision:self.failed.emit(str(error))
            return
        if not self.closed and self.job_revision==self.revision:self.ready.emit(result)
    def stop(self,*args):
        self.closed=True;self.cancel.set();self.pending=None;self.delay.stop();self.poll.stop();self.pool.shutdown(wait=False,cancel_futures=True)
