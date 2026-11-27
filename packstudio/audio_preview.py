"""Resource-byte playback; no audio editing, conversion or extracted temp files."""
import copy
from pathlib import Path
from PySide6.QtCore import QBuffer,QByteArray,QIODevice,QUrl
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QFileDialog
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
from .sounds import is_audio


class AudioPreview(QWidget):
    def __init__(self,window):
        super().__init__(window.preview_stack);self.setObjectName('audio-preview');self.window=window;self.descriptor=None
        layout=QVBoxLayout(self)
        self.caption=QLabel();self.caption.setWordWrap(True);layout.addWidget(self.caption)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        row=QHBoxLayout();layout.addLayout(row)
        self.play_button=QPushButton(window.tr('播放','Play'));row.addWidget(self.play_button)
        stop=QPushButton(window.tr('停止','Stop'));row.addWidget(stop)
        self.replace_button=QPushButton(window.tr('替换 OGG…','Replace OGG…'));layout.addWidget(self.replace_button)
        add=QPushButton(window.tr('加入项目（含关联声音定义）','Add to project with sound definitions'));layout.addWidget(add)
        add.setToolTip(window.tr('若声音定义引用了该文件，会一并保留完整定义和包内依赖，可能包含其他音效。','If a sound definition refers to this file, its complete definition and in-pack dependencies are included, possibly including other sounds.'))
        layout.addStretch();self.setMinimumWidth(260)
        self.player=QMediaPlayer(self);self.output=QAudioOutput(self);self.player.setAudioOutput(self.output)
        self.buffer=QBuffer(self);self.output.setVolume(.5)
        self.play_button.clicked.connect(lambda:window.run(self.play));stop.clicked.connect(self.stop)
        self.replace_button.clicked.connect(lambda:window.run(self.replace_file));add.clicked.connect(lambda:window.run(lambda:window.add_to_composition(self.descriptor)) if self.descriptor else None)
        self.player.errorOccurred.connect(lambda error,message:self.status.setText(window.tr('无法播放：','Cannot play: ')+message))
        self.player.playbackStateChanged.connect(self.playback_state)
        window.preview_stack.addWidget(self)
    def hideEvent(self,event):
        self.stop();super().hideEvent(event)
    def playback_state(self,state):
        if self.player.error()!=QMediaPlayer.Error.NoError:return
        self.status.setText(self.window.tr('播放中','Playing') if state==QMediaPlayer.PlaybackState.PlayingState else self.window.tr('已停止','Stopped'))
    def stop(self):
        self.player.stop()
    def raw(self):
        if not self.descriptor:raise ValueError('未选择音效')
        owner=self.window.source(self.descriptor['origin'])
        if owner is None or self.descriptor['path'] not in owner.files:raise ValueError('音效来源已移除')
        return owner,owner.files[self.descriptor['path']]
    def open(self,descriptor):
        self.stop();self.descriptor=copy.deepcopy(descriptor);owner,raw=self.raw()
        self.player.setSource(QUrl());self.buffer.close();self.buffer.setData(QByteArray(raw));self.buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self.player.setSourceDevice(self.buffer,QUrl('file:///preview.ogg'))
        prefix=self.window.tr('项目副本','Project copy') if descriptor['origin'].startswith('stage:') else self.window.tr('素材库本体','Library asset')
        self.caption.setText(prefix+' · '+owner.name+'\n'+descriptor['path']+f'\n{len(raw):,} bytes')
        self.status.setText(self.window.tr('点击播放试听；原始路径保持不变。','Click Play to preview; the original path is preserved.'))
        self.replace_button.setEnabled(not self.window.is_builtin(descriptor))
        self.window.set_preview_page(self)
        self.window.docks['render'].show();self.window.docks['render'].raise_()
    def play(self):
        self.raw();self.player.setPosition(0);self.player.play()
    def replace_file(self):
        path,_=QFileDialog.getOpenFileName(self,self.window.tr('替换音效','Replace sound'),'','OGG (*.ogg)')
        if path:
            if Path(path).stat().st_size>256*1024**2:raise ValueError('音效超过 256 MiB')
            self.replace_bytes(Path(path).read_bytes())
    def replace_bytes(self,raw):
        from .resource_history import transaction
        with transaction(self.window,self.descriptor['origin']):return self._replace_bytes(raw)
    def _replace_bytes(self,raw):
        if self.window.is_builtin(self.descriptor):raise ValueError('原版素材只读，请先加入项目')
        if not raw.startswith(b'OggS'):raise ValueError('请选择有效的 OGG 容器；不会自动转换音频格式')
        owner,_=self.raw();self.stop();self.window.remember();owner.files[self.descriptor['path']]=raw
        if self.descriptor['origin'].startswith('stage:'):self.window.changed()
        else:self.window.library_store.put(owner)
        self.window.refresh();self.open(self.descriptor)


def open_sound(window,descriptor):
    if not hasattr(window,'audio_preview'):window.audio_preview=AudioPreview(window)
    window.audio_preview.open(descriptor)


def add_actions(window,menu,descriptor):
    if not is_audio(descriptor.get('path','')):return
    stable=copy.deepcopy(descriptor);menu.addSeparator()
    action=menu.addAction(window.tr('音效预览／替换…','Sound preview / replace…'))
    action.triggered.connect(lambda:window.run(lambda:open_sound(window,stable)))
    action=menu.addAction(window.tr('停止音效','Stop sound'))
    action.triggered.connect(lambda:window.audio_preview.stop() if hasattr(window,'audio_preview') else None)
