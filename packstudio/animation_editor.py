"""Frame views on the main canvas. Source PNG and metadata stay intact."""
import json
import re
from pathlib import PurePosixPath
from PySide6.QtCore import Qt,QTimer,QSize
from PySide6.QtGui import QIcon,QPixmap
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QListWidget,QListWidgetItem,QInputDialog,QMenu
from .texture_animation import timeline


def state_paths(files,path):
    """Recognize explicit vanilla state filenames, never arbitrary numbered art."""
    p=PurePosixPath(path);stem=p.stem
    patterns=(r'(compass|clock)(?:_\d+)?',r'(bow)(?:_standby|_pulling_\d+)?',
              r'(crossbow)(?:_standby|_pulling_\d+|_arrow|_firework)?')
    if '/textures/item/' not in path and '/textures/items/' not in path:return []
    for pattern in patterns:
        match=re.fullmatch(pattern,stem)
        if match:
            candidates=sorted(f for f in files if PurePosixPath(f).parent==p.parent
                              and f.endswith('.png') and re.fullmatch(pattern,PurePosixPath(f).stem)
                              and PurePosixPath(f).stem.startswith(match[1]))
            return candidates if len(candidates)>1 else []
    return []


class AnimationEditor(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window;self.frames=[];self.states=[];self.descriptor=None
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.advance)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        bar=QHBoxLayout();layout.addLayout(bar)
        self.note=QLabel();self.note.setWordWrap(True);bar.addWidget(self.note,1)
        self.mode=QComboBox();self.mode.addItems(['单帧编辑','完整 PNG']);bar.addWidget(self.mode)
        self.play=QPushButton('播放');self.play.setCheckable(True);bar.addWidget(self.play)
        self.manual=QPushButton('确认帧尺寸…');bar.addWidget(self.manual)
        self.cards=QListWidget();self.cards.setFlow(QListWidget.Flow.LeftToRight)
        self.cards.setViewMode(QListWidget.ViewMode.IconMode);self.cards.setWrapping(False)
        self.cards.setStyleSheet('QListWidget::item {height:62px; padding:0 3px;}')
        self.cards.setGridSize(QSize(104,66))
        self.cards.setIconSize(QSize(40,40));self.cards.setFixedHeight(82);layout.addWidget(self.cards)
        self.mode.currentIndexChanged.connect(self.select_view)
        self.cards.currentRowChanged.connect(self.pick)
        self.cards.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.cards.customContextMenuRequested.connect(self.context_menu)
        self.play.toggled.connect(self.playback);self.manual.clicked.connect(self.manual_split)
        window.docks['editor'].widget().layout().addWidget(self)
        window.canvas.changed.connect(self.refresh_icons)
        self.hide()

    def stop(self):
        self.play.setChecked(False);self.timer.stop()

    def reset(self):
        self.stop();self.descriptor=None;self.frames=[];self.states=[];self.hide()

    def open(self,descriptor):
        self.reset()
        if descriptor.get('kind')!='png' or descriptor.get('regions') or not self.window.current:return
        self.descriptor=dict(descriptor);image=self.window.canvas.image
        if image.isNull():return
        files=self.window.editing_files();path=descriptor['path'];note=''
        try:
            self.frames,interpolate=timeline(files.get(path+'.mcmeta'),image.width(),image.height())
            if interpolate:note=' · 预览不模拟插值，配置保留'
        except (ValueError,UnicodeError) as error:note='配置无法解析：'+str(error)
        if self.frames:
            self.populate('时间动画'+note);return
        self.states=state_paths(files,path)
        if self.states:return  # State textures are already listed in associated resources.
        if note or image.height()>image.width() or image.width()>image.height():
            self.note.setText(note or '非方形贴图：未自动拆帧，可确认尺寸后建立帧视图')
            self.mode.hide();self.play.hide();self.cards.hide();self.manual.show();self.show()

    def populate(self,note):
        self.note.setText(note+' · '+str(len(self.frames))+' 项')
        self.cards.blockSignals(True);self.cards.clear()
        for position,(index,rect,ticks) in enumerate(self.frames):
            item=QListWidgetItem(f'{position+1} · 帧 {index}');item.setToolTip(f'源区域 {rect} · {ticks} tick');self.cards.addItem(item)
        self.cards.blockSignals(False);self.refresh_icons()
        self.mode.blockSignals(True);self.mode.setCurrentIndex(0);self.mode.blockSignals(False)
        self.mode.show();self.play.show();self.manual.hide();self.cards.show();self.show()
        self.window.canvas.document_key=(self.descriptor['origin'],self.descriptor['path'])
        self.cards.setCurrentRow(0)

    def refresh_icons(self):
        for pos,(_,rect,_) in enumerate(self.frames):
            if pos<256 or pos==self.cards.currentRow():
                self.cards.item(pos).setIcon(QIcon(QPixmap.fromImage(self.window.canvas.image.copy(*rect).scaled(40,40,Qt.AspectRatioMode.KeepAspectRatio))))
        self.refresh_preview()

    def refresh_preview(self):
        if not self.frames or not self.descriptor:return
        row=self.cards.currentRow()
        if not 0<=row<len(self.frames):return
        # A generated item mesh built from a whole strip has invalid geometry.
        # Show the actual frame in the existing preview surface instead.
        self.window.preview.flat_image=self.window.canvas.image.copy(*self.frames[row][1])
        self.window.preview.update()

    def select_view(self):
        if not self.frames:return
        if self.mode.currentIndex()==1:self.stop()
        self.pick(self.cards.currentRow())

    def pick(self,index):
        if self.states:
            if 0<=index<len(self.states) and self.states[index]!=self.descriptor['path']:
                d={**self.descriptor,'path':self.states[index],'name':PurePosixPath(self.states[index]).name}
                self.window.run(lambda:self.window.edit_descriptor(d))
            return
        if not 0<=index<len(self.frames):return
        canvas=self.window.canvas
        if canvas.drawing:return
        rect=self.frames[index][1] if self.mode.currentIndex()==0 else (0,0,canvas.image.width(),canvas.image.height())
        canvas.set_atlas(canvas.image,[rect],(self.descriptor['origin'],self.descriptor['path']))
        self.refresh_icons()
        if self.play.isChecked():self.timer.start(self.frames[index][2]*50)

    def playback(self,playing):
        self.timer.stop();self.play.setText('暂停' if playing else '播放')
        if self.descriptor:self.window.canvas.read_only=playing or self.window.is_builtin(self.descriptor)
        if playing and self.frames:
            self.mode.setCurrentIndex(0);self.pick(max(0,self.cards.currentRow()))

    def advance(self):
        if not self.play.isChecked() or not self.frames:return
        if not self.window.current or (self.window.current_source,self.window.current[0])!=(self.descriptor['origin'],self.descriptor['path']):
            self.reset();return
        if self.descriptor['path'] not in self.window.editing_files():
            self.reset();return
        row=(self.cards.currentRow()+1)%len(self.frames)
        if row==self.cards.currentRow():self.pick(row)
        else:self.cards.setCurrentRow(row)

    def manual_split(self):
        image=self.window.canvas.image
        width,ok=QInputDialog.getInt(self,'建立帧视图','帧宽（像素）；只改变视图，不写入动画配置',min(image.width(),image.height()),1,image.width())
        if not ok:return
        height,ok=QInputDialog.getInt(self,'建立帧视图','帧高（像素）',min(width,image.height()),1,image.height())
        if not ok:return
        def split():
            self.frames,_=timeline(json.dumps({'animation':{'width':width,'height':height}}).encode(),image.width(),image.height())
            self.populate('手动帧视图 · 预览每帧 1 tick，未写入配置')
        self.window.run(split)

    def hideEvent(self,event):
        self.stop();super().hideEvent(event)

    def frame_descriptor(self,index):
        d=dict(self.descriptor)
        if self.states:return {**d,'path':self.states[index],'name':PurePosixPath(self.states[index]).name}
        x,y,width,height=self.frames[index][1];image=self.window.canvas.image
        return {**d,'kind':'component','name':f'帧 {self.frames[index][0]}','regions':[(x/image.width(),y/image.height(),width/image.width(),height/image.height())]}

    def context_menu(self,pos):
        item=self.cards.itemAt(pos)
        if item is None:return
        index=self.cards.row(item);descriptor=self.frame_descriptor(index)
        if self.states:menu=self.window.resource_menu(descriptor)
        else:
            menu=QMenu(self);menu.setToolTipsVisible(True)
            menu.addAction('选中此帧作为替换来源',lambda:self.window.run(lambda:self.window.select_asset(descriptor)))
            action=menu.addAction('替换为选中',lambda:self.window.run(lambda:self.replace_frame(index)))
            from .capabilities import replacement
            enabled,reason=replacement(self.window,descriptor,frame=True);action.setEnabled(enabled);action.setToolTip(reason)
        menu.exec(self.cards.viewport().mapToGlobal(pos));menu.deleteLater()

    def replace_frame(self,index):
        from .capabilities import replacement
        enabled,reason=replacement(self.window,self.frame_descriptor(index),frame=True)
        if not enabled:raise ValueError(reason)
        if self.window.is_builtin(self.descriptor):raise ValueError('原版只读，请先加入项目副本。')
        from .core import decode
        selected=self.window.selected_asset
        files=(selected or {}).get('files',{})
        pictures=[raw for raw in files.values() if raw.startswith(b'\x89PNG\r\n\x1a\n')]
        if len(pictures)!=1:raise ValueError('请先选中单张 PNG 或单个帧作为替换来源。')
        image=decode(pictures[0]);rect=self.frames[index][1]
        if image.width()!=rect[2] or image.height()!=rect[3]:raise ValueError('帧替换需要相同尺寸，以保留动画布局和配置。')
        self.stop();self.mode.setCurrentIndex(0);self.cards.setCurrentRow(index);self.pick(index)
        canvas=self.window.canvas
        if canvas.view_image()==image:return
        canvas.checkpoint();canvas.replace_view(image);canvas.changed.emit();canvas.update()
