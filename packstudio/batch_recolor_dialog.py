"""Folder-oriented whole-image recolor. No editor canvas or selection state."""
from dataclasses import replace
from types import SimpleNamespace
from PySide6.QtCore import Qt,QSignalBlocker,QEvent
from PySide6.QtGui import QPixmap,QRegion
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QTreeWidget,QTreeWidgetItem,QLabel,QPushButton,QSplitter,QWidget,QSizePolicy,QMessageBox
from .task_progress import run_progress
from .core import decode
from .batch_recolor import plan_whole,preview_files,apply_batch
from .recolor_settings import RecolorSettings

def display_parts(path,descriptor):
    """Trim display ancestors only; keep full paths as all resource identities."""
    if descriptor.get('kind')=='folder':
        root=descriptor.get('path','').strip('/')
        if root and path.startswith(root+'/'):return [root.rsplit('/',1)[-1],*path[len(root)+1:].split('/')]
    if descriptor.get('kind')=='png':return [path.rsplit('/',1)[-1]]
    return path.split('/')

class BatchRecolorDialog(QDialog):
    def __init__(self,window,descriptor):
        super().__init__(window);self.window=window;self.origin=descriptor['origin'];self.owner=window.source(self.origin)
        if self.owner is None:raise ValueError('来源已移除')
        self.output=None;self.busy=False;self.applying=False;self.revision=0;self.current_path=None;self.image=None;self.preview_raw=None;self.scaled_key=None
        snapshot=SimpleNamespace(files=dict(self.owner.files),kind=self.owner.kind)
        self.units,self.baseline,self.metadata,self.errors=run_progress(window,'正在分析批量范围',lambda cancel,progress:plan_whole(snapshot,descriptor,cancel,progress))
        if not self.units:raise ValueError('没有可处理的 PNG。\n'+'\n'.join(p+': '+e for p,e in self.errors))
        from .live_recolor import LivePreview
        self.live=LivePreview(self);self.live.ready.connect(self.receive_preview);self.live.failed.connect(lambda message:self.preview.setText(message))
        self.finished.connect(self.live.stop)
        self.setWindowTitle('批量调色');box=QVBoxLayout(self)
        split=QSplitter();box.addWidget(split,1);self.tree=QTreeWidget();self.tree.setHeaderHidden(True);self.tree.setMinimumWidth(160);self.tree.setIndentation(12);self.tree.setUniformRowHeights(True);split.addWidget(self.tree)
        self.preview=QLabel();self.preview.installEventFilter(self);self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter);self.preview.setMinimumSize(120,140);self.preview.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Ignored);split.addWidget(self.preview);split.setStretchFactor(1,1)
        self.controls=RecolorSettings();box.addWidget(self.controls);self.controls.changed.connect(self.invalidate)
        row=QHBoxLayout();box.addLayout(row);row.addStretch()
        self.apply_button=QPushButton('应用');cancel=QPushButton('取消')
        for button in (self.apply_button,cancel):row.addWidget(button)
        self.apply_button.clicked.connect(lambda:window.run(self.apply));cancel.clicked.connect(self.reject)
        self.apply_button.setEnabled(False);self.leaves={};folders={}
        for unit in self.units:
            parts=display_parts(unit.path,descriptor);parent=None
            for depth,part in enumerate(parts[:-1]):
                key='/'.join(parts[:depth+1])
                if key not in folders:
                    item=QTreeWidgetItem([part]);(parent.addChild(item) if parent else self.tree.addTopLevelItem(item))
                    item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable|Qt.ItemFlag.ItemIsAutoTristate);folders[key]=item
                parent=folders[key]
            leaf=QTreeWidgetItem([parts[-1]]);(parent.addChild(leaf) if parent else self.tree.addTopLevelItem(leaf))
            leaf.setData(0,Qt.ItemDataRole.UserRole,unit.path);leaf.setToolTip(0,unit.path);leaf.setFlags(leaf.flags()|Qt.ItemFlag.ItemIsUserCheckable);leaf.setCheckState(0,Qt.CheckState.Checked);self.leaves[unit.path]=leaf
        for path,error in self.errors:
            item=QTreeWidgetItem([path.rsplit('/',1)[-1]]);item.setToolTip(0,path+'\n'+error);item.setDisabled(True);self.tree.addTopLevelItem(item)
        self.tree.itemChanged.connect(lambda *_:self.invalidate());self.tree.currentItemChanged.connect(self.pick)
        self.tree.expandToDepth(2);self.tree.setCurrentItem(next(iter(self.leaves.values())));self.apply_button.setEnabled(True)
        area=window.screen().availableGeometry();self.resize(min(760,area.width()-32),min(580,area.height()-64));split.setSizes([240,500])
        if self.errors:QMessageBox.warning(self,'部分图片已跳过','\n'.join(p+': '+e for p,e in self.errors))
    def selected_paths(self):
        return {p for p,item in self.leaves.items() if item.checkState(0)==Qt.CheckState.Checked}
    def invalidate(self,*args):
        self.revision+=1;self.output=None;self.apply_button.setEnabled(bool(self.selected_paths()) and not self.applying)
        self.display_preview()
    def pick(self,item,previous=None):
        if item is None:return
        path=item.data(0,Qt.ItemDataRole.UserRole)
        if path in self.baseline:
            self.current_path=path;self.image=None;self.preview.clear();self.display_preview()
    def display_preview(self):
        if self.current_path is not None and not self.applying:
            self.live.request(self.baseline[self.current_path],self.controls.settings())
    def receive_preview(self,image):
        self.image=image;self.scaled_key=None;self.fit_image()
    def fit_image(self):
        if self.image is None:return
        size=self.preview.size();key=(self.image.cacheKey(),size.width(),size.height())
        if self.scaled_key==key:return
        self.scaled_key=key
        small=self.image.scaled(size,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation)
        self.preview.setPixmap(QPixmap.fromImage(small))
    def eventFilter(self,obj,event):
        if obj is getattr(self,'preview',None) and event.type()==QEvent.Type.Resize:self.fit_image()
        return False
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'preview'):self.fit_image()
    def apply(self):
        if self.busy or self.applying:return
        paths=self.selected_paths()
        if not paths:raise ValueError('请勾选要处理的文件夹或 PNG。')
        from .edit_confirmation import batch
        revision=self.revision;settings=self.controls.settings();self.applying=True;self.apply_button.setEnabled(False)
        self.live.cancel.set()
        try:
            if not batch(self.window,self,paths):return
            if revision!=self.revision:raise ValueError('范围或参数已变化，请重新应用。')
            units=[replace(u,allowed=QRegion(u.allowed),mask=QRegion(u.allowed),weights={}) for u in self.units if u.path in paths]
            output=run_progress(self,'正在批量调色',lambda cancel,progress:preview_files(units,dict(self.baseline),settings,cancel,progress))
            if revision!=self.revision:raise ValueError('范围或参数已变化，请重新应用。')
            baseline={p:self.baseline[p] for p in paths};metadata={p+'.mcmeta':self.metadata[p+'.mcmeta'] for p in paths}
            apply_batch(self.window,self.origin,self.owner,baseline,metadata,output);self.accept()
        except InterruptedError:pass
        finally:
            self.applying=False;self.apply_button.setEnabled(bool(self.selected_paths()))
            if not self.live.closed:self.display_preview()
    def reject(self):
        if not self.busy and not self.applying:super().reject()
    def closeEvent(self,event):
        if self.busy or self.applying:event.ignore();return
        super().closeEvent(event)
