"""Run pure image work off the UI thread with modal, cancellable progress."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from PySide6.QtCore import QEventLoop,QTimer,Qt
from PySide6.QtWidgets import QProgressDialog


def run_progress(parent,title,work,cancellable=True):
    cancel=Event();latest=[0,0]
    class ProgressDialog(QProgressDialog):
        def reject(self):
            if cancellable:super().reject()
        def closeEvent(self,event):
            if cancellable:super().closeEvent(event)
            else:event.ignore()
    dialog=ProgressDialog(title,'取消',0,0,parent)
    if not cancellable:dialog.setCancelButton(None)
    dialog.setWindowTitle(title);dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
    dialog.setMinimumDuration(0);dialog.setAutoClose(False);dialog.setAutoReset(False)
    dialog.canceled.connect(cancel.set)
    loop=QEventLoop();timer=QTimer();timer.setInterval(40)
    pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='image-task')
    def report(done,total):latest[:]=[done,total]
    future=pool.submit(work,cancel,report)
    def poll():
        done,total=latest
        if not cancel.is_set():
            dialog.setRange(0,total);dialog.setValue(done)
            if total:dialog.setLabelText(f'{title} · {done * 100 // total}%')
        if future.done():loop.quit()
    timer.timeout.connect(poll);dialog.show();timer.start()
    try:
        loop.exec()
        if cancel.is_set():raise InterruptedError('已取消，原图未修改。')
        return future.result()
    finally:
        timer.stop();dialog.hide();dialog.deleteLater();pool.shutdown(wait=False,cancel_futures=True)


def encode_image(parent,image):
    from .core import png
    from PySide6.QtGui import QImage
    if image.width()*image.height()<=1024*1024:return png(image)
    snapshot=QImage(image)
    return run_progress(parent,'正在保存原尺寸图像',lambda cancel,progress:png(snapshot),cancellable=False)
