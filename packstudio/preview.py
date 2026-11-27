import math
from PySide6.QtCore import Qt,QPointF,QRectF,Signal
from PySide6.QtGui import QPainter,QPolygonF,QTransform,QColor,QImage,QPainterPath,QPen
from PySide6.QtWidgets import QWidget
from .core import decode
from .pointer_input import install as install_pointer_input,modifiers,zoom_steps

class Preview(QWidget):
    """Orthographic, textured model viewer; resource data stays untouched."""
    pixelHovered=Signal(object)
    def __init__(self):
        super().__init__();self.image=None;self.mode='none';self.yaw=.65;self.pitch=.4;self.zoom=1
        install_pointer_input(self)
        self.faces=[];self.textures={};self.center=(0,0,0);self.extent=16;self.message='';self.missing=[]
        self.highlight=None;self.current_path='';self.hit_faces=[];self.pan=QPointF();self.setMouseTracking(True)
        self.setMinimumSize(260,180)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent,True)
    def set_model(self,faces,get_texture,current_path,current_image):
        self.sky_image=None;self.sky_cache=None
        self.flat_image=None
        self.faces=faces;self.image=current_image;self.current_path=current_path;self.textures={};self.missing=[];self.message=''
        points=[p for face in faces for p in face.vertices]
        if not points:
            self.update();return
        lo=[min(p[i] for p in points) for i in range(3)];hi=[max(p[i] for p in points) for i in range(3)]
        self.center=tuple((lo[i]+hi[i])/2 for i in range(3));self.extent=max(max(hi[i]-lo[i] for i in range(3)),1)
        for face in faces:
            path=face.texture
            if path in self.textures:continue
            if path==current_path:im=current_image
            else:
                data=get_texture(path) if path else None
                try:im=decode(data) if data else None
                except ValueError:im=None
            if im is None or im.isNull():
                self.missing.append(path);im=QImage(16,16,QImage.Format.Format_ARGB32);im.fill(QColor('#ff00ff'));p=QPainter(im);p.fillRect(0,0,8,8,Qt.GlobalColor.black);p.fillRect(8,8,8,8,Qt.GlobalColor.black);p.end()
            if '/entity/' not in path and im.height()>im.width() and get_texture(path+'.mcmeta'):
                im=im.copy(0,0,im.width(),im.width())
            self.textures[path]=im
        self.update()
    def clear_model(self,message=''):
        self.sky_image=None;self.sky_cache=None
        self.flat_image=None
        self.faces=[];self.textures={};self.image=None;self.hit_faces=[];self.highlight=None;self.current_path='';self.message=message;self.update()
    def set_highlight(self,pixel,erase=False):
        highlight=(pixel,erase) if pixel is not None else None
        if highlight!=self.highlight:self.highlight=highlight;self.update()
    def leaveEvent(self,event):self.pixelHovered.emit(None);super().leaveEvent(event)
    def mousePressEvent(self,e):self.last=e.position()
    def mouseMoveEvent(self,e):
        if e.buttons() & Qt.MouseButton.LeftButton:
            d=e.position()-self.last;self.yaw+=d.x()*.01;self.pitch=max(-1.4,min(1.4,self.pitch+d.y()*.01));self.last=e.position();self.update()
        elif e.buttons() & Qt.MouseButton.MiddleButton:
            self.pan+=e.position()-self.last;self.last=e.position();self.update()
        else:
            pixel=None
            for quad,inverse,path,image in reversed(self.hit_faces):
                if quad.containsPoint(e.position(),Qt.FillRule.OddEvenFill):
                    uv=inverse.map(e.position());x,y=int(uv.x()),int(uv.y())
                    if 0<=x<image.width() and 0<=y<image.height() and image.pixelColor(x,y).alpha():
                        if path==self.current_path:pixel=(x,y)
                        break
            self.pixelHovered.emit(pixel)
    def wheelEvent(self,e):
        if not modifiers(e) & Qt.KeyboardModifier.AltModifier:
            e.ignore();return
        steps=zoom_steps(e)
        if not steps:e.ignore();return
        self.zoom=max(.2,min(8,self.zoom*1.1**max(-10,min(10,steps))))
        self.update();e.accept()
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#1f1f1f'))
        sky=getattr(self,'sky_image',None)
        if sky is not None:
            from .sky_view import render
            key=(sky.cacheKey(),self.sky_layout,self.yaw,self.pitch,self.zoom,self.width(),self.height())
            if getattr(self,'sky_cache',None) is None or self.sky_cache[0]!=key:
                self.sky_cache=(key,render(sky,self.sky_layout,self.yaw,self.pitch,self.zoom,self.width(),self.height()))
            p.drawImage(self.rect(),self.sky_cache[1]);return
        flat=getattr(self,'flat_image',None)
        if flat is not None and not flat.isNull():
            scaled=flat.scaled(max(1,self.width()-24),max(1,self.height()-24),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation)
            p.drawImage((self.width()-scaled.width())//2,(self.height()-scaled.height())//2,scaled);return
        if not self.faces:
            p.setPen(QColor('#c5cbd5'));p.drawText(self.rect().adjusted(15,15,-15,-15),Qt.AlignmentFlag.AlignCenter|Qt.TextFlag.TextWordWrap,self.message);return
        scale=min(self.width(),self.height())*.68/self.extent*self.zoom
        def project(v):
            x,y,z=(v[i]-self.center[i] for i in range(3));xx=x*math.cos(self.yaw)+z*math.sin(self.yaw);zz=-x*math.sin(self.yaw)+z*math.cos(self.yaw)
            yy=y*math.cos(self.pitch)-zz*math.sin(self.pitch);depth=y*math.sin(self.pitch)+zz*math.cos(self.pitch)
            return QPointF(self.width()/2+xx*scale+self.pan.x(),self.height()/2+yy*scale+self.pan.y()),depth
        projected=[]
        for face in self.faces:
            values=[project(v) for v in face.vertices];projected.append((sum(v[1] for v in values)/4,face,QPolygonF([v[0] for v in values])))
        self.hit_faces=[]
        for _,face,quad in sorted(projected,key=lambda x:x[0],reverse=True):
            texture=self.textures[face.texture];u,v,U,V=face.uv
            uv=[QPointF(u*texture.width(),v*texture.height()),QPointF(U*texture.width(),v*texture.height()),QPointF(U*texture.width(),V*texture.height()),QPointF(u*texture.width(),V*texture.height())]
            shift=(face.rotation//90)%4;uv=uv[shift:]+uv[:shift]
            transform=QTransform()
            if QTransform.quadToQuad(QPolygonF(uv),quad,transform):
                p.save()
                clip=QPainterPath();clip.addPolygon(quad);p.setClipPath(clip);p.setTransform(transform);p.drawImage(0,0,texture)
                inverse,ok=transform.inverted()
                if ok:self.hit_faces.append((quad,inverse,face.texture,texture))
                if self.highlight and face.texture==self.current_path:
                    (x,y),erase=self.highlight
                    if min(u,U)*texture.width()<=x<max(u,U)*texture.width() and min(v,V)*texture.height()<=y<max(v,V)*texture.height():
                        color=QColor('#ff5577') if erase else QColor('#ffff44');fill=QColor(color);fill.setAlpha(100)
                        p.fillRect(QRectF(x,y,1,1),fill);pen=QPen(color,1);pen.setCosmetic(True);p.setPen(pen);p.drawRect(QRectF(x,y,1,1))
                p.restore()
