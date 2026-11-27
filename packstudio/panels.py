import json
from PySide6.QtCore import Qt,Signal,QItemSelectionModel,QMimeData,QPersistentModelIndex,QModelIndex,QPoint,QRect
from PySide6.QtGui import QDrag,QPixmap,QPainter,QPainterPath,QColor,QCursor,QPen
from PySide6.QtWidgets import QListWidget,QTreeWidget,QTreeWidgetItem,QAbstractItemView,QApplication,QToolButton

ASSET_MIME='application/x-packstudio-asset'

def grab_cursor():
    pix=QPixmap(28,28);pix.fill(Qt.GlobalColor.transparent);p=QPainter(pix)
    path=QPainterPath();path.moveTo(8,24);path.lineTo(3,13);path.cubicTo(1,8,5,7,7,11)
    path.lineTo(7,5);path.cubicTo(7,2,11,2,11,5);path.lineTo(11,10)
    path.lineTo(11,3);path.cubicTo(11,0,15,0,15,3);path.lineTo(15,10)
    path.lineTo(15,4);path.cubicTo(15,1,19,1,19,4);path.lineTo(19,11)
    path.cubicTo(23,6,26,10,24,16);path.lineTo(21,24);path.closeSubpath()
    p.setPen(QColor('#161616'));p.setBrush(QColor('#eeeeee'));p.drawPath(path);p.end();return pix

class CompositionList(QListWidget):
    orderChanged=Signal(object)
    deleteRequested=Signal(object)
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction);self.setDropIndicatorShown(True)
    def dropEvent(self,event):
        super().dropEvent(event)
        self.orderChanged.emit([self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())])
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Delete:
            self.deleteRequested.emit([i.data(Qt.ItemDataRole.UserRole) for i in self.selectedItems()]);event.accept()
        else:super().keyPressEvent(event)

