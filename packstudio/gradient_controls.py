"""Compact transition settings with bounded, monotonic curve handles."""
from PySide6.QtCore import Qt,QPointF,QRectF,Signal,QTimer
from PySide6.QtGui import QColor,QPainter,QPen,QPainterPath
from PySide6.QtWidgets import QWidget,QFormLayout,QVBoxLayout,QComboBox,QSpinBox,QPushButton,QSizePolicy
from .gradient_transition import transition_value


class CurveEditor(QWidget):
    changed=Signal(object)
    def __init__(self):
        super().__init__();self.points=[(0.,0.),(1.,1.)];self.drag=-1
        self.setMinimumSize(180,160);self.setMouseTracking(True)
    def plot(self):return QRectF(self.rect()).adjusted(12,12,-12,-12)
    def screen(self,p):
        r=self.plot();return QPointF(r.left()+p[0]*r.width(),r.bottom()-p[1]*r.height())
    def value(self,pos):
        r=self.plot();return (max(0.,min(1.,(pos.x()-r.left())/max(1,r.width()))),max(0.,min(1.,(r.bottom()-pos.y())/max(1,r.height()))))
    def hit(self,pos):
        return next((i for i,p in enumerate(self.points) if (self.screen(p)-pos).manhattanLength()<12),-1)
    def publish(self):self.update();self.changed.emit(tuple(self.points))
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.fillRect(self.rect(),QColor('#252525'));r=self.plot()
        p.setPen(QPen(QColor('#414141'),1))
        for i in range(5):
            x=r.left()+r.width()*i/4;y=r.top()+r.height()*i/4
            p.drawLine(QPointF(x,r.top()),QPointF(x,r.bottom()));p.drawLine(QPointF(r.left(),y),QPointF(r.right(),y))
        path=QPainterPath();path.moveTo(self.screen(self.points[0]))
        for point in self.points[1:]:path.lineTo(self.screen(point))
        p.setPen(QPen(QColor('#55bfff'),2));p.drawPath(path)
        p.setBrush(QColor('#dddddd'))
        for point in self.points:p.drawEllipse(self.screen(point),4,4)
    def mousePressEvent(self,event):
        index=self.hit(event.position())
        if event.button()==Qt.MouseButton.RightButton:
            if 0<index<len(self.points)-1:self.points.pop(index);self.publish()
        elif event.button()==Qt.MouseButton.LeftButton:
            if index<0 and len(self.points)<16:
                x,y=self.value(event.position())
                if .005<x<.995:
                    index=next(i for i in range(1,len(self.points)) if self.points[i][0]>x)
                    if min(x-self.points[index-1][0],self.points[index][0]-x)<.005:return
                    y=max(self.points[index-1][1],min(self.points[index][1],y))
                    self.points.insert(index,(x,y));self.publish()
            self.drag=index if 0<index<len(self.points)-1 else -1
    def mouseMoveEvent(self,event):
        if self.drag<0:return
        x,y=self.value(event.position());a=self.points[self.drag-1];b=self.points[self.drag+1]
        self.points[self.drag]=(max(a[0]+.005,min(b[0]-.005,x)),max(a[1],min(b[1],y)));self.publish()
    def mouseReleaseEvent(self,event):self.drag=-1


class TransitionControls(QWidget):
    def __init__(self,panel):
        super().__init__();self.panel=panel;box=QVBoxLayout(self);box.setContentsMargins(0,0,0,0);form=QFormLayout();box.addLayout(form)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.form=form
        tr=panel.window.tr;settings=panel.tool_settings['gradient'];self.fields={}
        for key,label,en,low,high,value in [('midpoint','中点（%）','Midpoint (%)',1,99,settings.midpoint),('smooth','过渡宽度（%）','Transition width (%)',0,100,settings.smooth),('steps','色阶数','Levels',2,256,settings.steps)]:
            spin=QSpinBox();spin.setRange(low,high);spin.setValue(value);form.addRow(tr(label,en),spin);self.fields[key]=spin
            spin.valueChanged.connect(lambda v,k=key:self.change(k,v))
        self.mode=QComboBox()
        for zh,en,key in [('平滑','Smooth','smooth'),('阶梯','Steps','steps'),('自定义曲线','Custom curve','curve')]:self.mode.addItem(tr(zh,en),key)
        form.addRow(tr('过渡','Transition'),self.mode)
        self.strip=TransitionStrip(settings);box.addWidget(self.strip)
        self.curve=CurveEditor();box.addWidget(self.curve)
        self.curve.setToolTip(tr('左键添加或拖动控制点，右键删除；端点固定。','Click to add or drag points; right-click to remove. Endpoints are fixed.'))
        self.curve.changed.connect(lambda points:self.change('curve',points))
        self.mode.currentIndexChanged.connect(self.mode_changed)
        reset=QPushButton(tr('重置过渡','Reset transition'));box.addWidget(reset);reset.clicked.connect(self.reset)
        self.mode_changed()
    def change(self,key,value):
        setattr(self.panel.tool_settings['gradient'],key,value);self.panel.invalidate()
        if hasattr(self,'strip'):self.strip.update()
    def mode_changed(self):
        key=self.mode.currentData();self.change('transition',key)
        self.form.setRowVisible(self.fields['steps'],key=='steps');self.curve.setVisible(key=='curve')
        popup=getattr(self.panel.window,'recolor_window',None)
        if popup and popup.isVisible() and self.panel.gradient_page=='transition':QTimer.singleShot(0,popup.fit_page)
    def reset(self):
        for key,value in [('midpoint',50),('smooth',100),('steps',8)]:self.fields[key].setValue(value)
        self.curve.points=[(0.,0.),(1.,1.)];self.curve.publish()


class TransitionStrip(QWidget):
    def __init__(self,settings):
        super().__init__();self.settings=settings;self.setFixedHeight(24)
    def paintEvent(self,event):
        p=QPainter(self);s=self.settings;a=QColor(s.first);b=QColor(s.last)
        for x in range(self.width()):
            t=transition_value(x/max(1,self.width()-1),s.midpoint,s.smooth,s.transition,s.steps,s.curve)
            c=QColor(*(round(u+(v-u)*t) for u,v in zip(a.getRgb()[:3],b.getRgb()[:3])))
            p.setPen(c);p.drawLine(x,0,x,self.height())
