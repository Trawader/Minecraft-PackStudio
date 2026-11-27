"""Reusable recolor settings, independent of every canvas and file owner."""
from PySide6.QtCore import Signal,QSize
from PySide6.QtGui import QColor,QIcon,QPixmap
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QComboBox,QPushButton,QLabel,QSpinBox
from .color_controls import ColorControls
from .recolor import Settings

class RecolorSettings(QWidget):
    changed=Signal()
    def __init__(self,parent=None):
        super().__init__(parent);box=QVBoxLayout(self);box.setContentsMargins(0,0,0,0)
        row=QHBoxLayout();box.addLayout(row);self.mode=QComboBox()
        for label,key in [('明暗渐变','range'),('透明度','opacity'),('颜色','color')]:self.mode.addItem(label,key)
        row.addWidget(self.mode);self.colors=['#AA96F8','#EEE6FF'];self.buttons=[]
        for index in range(2):
            button=QPushButton();row.addWidget(button);self.buttons.append(button)
            button.clicked.connect(lambda checked=False,i=index:self.choose(i))
        self.alpha_row=QWidget();line=QHBoxLayout(self.alpha_row);line.setContentsMargins(0,0,0,0)
        line.addWidget(QLabel('不透明度%'));self.alpha=QSpinBox();self.alpha.setRange(0,100);self.alpha.setValue(100);line.addWidget(self.alpha);box.addWidget(self.alpha_row)
        self.color=ColorControls(lambda *_:self.changed.emit());box.addWidget(self.color)
        self.alpha.valueChanged.connect(lambda *_:self.changed.emit());self.mode.currentIndexChanged.connect(self.options)
        self.update_colors();self.options()
    def update_colors(self):
        for button,value in zip(self.buttons,self.colors):
            image=QPixmap(20,20);image.fill(QColor(value));button.setIcon(QIcon(image));button.setIconSize(QSize(20,20));button.setText(value.upper())
    def choose(self,index):
        from .color_editor import choose_color
        color=choose_color(QColor(self.colors[index]),self)
        if color.isValid():self.colors[index]=color.name();self.update_colors();self.changed.emit()
    def options(self):
        mode=self.mode.currentData()
        for button in self.buttons:button.setVisible(mode=='range')
        self.alpha_row.setVisible(mode=='opacity');self.color.setVisible(mode=='color');self.changed.emit()
    def settings(self):
        return Settings(mode=self.mode.currentData(),first=self.colors[0],last=self.colors[1],opacity=self.alpha.value(),**self.color.values())