class AssetTree(QTreeWidget):
    assetActivated=Signal(object)
    libraryMoved=Signal(object,object)
    assetDropped=Signal(object)
    selectionCancelled=Signal()
    drag_role='library'
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setExpandsOnDoubleClick(False)
        self.sticky_parent=QToolButton(self.viewport());self.sticky_parent.setAutoRaise(False)
        self.sticky_parent.setStyleSheet('QToolButton {background:#252526;color:#dddddd;text-align:left;border:0;border-bottom:1px solid #444;padding:3px;}')
        self.sticky_parent.hide();self.sticky_index=QPersistentModelIndex()
        self.sticky_parent.clicked.connect(self.collapse_sticky)
        self.verticalScrollBar().valueChanged.connect(self.update_sticky)
        self.itemExpanded.connect(lambda *_:self.update_sticky());self.itemCollapsed.connect(lambda *_:self.update_sticky())
        self.model().modelReset.connect(self.update_sticky);self.model().rowsRemoved.connect(lambda *_:self.update_sticky())
    def resizeEvent(self,event):
        super().resizeEvent(event);self.update_sticky()
    def update_sticky(self,*args):
        if not hasattr(self,'sticky_parent'):return
        item=self.itemAt(QPoint(2,1));ancestor=item.parent() if item else None
        if ancestor is None or self.visualItemRect(ancestor).top()>=0:
            self.sticky_parent.hide();self.sticky_index=QPersistentModelIndex();return
        names=[];node=ancestor
        while node:names.append(node.text(0));node=node.parent()
        text=' / '.join(reversed(names));self.sticky_index=QPersistentModelIndex(self.indexFromItem(ancestor))
        self.sticky_parent.setText('⌃ '+ancestor.text(0));self.sticky_parent.setToolTip(text+'\n点击收起 / Click to collapse')
        self.sticky_parent.setGeometry(0,0,self.viewport().width(),26);self.sticky_parent.show();self.sticky_parent.raise_()
    def collapse_sticky(self):
        if not self.sticky_index.isValid():return
        item=self.itemFromIndex(self.sticky_index)
        if item:item.setExpanded(False);self.scrollToItem(item)
        self.update_sticky()
    def clear_drop_line(self):
        self.drop_line=None;self.viewport().update()
    def insertion_point(self,event,payload):
        target=self.itemAt(event.position().toPoint());asset=payload['asset']
        if self.drag_role=='project' or asset.get('kind')=='root':
            while target and target.parent():target=target.parent()
            parent=self.invisibleRootItem()
        else:
            source=next((item for item in self.findItems('*',Qt.MatchFlag.MatchWildcard|Qt.MatchFlag.MatchRecursive) if item.data(0,Qt.ItemDataRole.UserRole)==asset),None)
            if source is None:return None
            parent=source.parent() or self.invisibleRootItem()
            if target and (target.parent() or self.invisibleRootItem()) is not parent:return None
        if self.drag_role=='library' and payload['role']!='library':return None
        if self.drag_role=='project' and payload['role']=='project' and asset.get('kind')!='root':return None
        index=parent.indexOfChild(target) if target else parent.childCount()
        if target and event.position().y()>self.visualItemRect(target).center().y():index+=1
        before=parent.child(index) if index<parent.childCount() else None
        if before:y=self.visualItemRect(before).top()
        elif parent.childCount():
            last=parent.child(parent.childCount()-1)
            while last.isExpanded() and last.childCount():last=last.child(last.childCount()-1)
            y=self.visualItemRect(last).bottom()+1
        else:y=3
        return index,before,max(2,min(self.viewport().height()-3,y))
    def paintEvent(self,event):
        super().paintEvent(event)
        y=getattr(self,'drop_line',None)
        if y is not None:
            p=QPainter(self.viewport());p.setPen(QPen(QColor('#29b6ff'),2));p.drawLine(4,y,self.viewport().width()-5,y);p.drawEllipse(2,y-2,4,4);p.end()
    def selectionCommand(self,index,event=None):
        if event is not None:return QItemSelectionModel.SelectionFlag.NoUpdate
        return super().selectionCommand(index,event)
    def mousePressEvent(self,event):
        item=self.itemAt(event.position().toPoint())
        self.press_index=QPersistentModelIndex(self.indexFromItem(item)) if item else QPersistentModelIndex()
        self.branch_press=False
        self.press_expanded=item.isExpanded() if item else None
        self.drag_origin=event.position().toPoint();self.drag_descriptor=item.data(0,Qt.ItemDataRole.UserRole) if item else None;self.dragged=False
        if self.drag_descriptor and self.drag_descriptor.get('origin')=='@category':self.drag_descriptor=None
        if event.button()==Qt.MouseButton.LeftButton and item:
            rect=self.visualItemRect(item);indent=self.indentation()
            branch=QRect(rect.right()+1,rect.top(),indent,rect.height()) if self.layoutDirection()==Qt.LayoutDirection.RightToLeft else QRect(rect.left()-indent,rect.top(),indent,rect.height())
            expandable=item.childCount()>0 or item.childIndicatorPolicy()==QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
            if expandable and branch.contains(event.position().toPoint()):
                self.branch_press=True;self.drag_descriptor=None
                item.setExpanded(not item.isExpanded());event.accept();return
        super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if event.buttons()&Qt.MouseButton.LeftButton and getattr(self,'drag_descriptor',None) and (event.position().toPoint()-self.drag_origin).manhattanLength()>=QApplication.startDragDistance():
            self.dragged=True;drag=QDrag(self);mime=QMimeData();mime.setData(ASSET_MIME,json.dumps({'role':self.drag_role,'asset':self.drag_descriptor}).encode('utf-8'));drag.setMimeData(mime)
            hand=grab_cursor()
            for action in (Qt.DropAction.CopyAction,Qt.DropAction.MoveAction,Qt.DropAction.IgnoreAction):drag.setDragCursor(hand,action)
            QApplication.setOverrideCursor(QCursor(hand,12,12))
            try:drag.exec(Qt.DropAction.CopyAction|Qt.DropAction.MoveAction,Qt.DropAction.MoveAction)
            finally:QApplication.restoreOverrideCursor();self.drag_descriptor=None
            return
        super().mouseMoveEvent(event)
    def dragEnterEvent(self,event):
        self.dragMoveEvent(event)
    def dragMoveEvent(self,event):
        try:
            payload=json.loads(bytes(event.mimeData().data(ASSET_MIME)));point=self.insertion_point(event,payload)
            if point is None:raise ValueError('Invalid drop target')
            self.drop_line=point[2];self.viewport().update();event.acceptProposedAction()
        except (ValueError,KeyError,TypeError):self.clear_drop_line();event.ignore()
    def dragLeaveEvent(self,event):
        self.clear_drop_line();event.accept()
    def dropEvent(self,event):
        self.clear_drop_line()
        try:
            payload=json.loads(bytes(event.mimeData().data(ASSET_MIME)));point=self.insertion_point(event,payload)
            if point is None:event.ignore();return
            target=point[1]
            if payload['role']!='library':event.ignore();return
            self.libraryMoved.emit(payload['asset'],target.data(0,Qt.ItemDataRole.UserRole) if target else None)
            event.setDropAction(Qt.DropAction.CopyAction);event.accept()
        except (ValueError,KeyError,TypeError):event.ignore()
    def mouseReleaseEvent(self,event):
        if getattr(self,'branch_press',False):
            self.branch_press=False;event.accept();return
        pressed=getattr(self,'press_index',QPersistentModelIndex())
        if not pressed.isValid() or self.indexAt(event.position().toPoint())!=pressed:
            super().mouseReleaseEvent(event);return
        super().mouseReleaseEvent(event)
        if not pressed.isValid():return
        item=self.itemFromIndex(QModelIndex(pressed))
        if event.button()!=Qt.MouseButton.LeftButton or not item or getattr(self,'dragged',False):return
        d=item.data(0,Qt.ItemDataRole.UserRole) or {}
        # Qt handles branch arrows and enabled checkboxes; a folder label also toggles.
        checkbox=bool(item.flags()&Qt.ItemFlag.ItemIsUserCheckable) and 0<=event.position().x()-self.visualItemRect(item).x()<22
        if d.get('kind') in ('root','folder','resource_group'):
            if not checkbox and item.isExpanded()==self.press_expanded:item.setExpanded(not item.isExpanded())
        elif not checkbox and item.isExpanded()==self.press_expanded:self.assetActivated.emit(d)
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:self.clearSelection();self.selectionCancelled.emit();event.accept()
        else:super().keyPressEvent(event)

