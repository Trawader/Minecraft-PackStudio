"""Explicit part masks and luminance-distribution transfer, without image synthesis."""
import json
from pathlib import Path
from functools import lru_cache
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QPainter,QColor
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QPushButton,QDialogButtonBox


def rgba(image):
    # Keep the converted image alive until its borrowed pixel buffer is copied.
    converted=image.convertToFormat(QImage.Format.Format_RGBA8888)
    return bytes(converted.constBits())
def luminance(r,g,b):return (54*r+183*g+19*b)//256


@lru_cache(maxsize=1)
def evidence():
    path=Path(__file__).parent/'data/material-evidence.json'
    return json.loads(path.read_text('utf-8')) if path.exists() else {'tool_evidence':{}}


def part_mask(image,kind,peers=(),protected_out=None):
    data=rgba(image);w,h=image.width(),image.height();result=bytearray(w*h)
    if not kind.startswith('equipment:'):
        for p in range(w*h):
            r,g,b,a=data[p*4:p*4+4]
            protect=kind.startswith('stained_glass') and (max(r,g,b)<12 or min(r,g,b)>225 and max(r,g,b)-min(r,g,b)<16)
            result[p]=int(a>0 and not protect)
        return result
    kind=kind.split(':')[1];stats=evidence()['tool_evidence'].get(kind,{})
    from itertools import islice
    same=[rgba(peer) for peer in islice((peer for peer in peers if peer.size()==image.size()),8)]
    protected=bytearray(w*h)
    head=stats.get('head',[0]*256);fixed=stats.get('fixed',[0]*256)
    for p in range(w*h):
        r,g,b,a=data[p*4:p*4+4]
        if not a:continue
        index=min(15,(p%w)*16//w)+min(15,(p//w)*16//h)*16
        votes=head[index]+fixed[index];prob=head[index]/votes if votes else 0
        stable=sum(peer[p*4+3]>0 and max(abs(data[p*4+c]-peer[p*4+c]) for c in range(3))<=10 for peer in same)
        # Shared pixels across material variants are protected, not recoloured.
        if stable>=2:protected[p]=1;continue
        brown=r>g*1.12 and g>b*1.12
        if brown and fixed[index]>=head[index]*.4:protected[p]=1;continue
        changed=sum(peer[p*4+3]>0 and max(abs(data[p*4+c]-peer[p*4+c]) for c in range(3))>24 for peer in same)
        result[p]=int(prob>=.7 or changed>=2 and prob>=.4)
    if protected_out is not None:protected_out[:]=protected
    return result


def histogram(image,mask):
    source=rgba(image);hist=[0]*256
    for p,selected in enumerate(mask):
        if selected:
            r,g,b,a=source[p*4:p*4+4]
            if a:hist[luminance(r,g,b)]+=a
    return hist


def transfer(image,mask,target,target_mask,strength=100,source_histogram=None):
    source=rgba(image);reference=rgba(target);hist=source_histogram or histogram(image,mask);colours=[]
    step=max(1,len(target_mask)//16384)
    for p in range(0,len(target_mask),step):
        if target_mask[p]:
            r,g,b,a=reference[p*4:p*4+4]
            if a:colours.append((luminance(r,g,b),r,g,b))
    if not sum(hist) or not colours:raise ValueError('没有确认的换色部件像素；请调整部件区域或选择其他参考')
    colours.sort();total=sum(hist);cumulative=0;table=[]
    for count in hist:
        q=(cumulative+count/2)/total;cumulative+=count
        index=q*(len(colours)-1);lo=int(index);hi=min(len(colours)-1,lo+1);weight=index-lo
        table.append(tuple(round(colours[lo][c]*(1-weight)+colours[hi][c]*weight) for c in (1,2,3)))
    output=bytearray(source)
    for p,selected in enumerate(mask):
        if not selected or not source[p*4+3]:continue
        r,g,b=source[p*4:p*4+3];colour=table[luminance(r,g,b)]
        for c in range(3):output[p*4+c]=round(source[p*4+c]+(colour[c]-source[p*4+c])*strength/100)
    return QImage(output,image.width(),image.height(),image.width()*4,QImage.Format.Format_RGBA8888).copy()


def mask_region(mask,width):
    from PySide6.QtGui import QRegion
    result=QRegion()
    for y in range(len(mask)//width):
        x=0
        while x<width:
            if not mask[y*width+x]:x+=1;continue
            start=x
            while x<width and mask[y*width+x]:x+=1
            result=result.united(QRegion(start,y,x-start,1))
    return result


def region_mask(image,region):
    from PySide6.QtCore import QPoint
    data=rgba(image);w,h=image.width(),image.height();result=bytearray(w*h)
    bounds=region.boundingRect().intersected(image.rect())
    for y in range(bounds.top(),bounds.bottom()+1):
        for x in range(bounds.left(),bounds.right()+1):
            p=y*w+x
            result[p]=int(data[p*4+3]>0 and region.contains(QPoint(x,y)))
    return result


from .canvas import Canvas
class MaskCanvas(Canvas):
    """Use the normal selection engine without editing the source pixels."""
    def __init__(self,image,mask):
        super().__init__();self.setMinimumSize(360,300);self.mask_brush_size=1;self.mask_eraser_size=1;self.brushing=False;self.last_mask_point=None
        self.set_image(image);self.read_only=True;self.tool='select';self.rectangle_mode='opaque'
        self.selection_region=mask_region(mask,image.width());self.sync_selection()
    @property
    def mask(self):return region_mask(self.image,self.selection_region)
    def paintEvent(self,event):
        super().paintEvent(event)
        p=QPainter(self);p.translate(self.offset);p.scale(self.zoom,self.zoom)
        p.setClipRegion(self.selection_region);p.fillRect(self.image.rect(),QColor(255,40,100,100))
    def resizeEvent(self,event):
        super().resizeEvent(event)
        from PySide6.QtCore import QPointF
        self.zoom=max(.1,min((self.width()-24)/max(1,self.image.width()),(self.height()-24)/max(1,self.image.height())))
        self.offset=QPointF((self.width()-self.image.width()*self.zoom)/2,(self.height()-self.image.height()*self.zoom)/2)
    def mark(self,event):
        from PySide6.QtGui import QRegion
        point=self.pos(event)
        from .brush import stroke_points
        size=self.mask_brush_size if self.tool=='mask_add' else self.mask_eraser_size
        region=QRegion()
        for x,y in stroke_points(self.last_mask_point or point,point,size):region=region.united(QRegion(x,y,1,1))
        self.last_mask_point=point;region=region.intersected(QRegion(self.image.rect()))
        self.selection_region=self.selection_region.united(region) if self.tool=='mask_add' else self.selection_region.subtracted(region)
        self.selection_weights={};self.sync_selection()
    def mousePressEvent(self,event):
        if self.tool in ('mask_add','mask_remove') and event.button()==Qt.MouseButton.LeftButton:
            self.setFocus();self.last_mask_point=None;self.brushing=True;self._selection_snapshot=self.snapshot(False);self.mark(event);return
        super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.brushing and event.buttons()&Qt.MouseButton.LeftButton:self.mark(event);return
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        if self.brushing and event.button()==Qt.MouseButton.LeftButton:self.brushing=False;self.finish_selection();return
        super().mouseReleaseEvent(event)


class MaskDialog(QDialog):
    def __init__(self,parent,image,mask):
        super().__init__(parent);self.owner=parent.window;self.setWindowTitle('修正换色区域')
        from .appearance import tool_icon
        from .ui import Window
        from PySide6.QtCore import QSize
        layout=QVBoxLayout(self)
        self.canvas=MaskCanvas(image,mask);self.tool_buttons={}
        layout.addWidget(self.canvas,1);row=QHBoxLayout();layout.addLayout(row)
        for key,icon,label in [('mouse','mouse','移动'),('mask_add','pencil','画笔'),('mask_remove','eraser','橡皮擦'),('select','select','矩形选区'),('wand','wand','魔棒')]:
            button=QPushButton();button.setIcon(tool_icon(icon));button.setIconSize(QSize(20,20));button.setFixedSize(30,28);button.setCheckable(True);button.setToolTip(self.tr(label))
            self.tool_buttons[key]=button;row.addWidget(button)
            button.clicked.connect(lambda checked=False,k=key:self.set_tool(k))
            if key!='mouse':
                from .editor_layout import add_menu_mark
                add_menu_mark(button);button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                button.customContextMenuRequested.connect(lambda pos,k=key:self.tool_settings(k,pos))
        clear=QPushButton(self.tr('取消选择'));clear.clicked.connect(self.canvas.clear_selection);row.addWidget(clear);row.addStretch()
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        for button in self.findChildren(QPushButton):button.setAutoDefault(False)
        from .tool_hints import ToolHint
        self.tool_hints=[ToolHint(self.tool_buttons[k]) for k in ('select','wand')]
        self.update_rectangle_tooltip();self.set_tool('mouse');self.resize(560,540)
    def tool_settings(self,key,pos):
        from .ui import Window
        if key=='select':return Window.rectangle_settings(self,self.tool_buttons[key],pos)
        if key=='wand':return Window.wand_settings(self,self.tool_buttons[key],pos)
        from .editor_controls import size_settings
        size_settings(self,self.tool_buttons[key],pos,'mask_brush_size' if key=='mask_add' else 'mask_eraser_size')
    def tr(self,zh,en=None):return self.owner.tr(zh,en or zh)
    def set_tool(self,key):
        self.canvas.set_tool(key)
        for name,button in self.tool_buttons.items():button.setChecked(name==key)
        self.canvas.setFocus()
    def rectangle_menu(self):
        from .ui import Window
        return Window.rectangle_menu(self)
    def set_rectangle_mode(self,mode):
        self.canvas.rectangle_mode=mode;self.set_tool('select');self.update_rectangle_tooltip()
    def update_rectangle_tooltip(self):
        from .ui import Window
        Window.update_rectangle_tooltip(self)


def edit_mask(parent,image,mask):
    dialog=MaskDialog(parent,image,mask)
    try:return dialog.canvas.mask if dialog.exec()==QDialog.DialogCode.Accepted else None
    finally:dialog.deleteLater()
