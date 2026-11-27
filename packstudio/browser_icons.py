"""Vanilla-textured shulker folders for the friendly resource browser."""
from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QIcon,QPixmap,QPainter,QPolygonF,QTransform,QColor
from .core import decode

RAINBOW=('red','orange','yellow','lime','cyan','blue','purple')
COLOR_ROLE=Qt.ItemDataRole.UserRole+1

def shulker_icon(w,color):
    key='@shulker:'+color
    if key in w._category_icons:return w._category_icons[key]
    path='assets/minecraft/textures/block/'+color+'_shulker_box.png'
    raw=w.vanilla.get('1.21.11',path) or w.vanilla.get('1.16.5',path)
    pix=QPixmap(32,32);pix.fill(Qt.GlobalColor.transparent)
    painter=QPainter(pix)
    if raw:
        im=decode(raw)
        square=QPolygonF([QPointF(0,0),QPointF(im.width(),0),QPointF(im.width(),im.height()),QPointF(0,im.height())])
        faces=[([(16,1),(30,8),(16,15),(2,8)],0), ([(2,8),(16,15),(16,31),(2,24)],65), ([(16,15),(30,8),(30,24),(16,31)],30)]
        for points,shade in faces:
            transform=QTransform();QTransform.quadToQuad(square,QPolygonF([QPointF(*p) for p in points]),transform)
            painter.save();painter.setTransform(transform);painter.drawImage(0,0,im);painter.fillRect(im.rect(),QColor(0,0,0,shade));painter.restore()
        painter.setPen(QColor(25,15,35,160));painter.drawLine(2,15,16,22);painter.drawLine(16,22,30,15)
    painter.end();icon=QIcon(pix);w._category_icons[key]=icon;return icon

def decorate_folders(w):
    todo=[(w.tree.topLevelItem(i),0) for i in range(w.tree.topLevelItemCount())]
    while todo:
        node,depth=todo.pop();data=node.data(0,Qt.ItemDataRole.UserRole) or {}
        if data.get('kind') in ('root','folder'):
            complete=data.get('whole_pack',False) or data.get('kind')=='root'
            color='purple' if complete or node.text(0).startswith('完整材质包 /') else RAINBOW[depth%len(RAINBOW)]
            node.setIcon(0,shulker_icon(w,color));node.setData(0,COLOR_ROLE,color)
            next_depth=0 if complete else depth+1
        else:next_depth=depth
        todo.extend((node.child(i),next_depth) for i in range(node.childCount()))