class ProjectTree(AssetTree):
    drag_role='project'
    deleteRequested=Signal(object)
    orderChanged=Signal(object)
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(True)
    def dropEvent(self,event):
        self.clear_drop_line()
        if hasattr(event,'mimeData') and event.mimeData().hasFormat(ASSET_MIME):
            try:
                payload=json.loads(bytes(event.mimeData().data(ASSET_MIME)))
                if payload['role']=='library':
                    point=self.insertion_point(event,payload)
                    self.assetDropped.emit({**payload['asset'],'_insert_index':point[0]});event.setDropAction(Qt.DropAction.CopyAction);event.accept();return
                dragged=payload['asset']
            except (ValueError,KeyError,TypeError):event.ignore();return
        else:dragged=None
        # Project items can be reordered, never nested or moved into pack folders.
        roots=[self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        selected=[item for item in roots if item.isSelected()]
        if dragged:
            if dragged.get('kind')!='root':event.ignore();return
            hit=next((item for item in roots if item.data(0,Qt.ItemDataRole.UserRole)['origin']==dragged['origin']),None)
            if hit not in selected:selected=[hit] if hit else []
        if event.source() is not self or not selected or (not dragged and len(selected)!=len(self.selectedItems())):
            event.ignore();return
        target=self.itemAt(event.position().toPoint())
        while target and target.parent():target=target.parent()
        index=roots.index(target) if target else len(roots)
        if target and event.position().y()>self.visualItemRect(target).center().y():index+=1
        before=[item for item in roots[:index] if item not in selected]
        after=[item for item in roots[index:] if item not in selected]
        self.orderChanged.emit([(item.data(0,Qt.ItemDataRole.UserRole) or {})['origin'][6:] for item in before+selected+after])
        # The controller rebuilds rows from IDs. Do not let Qt also delete/move them.
        event.setDropAction(Qt.DropAction.IgnoreAction);event.accept()
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Delete:
            self.deleteRequested.emit([i.data(0,Qt.ItemDataRole.UserRole) for i in self.selectedItems()]);event.accept()
        else:super().keyPressEvent(event)
