"""Shared compact controls for whole-image balance and feathered hue bands."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QSlider,QSpinBox,QGridLayout

class ColorControls(QWidget):
    def __init__(self,changed,parent=None):
        super().__init__(parent);box=QVBoxLayout(self);box.setContentsMargins(0,0,0,0)
        self.kind=QComboBox();self.kind.addItem('色彩平衡','balance');self.kind.addItem('分色调整','bands');box.addWidget(self.kind)
        self.band=QComboBox();self.band.addItems(['红','黄','绿','青','蓝','品红']);box.addWidget(self.band)
        self.fields={};self.rows={}
        grid=QGridLayout();grid.setContentsMargins(0,0,0,0);grid.setColumnStretch(1,1);box.addLayout(grid)
        for key,label,limit in [('red','青 ↔ 红',100),('green','品红 ↔ 绿',100),('blue','黄 ↔ 蓝',100),('hue_shift','色相',180),('band_saturation','饱和度',100),('band_lightness','明度',100)]:
            item=QLabel(label);item.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter);slider=QSlider(Qt.Orientation.Horizontal);slider.setRange(-limit,limit);spin=QSpinBox();spin.setRange(-limit,limit)
            row=len(self.fields);grid.addWidget(item,row,0);grid.addWidget(slider,row,1);grid.addWidget(spin,row,2);self.fields[key]=(item,spin);self.rows[key]=(item,slider,spin)
            slider.valueChanged.connect(spin.setValue);spin.valueChanged.connect(slider.setValue);spin.valueChanged.connect(changed)
        self.kind.currentIndexChanged.connect(self.options);self.kind.currentIndexChanged.connect(changed);self.band.currentIndexChanged.connect(changed);self.options()

    def options(self):
        balance=self.kind.currentData()=='balance';self.band.setVisible(not balance)
        for key,widgets in self.rows.items():
            for widget in widgets:widget.setVisible((key in ('red','green','blue'))==balance)

    def values(self):
        return dict(color_kind=self.kind.currentData(),color_band=self.band.currentIndex(),**{key:spin.value() for key,(_,spin) in self.fields.items()})
