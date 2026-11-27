"""Shared RGBA / HSVA editor with a compact selectable swatch sheet."""
from PySide6.QtCore import QSignalBlocker,Qt,Signal,QPointF
from PySide6.QtGui import QColor,QPainter,QLinearGradient,QPen,QRegularExpressionValidator
from PySide6.QtCore import QRegularExpression
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QSpinBox,QTabWidget,QWidget,QGridLayout,QPushButton,QDialogButtonBox,QLineEdit,QTabBar,QStackedWidget,QScrollArea,QSizePolicy,QApplication


class ColorPlane(QWidget):
    """Mouse-driven HSV controls; alpha belongs to the numeric editor."""
    selected=Signal(float,float)
    def __init__(self,hue_strip=False):
        super().__init__();self.hue_strip=hue_strip;self.hue=0.;self.saturation=0.;self.value=1.
        self.setMinimumSize(20,100) if hue_strip else self.setMinimumSize(100,100)
        if hue_strip:self.setFixedWidth(20)
        self.setCursor(Qt.CursorShape.CrossCursor)
    def paintEvent(self,event):
        p=QPainter(self);w=self.width()-1;h=self.height()-1
        if self.hue_strip:
            gradient=QLinearGradient(0,0,0,h)
            for i in range(7):gradient.setColorAt(i/6,QColor.fromHsvF((i/6)%1,1,1))
            p.fillRect(self.rect(),gradient);y=self.hue*h
            p.setPen(QPen(Qt.GlobalColor.black,3));p.drawLine(QPointF(0,y),QPointF(w,y))
            p.setPen(QPen(Qt.GlobalColor.white,1));p.drawLine(QPointF(0,y),QPointF(w,y))
        else:
            gradient=QLinearGradient(0,0,w,0);gradient.setColorAt(0,QColor('white'));gradient.setColorAt(1,QColor.fromHsvF(self.hue,1,1))
            p.fillRect(self.rect(),gradient)
            shade=QLinearGradient(0,0,0,h);shade.setColorAt(0,QColor(0,0,0,0));shade.setColorAt(1,QColor('black'));p.fillRect(self.rect(),shade)
            center=QPointF(self.saturation*w,(1-self.value)*h)
            p.setPen(QPen(Qt.GlobalColor.black,3));p.drawEllipse(center,5,5)
            p.setPen(QPen(Qt.GlobalColor.white,1));p.drawEllipse(center,5,5)
        p.end()
    def choose(self,event):
        x=max(0,min(1,event.position().x()/max(1,self.width()-1)))
        y=max(0,min(1,event.position().y()/max(1,self.height()-1)))
        self.selected.emit(y if self.hue_strip else x,1-y)
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.choose(event);event.accept()
    def mouseMoveEvent(self,event):
        if event.buttons() & Qt.MouseButton.LeftButton:self.choose(event);event.accept()


