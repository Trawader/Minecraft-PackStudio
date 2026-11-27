from collections import deque
from PySide6.QtCore import Qt, Signal, QPointF, QRectF, QSize,QRect,QPoint
from PySide6.QtGui import QColor, QPainter, QPen, QImage,QBrush,QPixmap,QRegion,QPainterPath
from PySide6.QtWidgets import QWidget, QDialog,QApplication
from .pointer_input import install as install_pointer_input,modifiers,selection_operation,zoom_steps

class Canvas(QWidget):
    changed = Signal()
    picked = Signal(QColor)
    selectionChanged = Signal(object)
    hovered = Signal(object)
    strokeUpdated = Signal()
    zoomChanged = Signal(float)
    viewChanged = Signal()
    adjustmentRequested = Signal()
    gradientRequested = Signal(object,object)
    def __init__(self):
        super().__init__()
        install_pointer_input(self)
        self.image = QImage()
        self.reset_image=QImage()
        self.regions = None
        self.document_key = None
        self.zoom = 8.0
        self.offset = QPointF(16,16)
        self.tool = 'mouse'
        self.gradient_drag=None
        self.rectangle_mode='normal'
        self.read_only = False
        self.show_rulers = False
        self.hover_pixel=None
        self.color = QColor('#e894c8')
        self.brush_size=1;self.eraser_size=1
        self.brush_opacity=255
        self.history, self.future = [], []
        self.selection = None
        self.selection_region=QRegion();self.move_origin=None;self.move_delta=QPoint();self.moving=False
        self.selection_weights={};self.wand_tolerance=32;self.wand_contiguous=True;self.wand_antialias=False
        self.candidate_region=QRegion()
        self.color_preview=None
        self.amounts={tool:20 for tool in ('burn','dodge','lighten','darken')}
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.drawing = False
        self.task_running=False
        self.stroke_dirty = False
        checker=QPixmap(16,16);checker.fill(QColor('#bbbbbb'));p=QPainter(checker)
        p.fillRect(0,0,8,8,QColor('#888888'));p.fillRect(8,8,8,8,QColor('#888888'));p.end()
        self.checker=QBrush(checker)
        self.setMinimumSize(360,320)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent,True)
        self.setMouseTracking(True)
    def set_image(self,image):
        self.gradient_drag=None
        if hasattr(self,'timeline'):self.timeline.flush()
        self.color_preview=None
        self.candidate_region=QRegion();self.viewChanged.emit()
        self.regions=None;self.document_key=None
        self.drawing=False;self.panning=False
        self.hover_pixel=None;self.hovered.emit(None)
        self.image = QImage(image)
        self.reset_image=QImage(image)
        self.history.clear(); self.future.clear()
        self.clear_selection(record=False)
        self.zoom = max(0.1,min(12,(self.width()-32)/max(1,image.width()),(self.height()-32)/max(1,image.height())))
        self.offset = QPointF(16,16)
        self.zoomChanged.emit(self.zoom)
        self.update()
    def set_atlas(self,image,regions,key):
        self.gradient_drag=None
        if hasattr(self,'timeline'):self.timeline.flush()
        self.color_preview=None
        self.candidate_region=QRegion();self.viewChanged.emit()
        view_changed=tuple(self.regions or ())!=tuple(regions)
        same=self.document_key==key and self.image.cacheKey()==image.cacheKey()
        if not same:
            if self.image.cacheKey()!=image.cacheKey():self.reset_image=QImage(image)
            self.image=QImage(image);self.history.clear();self.future.clear()
        self.document_key=key;self.regions=list(regions)
        if view_changed:
            self.history=[s for s in self.history if s['pixel_edit']]
            self.future=[s for s in self.future if s['pixel_edit']]
        self.clear_selection(record=False);self.drawing=False;self.panning=False;self.hover_pixel=None
        self.hovered.emit(None)
        size=self.view_size()
        self.zoom=max(.1,min(12,(self.width()-32)/max(1,size.width()),(self.height()-32)/max(1,size.height())))
        self.offset=QPointF(16,16);self.zoomChanged.emit(self.zoom);self.update()
    def view_size(self):
        if self.regions:return QSize(max(r[2] for r in self.regions),sum(r[3] for r in self.regions))
        return self.image.size()
    def reset_current(self):
        if self.read_only or self.drawing or self.task_running or self.image.isNull() or self.reset_image.size()!=self.image.size():return
        result=QImage(self.image) if self.regions else QImage(self.reset_image)
        if self.regions:
            painter=QPainter(result);painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            for region in self.regions:
                rect=QRect(*region);painter.drawImage(rect,self.reset_image,rect)
            painter.end()
        if result==self.image:return
        self.checkpoint(label='重置当前素材');self.image=result;self.color_preview=None
        self.clear_selection(record=False);self.changed.emit();self.update()
    def image_point(self,point):
        if not self.regions:return point if 0<=point[0]<self.image.width() and 0<=point[1]<self.image.height() else None
        top=0
        for x,y,width,height in self.regions:
            if 0<=point[0]<width and top<=point[1]<top+height:return x+point[0],y+point[1]-top
            top+=height
        return None
    def set_pixel(self,point,color):
        target=self.image_point(point)
        if target is not None:self.image.setPixelColor(*target,color)
    def pixel(self,point):
        target=self.image_point(point)
        return self.image.pixelColor(*target) if target is not None else QColor(0,0,0,0)
    def view_image(self):
        if not self.regions:return QImage(self.image)
        result=QImage(self.view_size(),QImage.Format.Format_ARGB32);result.fill(Qt.GlobalColor.transparent)
        painter=QPainter(result);top=0
        for x,y,width,height in self.regions:
            painter.drawImage(QRectF(0,top,width,height),self.image,QRectF(x,y,width,height));top+=height
        painter.end();return result
    def replace_view(self,image):
        if not self.regions:self.image=QImage(image);return
        painter=QPainter(self.image);painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source);top=0
        for x,y,width,height in self.regions:
            painter.drawImage(QRectF(x,y,width,height),image,QRectF(0,top,width,height));top+=height
        painter.end()
    def update_pixels(self,rect):
        x,y,width,height=rect
        self.update(QRectF(self.offset.x()+x*self.zoom-4,self.offset.y()+y*self.zoom-4,
                           width*self.zoom+8,height*self.zoom+8).toAlignedRect())
    def set_hover(self,point):
        if point==self.hover_pixel:return
        old=self.hover_pixel;self.hover_pixel=point
        for pixel in (old,point):
            if pixel is not None:self.update_pixels((*pixel,1,1))
        self.hovered.emit(point if self.tool in ('pencil','eraser') else None)
    def snapshot(self,pixel_edit=True):
        return {'image':QImage(self.image),'selection':QRegion(self.selection_region),
                'weights':dict(self.selection_weights),'view':tuple(self.regions or ()), 'pixel_edit':pixel_edit}
    def checkpoint(self,state=None,label=None):
        state=state if state is not None else self.snapshot()
        if label:state['_label']=label
        if hasattr(self,'timeline'):self.timeline.checkpoint(self,state)
        self.history.append(state)
        budget=128*1024*1024
        retained=[];used=0;images=set()
        for frame in reversed(self.history[-30:]):
            key=frame['image'].cacheKey()
            size=(0 if key in images else frame['image'].sizeInBytes())+len(frame['weights'])*128+frame['selection'].rectCount()*32
            if retained and used+size>budget:break
            retained.append(frame);used+=size;images.add(key)
        self.history=list(reversed(retained))
        self.future.clear()
    def finish_selection(self):
        state=getattr(self,'_selection_snapshot',None);self._selection_snapshot=None
        if state is not None and (state['selection']!=self.selection_region or state['weights']!=self.selection_weights):self.checkpoint(state)
    def restore_snapshot(self,state):
        pixels_changed=self.image!=state['image'];self.image=QImage(state['image'])
        same_view=state['view']==tuple(self.regions or ())
        self.selection_region=QRegion(state['selection']) if same_view else QRegion()
        self.selection_weights=dict(state['weights']) if same_view else {}
        self.sync_selection()
        if pixels_changed:self.changed.emit()
    def undo(self):
        if hasattr(self,'timeline') and not self.timeline.busy:
            return self.timeline.window.run(lambda:self.timeline.step())
        self.finish_selection();self.drawing=False
        self.cancel_move()
        if self.history:
            if self.read_only and self.history[-1]['pixel_edit']:return
            state=self.history.pop();self.future.append(self.snapshot(state['pixel_edit']));self.restore_snapshot(state)
    def redo(self):
        if hasattr(self,'timeline') and not self.timeline.busy:
            return self.timeline.window.run(lambda:self.timeline.step(redo=True))
        self.finish_selection();self.drawing=False
        self.cancel_move()
        if self.future:
            if self.read_only and self.future[-1]['pixel_edit']:return
            state=self.future.pop();self.history.append(self.snapshot(state['pixel_edit']));self.restore_snapshot(state)
    def pos(self,event):
        p = (event.position()-self.offset)/self.zoom
        return int(p.x()//1),int(p.y()//1)
    def valid(self,p):
        return self.image_point(p) is not None
    def editable(self,p):
        return self.valid(p) and (self.selection_region.isEmpty() or self.selection_region.contains(QPoint(*p)))
    def clear_selection(self,record=True):
        state=(getattr(self,'_selection_snapshot',None) or self.snapshot(False)) if record else None
        self._selection_snapshot=None
        if self.tool=='select':self.drawing=False
        self.selection_region=QRegion();self.selection=None;self.move_origin=None;self.moving=False
        self.selection_weights={}
        self.move_delta=QPoint();self.selectionChanged.emit(None);self.update()
        if state is not None and not state['selection'].isEmpty():self.checkpoint(state)
    def view_region(self):
        if not self.regions:return QRegion(QRect(QPoint(),self.view_size()))
        region=QRegion();top=0
        for x,y,width,height in self.regions:region=region.united(QRegion(0,top,width,height));top+=height
        return region
    def selection_rectangles(self):
        # Export disjoint/subtracted areas without filling the holes of their bounding box.
        if not self.selection:return []
        x,y,width,height=self.selection;active={};finished=[]
        for row in range(y,y+height):
            spans=[];column=x
            while column<x+width:
                if not self.selection_region.contains(QPoint(column,row)):column+=1;continue
                start=column
                while column<x+width and self.selection_region.contains(QPoint(column,row)):column+=1
                spans.append((start,column-start))
            current={}
            for start,length in spans:
                key=(start,length);previous=active.pop(key,None)
                current[key]=(start,previous[1],length,previous[3]+1) if previous else (start,row,length,1)
            finished.extend(active.values());active=current
        return finished+list(active.values())
    def sync_selection(self):
        self._selection_outline=None
        rect=self.selection_region.boundingRect()
        self.selection=(rect.x(),rect.y(),rect.width(),rect.height()) if not rect.isEmpty() else None
        self.selectionChanged.emit(self.selection);self.update()
    def selection_outline(self):
        if getattr(self,'_selection_outline',None) is None:
            path=QPainterPath();path.setFillRule(Qt.FillRule.WindingFill);path.addRegion(self.selection_region)
            self._selection_outline=path.simplified()
        return QPainterPath(self._selection_outline)
    def cancel_move(self):
        self.move_origin=None;self.moving=False;self.move_delta=QPoint();self.update()
    def moved_view(self):
        if self.move_delta.isNull():return QImage(self.move_origin)
        if self.selection_weights:
            mask=QImage(self.view_size(),QImage.Format.Format_ARGB32);mask.fill(Qt.GlobalColor.transparent)
            p=QPainter(mask);p.setClipRegion(self.selection_region);p.fillRect(mask.rect(),Qt.GlobalColor.white);p.end()
            for point,weight in self.selection_weights.items():mask.setPixelColor(*point,QColor(255,255,255,weight))
            cut=QImage(self.move_origin);p=QPainter(cut);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn);p.drawImage(0,0,mask);p.end()
            image=QImage(self.move_origin);p=QPainter(image);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut);p.drawImage(0,0,mask)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver);p.drawImage(self.move_delta,cut);p.end();return image
        image=QImage(self.move_origin);p=QPainter(image)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.setClipRegion(self.selection_region);p.fillRect(image.rect(),Qt.GlobalColor.transparent)
        p.setClipRegion(self.selection_region.translated(self.move_delta));p.drawImage(self.move_delta,self.move_origin)
        p.end();return image
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:
            if self.gradient_drag is not None:
                self.gradient_drag=None;self.update();event.accept();return
            self.clear_selection();event.accept();return
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter) and self.move_origin is not None:
            if not self.read_only and not self.move_delta.isNull():
                self.checkpoint();self.replace_view(self.moved_view());self.clear_selection(record=False);self.changed.emit()
            else:self.clear_selection()
            event.accept();return
        super().keyPressEvent(event)
    def mouseDoubleClickEvent(self,event):
        # A double click is never a deselect gesture.
        self.mousePressEvent(event)
    def paintEvent(self,event):
        p = QPainter(self)
        p.fillRect(self.rect(),QColor('#1f1f1f'))
        if self.image.isNull():
            return
        p.translate(self.offset); p.scale(self.zoom,self.zoom)
        size=self.view_size()
        p.fillRect(0,0,size.width(),size.height(),self.checker)
        if self.color_preview is not None:p.drawImage(0,0,self.color_preview)
        elif self.move_origin is not None:p.drawImage(0,0,self.moved_view())
        elif self.regions:
            top=0
            for x,y,width,height in self.regions:
                p.drawImage(QRectF(0,top,width,height),self.image,QRectF(x,y,width,height));top+=height
        else:p.drawImage(0,0,self.image)
        if not self.candidate_region.isEmpty():
            p.save();p.setClipRegion(self.candidate_region)
            p.fillRect(0,0,size.width(),size.height(),QColor(0,210,235,100));p.restore()
        if self.selection:
            p.setPen(QPen(QColor('#cccccc'),1/self.zoom,Qt.PenStyle.DashLine))
            outline=self.selection_outline()
            if self.move_origin is not None:outline.translate(self.move_delta)
            p.drawPath(outline)
        if self.gradient_drag is not None:
            a,b=self.gradient_drag
            p.setPen(QPen(QColor('#eeeeee'),1/self.zoom))
            p.drawLine(QPointF(a[0]+.5,a[1]+.5),QPointF(b[0]+.5,b[1]+.5))
            for x,y in (a,b):p.drawRect(QRectF(x+.5-3/self.zoom,y+.5-3/self.zoom,6/self.zoom,6/self.zoom))
        if self.hover_pixel is not None and self.tool in ('pencil','eraser'):
            x,y=self.hover_pixel;size=self.brush_size if self.tool=='pencil' else self.eraser_size
            footprint=QRectF(x-size//2,y-size//2,size,size)
            p.fillRect(footprint,QColor(255,70,100,65) if self.tool=='eraser' else QColor(255,255,255,60))
            p.setPen(QPen(QColor('#000000'),3/self.zoom));p.drawRect(footprint)
            p.setPen(QPen(QColor('#ff5577') if self.tool=='eraser' else QColor('#ffffff'),1/self.zoom));p.drawRect(footprint)
        if self.show_rulers:
            p.resetTransform();p.fillRect(0,0,self.width(),22,QColor('#292929'));p.fillRect(0,0,30,self.height(),QColor('#292929'))
            p.setPen(QColor('#cccccc'))
            step=1
            while step*self.zoom<45:step*=2
            for horizontal,limit,offset,extent in ((True,size.width(),self.offset.x(),self.width()),(False,size.height(),self.offset.y(),self.height())):
                start=max(0,int(-offset/self.zoom)//step*step)
                end=min(limit,int((extent-offset)/self.zoom)+step)
                for value in range(start,end+1,step):
                    position=round(offset+value*self.zoom)
                    if horizontal:
                        p.drawLine(position,17,position,22);p.drawText(position+2,13,str(value))
                    else:
                        p.drawLine(25,position,30,position);p.drawText(2,position-2,str(value))
            p.fillRect(0,0,30,22,QColor('#292929'));p.drawText(2,15,'px')
    def set_tool(self,tool):
        self.gradient_drag=None
        self.finish_selection()
        if self.move_origin is not None:self.cancel_move()
        self.tool=tool;self.drawing=False;self.panning=False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.hovered.emit(self.hover_pixel if tool in ('pencil','eraser') else None);self.update()
    def leaveEvent(self,event):
        self.set_hover(None);super().leaveEvent(event)
    def zoom_at(self,screen_point,steps):
        """Change the view transform only; keep the cursor's image point fixed."""
        if self.image.isNull() or not steps:return
        new_zoom=max(.1,min(80,self.zoom*1.25**max(-10.,min(10.,steps))))
        self.set_zoom_at(screen_point,new_zoom)
    def set_zoom_at(self,screen_point,new_zoom):
        """Set an exact scale, retaining the image point at the chosen anchor."""
        if self.image.isNull():return
        new_zoom=max(.1,min(80,new_zoom))
        anchor=(screen_point-self.offset)/self.zoom
        if new_zoom==self.zoom:return
        self.zoom=new_zoom
        self.offset=screen_point-anchor*new_zoom
        self.set_hover(None)
        self.zoomChanged.emit(new_zoom);self.update()
    def wheelEvent(self,event):
        if self.tool!='mouse' or self.image.isNull() or not modifiers(event) & Qt.KeyboardModifier.AltModifier:
            event.ignore();return
        steps=zoom_steps(event)
        if not steps:
            event.ignore();return
        self.zoom_at(event.position(),steps)
        # Accept even at the zoom limit so the parent scroll area does not move.
        event.accept()
    def mousePressEvent(self,event):
        if self.task_running:return
        if self.show_rulers and (event.position().x()<30 or event.position().y()<22):return
        self.last_screen = event.position()
        self.setFocus();point=self.pos(event)
        if self.tool=='mouse' and event.button()==Qt.MouseButton.LeftButton and not self.read_only:
            active=self.selection_region.translated(self.move_delta) if self.move_origin is not None else self.selection_region
            if active.contains(QPoint(*point)):
                if self.move_origin is None:self.move_origin=self.view_image();self.move_delta=QPoint()
                self.move_start=QPoint(*point)-self.move_delta;self.moving=True;return
        if event.button()==Qt.MouseButton.MiddleButton or (self.tool=='mouse' and event.button()==Qt.MouseButton.LeftButton):
            self.panning=True; return
        self.panning=False
        point=self.pos(event)
        if self.tool=='gradient' and event.button()==Qt.MouseButton.LeftButton:
            if not self.read_only and not self.image.isNull():
                self.gradient_drag=(point,point);self.update()
            event.accept();return
        if self.tool=='wand' and event.button()==Qt.MouseButton.LeftButton and not self.valid(point):
            self.clear_selection();event.accept();return
        if self.tool in ('select','wand') and event.button()==Qt.MouseButton.LeftButton and (self.tool=='select' or self.valid(point)):
            self.cancel_move();self.start=point;self.selection_before=QRegion(self.selection_region)
            self._selection_snapshot=self.snapshot(False)
            self.weights_before=dict(self.selection_weights)
            self.selection_operation=selection_operation(event)
            self.selection_started_outside=not self.valid(point)
            self.selection_press_position=event.position()
            self.selection_dragged=False
            if self.tool=='select' and self.rectangle_mode=='opaque':
                self.rectangle_opaque_region=self.view_region()
            if self.tool=='wand':
                from .wand import select
                image=self.view_image();allowed=self.view_region();options=(self.wand_tolerance,self.wand_contiguous,self.wand_antialias)
                result=self.pixel_task('魔棒',image,lambda cancel,progress:select(image,point,allowed,*options,cancel=cancel,progress=progress))
                if result is None:self._selection_snapshot=None;return
                region,weights=result
                self.combine_selection(region,weights);self.finish_selection();return
            self.drawing=True
            if not self.selection_started_outside:self.select_rect(point)
            return
        if event.button()!=Qt.MouseButton.LeftButton or not self.valid(point): return
        # Adjustment tools must not inherit the preceding wand/rectangle or
        # enter the pixel-stroke history path. Preview is explicitly applied.
        if self.tool=='recolor':
            if not self.read_only:self.adjustmentRequested.emit()
            event.accept();return
        self.start=point; self.last=point
        if self.tool=='picker':
            self.picked.emit(self.pixel(point)); return
        if self.tool=='fill':
            if self.read_only:return
            from .pixel_tasks import fill_selection
            image=self.view_image();allowed=self.view_region()
            if not self.selection_region.isEmpty():allowed=allowed.intersected(self.selection_region)
            target=QColor(self.color);weights=dict(self.selection_weights)
            result=self.pixel_task('填充',image,lambda cancel,progress:fill_selection(image,allowed,target,weights,cancel,progress))
            if result is not None and result!=image:
                self.checkpoint();self.replace_view(result);self.changed.emit();self.update()
            return
        if self.read_only or not self.editable(point):return
        self.tone_visited=set()
        self.selection_visited=set()
        if self.tool in ('bucket','magic_eraser'):
            from .pixel_tasks import fill
            image=self.view_image();allowed=self.view_region()
            if not self.selection_region.isEmpty():allowed=allowed.intersected(self.selection_region)
            weights=dict(self.selection_weights)
            target=QColor(0,0,0,0) if self.tool=='magic_eraser' else QColor(self.color)
            if self.tool=='bucket':target.setAlpha(255)
            result=self.pixel_task('魔术橡皮擦' if self.tool=='magic_eraser' else '油漆桶',image,lambda cancel,progress:fill(image,point,allowed,target,weights,cancel,progress))
            if result is not None and result!=image:
                self.checkpoint();self.replace_view(result);self.changed.emit();self.update()
            return
        self._stroke_future=list(self.future);self.checkpoint();self.stroke_dirty=False
        self.drawing=True;self.stroke(point,point)

    def pixel_task(self,title,image,work):
        from .pixel_tasks import execute
        key=self.image.cacheKey();view=tuple(self.regions or ());self.task_running=True
        try:
            result=execute(self,title,image,work)
            return result if key==self.image.cacheKey() and view==tuple(self.regions or ()) else None
        except InterruptedError:return None
        finally:self.task_running=False

    def stroke(self,a,b):
        if self.read_only:return
        x,y=a; dx=b[0]-x; dy=b[1]-y; steps=max(abs(dx),abs(dy),1)
        changed=False;color=QColor(0,0,0,0) if self.tool=='eraser' else QColor(self.color)
        if self.tool=='pencil':color.setAlpha(round(color.alpha()*self.brush_opacity/255))
        from .brush import stroke_points
        size=self.brush_size if self.tool=='pencil' else self.eraser_size if self.tool=='eraser' else 1
        for pt in stroke_points(a,b,size):
            if not self.editable(pt):continue
            if pt in self.selection_weights:
                if pt in self.selection_visited:continue
                self.selection_visited.add(pt)
            if self.tool in self.amounts:
                if pt in self.tone_visited:continue
                self.tone_visited.add(pt);old=self.pixel(pt)
                if not old.alpha():continue
                amount=self.amounts[self.tool]/100
                if self.tool in ('burn','dodge'):
                    gamma=1+amount*2 if self.tool=='burn' else 1/(1+amount*2)
                    color=QColor(*(round(255*(v/255)**gamma) for v in (old.red(),old.green(),old.blue())),old.alpha())
                else:
                    hue,sat,value,alpha=old.getHsvF();value=max(0,min(1,value+(amount if self.tool=='lighten' else -amount)))
                    color=QColor.fromHsvF(max(0,hue),sat,value,alpha)
            if self.pixel(pt)!=color:self.paint_pixel(pt,color);changed=True
        if not changed:return
        self.stroke_dirty=True
        self.update_pixels((min(a[0],b[0])-size//2,min(a[1],b[1])-size//2,abs(dx)+size,abs(dy)+size))
        self.strokeUpdated.emit()
    def mouseMoveEvent(self,event):
        if self.task_running:return
        if self.gradient_drag is not None:
            self.gradient_drag=(self.gradient_drag[0],self.pos(event));self.update();event.accept();return
        point=self.pos(event);self.set_hover(point if self.valid(point) else None)
        if self.moving:
            delta=QPoint(*point)-self.move_start;bounds=self.selection_region.boundingRect();size=self.view_size()
            delta.setX(max(-bounds.left(),min(size.width()-1-bounds.right(),delta.x())))
            delta.setY(max(-bounds.top(),min(size.height()-1-bounds.bottom(),delta.y())))
            if not self.selection_region.translated(delta).subtracted(self.view_region()).isEmpty():return
            self.move_delta=delta;self.update();return
        if getattr(self,'panning',False):
            self.offset+=event.position()-self.last_screen; self.last_screen=event.position(); self.update(); return
        if not self.drawing:return
        if self.tool=='select':
            self.selection_dragged=self.selection_dragged or (event.position()-self.selection_press_position).manhattanLength()>=QApplication.startDragDistance()
            if self.selection_started_outside and not self.selection_dragged:return
            self.select_rect(point)
        else:
            self.stroke(self.last,point); self.last=point
    def mouseReleaseEvent(self,event):
        if self.task_running:return
        if self.gradient_drag is not None:
            if event.button()!=Qt.MouseButton.LeftButton:return
            start,_=self.gradient_drag;end=self.pos(event);self.gradient_drag=None;self.update()
            if start!=end and not self.read_only:self.gradientRequested.emit(start,end)
            event.accept();return
        if self.moving:self.moving=False;event.accept();return
        self.panning=False
        if self.drawing:
            self.drawing=False
            if self.tool=='select':
                if self.selection_started_outside and not self.selection_dragged and (event.position()-self.selection_press_position).manhattanLength()<QApplication.startDragDistance():
                    self.selection_region=QRegion();self.selection_weights={};self.sync_selection()
                else:
                    if self.rectangle_mode=='opaque':
                        image=self.view_image();bounds=QRegion(QRect(QPoint(*self.start),QPoint(*self.pos(event))).normalized()).intersected(self.view_region())
                        from .pixel_tasks import opaque
                        result=self.pixel_task('魔法矩形',image,lambda cancel,progress:opaque(image,bounds,cancel,progress))
                        if result is None:
                            self.selection_region=QRegion(self.selection_before);self.selection_weights=dict(self.weights_before);self._selection_snapshot=None;self.sync_selection();return
                        self.rectangle_opaque_region=result
                    self.select_rect(self.pos(event))
                self.finish_selection()
            elif self.stroke_dirty:self.changed.emit()
            elif self.history:self.history.pop();self.future=getattr(self,'_stroke_future',[])
    def select_rect(self,point):
        rect=QRect(QPoint(*self.start),QPoint(*point)).normalized().intersected(QRect(QPoint(),self.view_size()))
        region=QRegion(rect)
        region=region.intersected(self.view_region())
        if self.rectangle_mode=='opaque':region=region.intersected(self.rectangle_opaque_region)
        self.combine_selection(region,{})
    def opaque_region(self):
        from .pixel_tasks import opaque
        image=self.view_image();allowed=self.view_region()
        return self.pixel_task('魔法矩形',image,lambda cancel,progress:opaque(image,allowed,cancel,progress))
    def combine_selection(self,region,weights):
        operation=self.selection_operation;before=self.selection_before
        self.selection_region=before.subtracted(region) if operation=='subtract' else before.united(region) if operation=='add' else region
        result={}
        for point in self.weights_before.keys() | weights.keys():
            p=QPoint(*point)
            a=self.weights_before.get(point,255) if before.contains(p) else 0
            b=weights.get(point,255) if region.contains(p) else 0
            weight=max(a,b) if operation=='add' else round(a*(1-b/255)) if operation=='subtract' else b
            if weight:
                self.selection_region=self.selection_region.united(QRegion(*point,1,1))
                if weight<255:result[point]=weight
        self.selection_weights=result
        self.sync_selection()
    def paint_pixel(self,point,color):
        weight=self.selection_weights.get(point,255)/255
        if weight<1:
            old=self.pixel(point);alpha=old.alphaF()*(1-weight)+color.alphaF()*weight
            rgb=[round((a*old.alphaF()*(1-weight)+b*color.alphaF()*weight)/alpha) if alpha else 0 for a,b in zip(old.getRgb()[:3],color.getRgb()[:3])]
            color=QColor(*rgb,round(alpha*255))
        self.set_pixel(point,color)

class ScreenPicker(QDialog):
    picked = Signal(QColor)
    def __init__(self,screen,pixmap):
        super().__init__()
        self.screen_image=pixmap.toImage()
        self.ratio=pixmap.devicePixelRatio()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.Tool)
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
    def paintEvent(self,event):
        p=QPainter(self); p.drawImage(self.rect(),self.screen_image)
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            x=int(event.position().x()*self.ratio); y=int(event.position().y()*self.ratio)
            self.picked.emit(self.screen_image.pixelColor(x,y))
        else:self.reject()
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:self.reject()