class ColorComparison(QWidget):
    def __init__(self,original):
        super().__init__();self.original=QColor(original);self.color=QColor(original);self.setFixedHeight(24)
    def paintEvent(self,event):
        p=QPainter(self)
        for y in range(0,self.height(),8):
            for x in range(0,self.width(),8):p.fillRect(x,y,8,8,QColor('#aaa' if (x//8+y//8)%2 else '#ddd'))
        half=self.width()//2;p.fillRect(0,0,half,self.height(),self.original);p.fillRect(half,0,self.width()-half,self.height(),self.color);p.end()


class ColorEditor(QDialog):
    colorChanged=Signal(QColor)
    def __init__(self,color,parent=None,embedded=False):
        super().__init__(parent);self.setWindowTitle('调色 · RGBA / HSVA / 色板');self.color=QColor(color)
        self.embedded=embedded
        if embedded:self.setWindowFlags(Qt.WindowType.Widget)
        self.hue=max(0,self.color.hsvHueF())
        layout=QVBoxLayout(self);layout.setContentsMargins(10,10,10,10);layout.setSpacing(6)
        self.tabs=QTabBar();self.tabs.addTab('RGBA');self.tabs.addTab('HSVA');self.tabs.addTab('色板');layout.addWidget(self.tabs)
        self.visual=QStackedWidget();self.visual.setMinimumHeight(110);self.visual.setMaximumHeight(200);layout.addWidget(self.visual,1)
        picker=QWidget();planes=QHBoxLayout(picker);planes.setContentsMargins(0,0,0,0);planes.setSpacing(6)
        self.plane=ColorPlane();self.hue_strip=ColorPlane(True);planes.addWidget(self.plane,1);planes.addWidget(self.hue_strip)
        self.visual.addWidget(picker)
        self.plane.selected.connect(self.choose_sv);self.hue_strip.selected.connect(self.choose_hue)
        sheet=QWidget();grid=QGridLayout(sheet);grid.setContentsMargins(2,2,2,2);grid.setSpacing(1)
        self.swatch_scroll=QScrollArea();self.swatch_scroll.setWidgetResizable(True);self.swatch_scroll.setWidget(sheet)
        self.swatch_scroll.setFrameShape(QScrollArea.Shape.NoFrame);self.visual.addWidget(self.swatch_scroll)
        for row in range(13):
            for column in range(24):
                swatch=QColor.fromHsv(round(column*359/23),255 if row<6 else round(255*(12-row)/6),round(255*(1-row/7)) if row<6 else 255)
                if row==12:swatch=QColor(round(column*255/23),round(column*255/23),round(column*255/23))
                button=QPushButton();button.setFixedSize(14,14);button.setStyleSheet('background:'+swatch.name()+';border:1px solid #666;padding:0;border-radius:1px;')
                button.setToolTip(swatch.name());button.clicked.connect(lambda checked=False,c=swatch:self.choose_swatch(c));grid.addWidget(button,row,column)
        labels=QHBoxLayout();labels.addWidget(QLabel('当前颜色'));labels.addWidget(QLabel('新颜色'));layout.addLayout(labels)
        self.comparison=ColorComparison(color);layout.addWidget(self.comparison)
        # Kept as a nonvisual compatibility field; the comparison already shows color.
        self.preview=QLabel(self);self.preview.hide()
        hex_row=QHBoxLayout();hex_row.addWidget(QLabel('HEX'));self.hex=QLineEdit();hex_row.addWidget(self.hex);layout.addLayout(hex_row)
        self.hex.setValidator(QRegularExpressionValidator(QRegularExpression('#?[0-9a-fA-F]{0,6}'),self.hex))
        self.hex.textEdited.connect(self.read_hex);self.hex.editingFinished.connect(self.sync)
        self.fields={};self.numeric=QStackedWidget();layout.addWidget(self.numeric)
        self.numeric.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Maximum)
        for mode,letters,limits in [('RGBA','RGBA',(255,255,255,255)),('HSVA','HSVA',(359,100,100,255))]:
            page=QWidget();grid=QGridLayout(page);grid.setContentsMargins(0,0,0,0);grid.setSpacing(4);fields=[]
            for i,(label,limit) in enumerate(zip(letters,limits)):
                grid.addWidget(QLabel(label),i//2,(i%2)*2);spin=QSpinBox();spin.setRange(0,limit);grid.addWidget(spin,i//2,(i%2)*2+1);fields.append(spin)
                spin.valueChanged.connect(lambda value,m=mode:self.read_fields(m))
            self.fields[mode]=fields;self.numeric.addWidget(page)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('确定');self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject)
        footer=QHBoxLayout();self.opacity_label=QLabel();footer.addWidget(self.opacity_label)
        self.opacity=QSpinBox();self.opacity.setRange(0,255);self.opacity.setKeyboardTracking(False)
        self.opacity.setAccessibleName('Alpha');footer.addWidget(self.opacity)
        self.opacity_percent=QLabel();footer.addWidget(self.opacity_percent)
        footer.addStretch();footer.addWidget(self.buttons);layout.addLayout(footer)
        self.opacity.valueChanged.connect(self.read_opacity)
        self.buttons.setVisible(not embedded)
        self.tabs.currentChanged.connect(self.change_mode);self.sync();self.resize(400,420)
    def change_mode(self,index):
        self.visual.setCurrentIndex(1 if index==2 else 0)
        self.numeric.setVisible(index!=2)
        if index!=2:self.numeric.setCurrentIndex(index)
    def showEvent(self,event):
        super().showEvent(event)
        if self.embedded:return
        screen=self.screen() or QApplication.primaryScreen()
        if screen:
            available=screen.availableGeometry()
            # Qt geometry is in logical pixels; reserve native frame/title space.
            width=min(400,max(240,available.width()-32));height=min(420,max(270,available.height()-64))
            self.resize(width,height)
            self.move(available.x()+(available.width()-self.width())//2,available.y()+(available.height()-self.height())//2)
    def choose_swatch(self,color):
        self.color=QColor(color);self.color.setAlpha(self.fields['RGBA'][3].value());self.sync()
    def choose_sv(self,saturation,value):
        self.color=QColor.fromHsvF(self.hue,saturation,value,self.color.alphaF());self.sync()
    def choose_hue(self,hue,_value):
        self.hue=min(359/360,hue)
        self.color=QColor.fromHsvF(self.hue,self.color.hsvSaturationF(),self.color.valueF(),self.color.alphaF());self.sync()
    def read_hex(self,value):
        digits=value.removeprefix('#')
        if len(digits)!=6:return
        color=QColor('#'+digits)
        if color.isValid():self.color=color;self.color.setAlpha(self.fields['RGBA'][3].value());self.sync()
    def read_fields(self,mode):
        values=[field.value() for field in self.fields[mode]]
        self.color=QColor(*values) if mode=='RGBA' else QColor.fromHsvF(values[0]/360,values[1]/100,values[2]/100,values[3]/255)
        if mode=='HSVA':self.hue=values[0]/360
        self.sync(mode)
    def read_opacity(self,value):
        self.color.setAlpha(value);self.sync()
    def sync(self,skip=None):
        h,s,v,a=self.color.getHsvF()
        if h>=0:self.hue=h
        values={'RGBA':self.color.getRgb(),'HSVA':(min(359,round(self.hue*360)),round(s*100),round(v*100),self.color.alpha())}
        for mode,fields in self.fields.items():
            if mode==skip:continue
            for field,value in zip(fields,values[mode]):
                blocker=QSignalBlocker(field);field.setValue(value);del blocker
        self.preview.setText(self.color.name(QColor.NameFormat.HexArgb));self.preview.setStyleSheet('background:'+self.color.name()+';color:'+('#000' if self.color.lightness()>127 else '#fff')+';padding:4px;')
        blocker=QSignalBlocker(self.hex);self.hex.setText(self.color.name().upper());del blocker
        self.comparison.color=QColor(self.color);self.comparison.update()
        for control in (self.plane,self.hue_strip):
            control.hue=self.hue;control.saturation=s;control.value=v;control.update()
        from .localization import text
        owner=self.parentWidget()
        while owner is not None and not hasattr(owner,'lang'):owner=owner.parentWidget()
        label=text('不透明度',getattr(owner,'lang','zh'))
        self.opacity_label.setText(label)
        with QSignalBlocker(self.opacity):self.opacity.setValue(self.color.alpha())
        self.opacity_percent.setText(f'{self.color.alpha()*100/255:.1f}%')
        self.colorChanged.emit(QColor(self.color))

    def set_color(self,color):
        with QSignalBlocker(self):
            self.color=QColor(color);self.comparison.original=QColor(color);self.sync()


def choose_color(color,parent):
    dialog=ColorEditor(color,parent)
    try:return QColor(dialog.color) if dialog.exec()==QDialog.DialogCode.Accepted else QColor()
    finally:dialog.deleteLater()
