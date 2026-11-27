"""Related assets for the single dockable canvas."""
import copy
from PySide6.QtCore import Qt,Signal,QSize,QSignalBlocker,QObject,QTimer
from PySide6.QtGui import QIcon,QPixmap,QAction
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QListWidgetItem,QSizePolicy


class ResourceCards(QListWidget):
    """Center the single row in the usable strip, including scrollbar changes."""
    def __init__(self):
        super().__init__()
        self.horizontalScrollBar().rangeChanged.connect(lambda *_:QTimer.singleShot(0,self,self.center_row))
    def center_row(self):
        bar=self.horizontalScrollBar()
        available=self.contentsRect().height()-(bar.height() if bar.isVisible() else 0)
        padding=max(0,(available-self.gridSize().height())//2)
        if self.viewportMargins().top()!=padding:self.setViewportMargins(0,padding,0,padding)
    def resizeEvent(self,event):
        super().resizeEvent(event);self.center_row()
    def showEvent(self,event):
        super().showEvent(event);QTimer.singleShot(0,self,self.center_row)


class ResourceStrip(QWidget):
    """Small child of the canvas panel; never a main-window bottom dock."""
    visibilityChanged=Signal(bool)
    def __init__(self,parent):
        super().__init__(parent);self.setFixedHeight(74)
        self.action=QAction('关联素材',self);self.action.setCheckable(True)
        self.action.toggled.connect(self.setVisible)
    def toggleViewAction(self):return self.action
    def showEvent(self,event):
        blocker=QSignalBlocker(self.action);self.action.setChecked(True);del blocker;super().showEvent(event);self.visibilityChanged.emit(True)
    def hideEvent(self,event):
        blocker=QSignalBlocker(self.action);self.action.setChecked(False);del blocker;super().hideEvent(event);self.visibilityChanged.emit(False)



class ResourceEditors(QObject):
    def __init__(self,window):
        super().__init__(window)
        self.window=window;self.context=None;self.paths=[]
        self.object_descriptor=None;self.thumbnail_bytes={}
        # Floating changes only the presentation of the existing editor dock.
        canvas_dock=window.docks['editor']
        # All floating docks share native OS chrome; no canvas-specific header.
        panel=window.docks['editor'].widget();dock=ResourceStrip(panel);dock.setObjectName('v3-object-strip-embedded')
        layout=QVBoxLayout(dock);layout.setContentsMargins(0,0,0,0);layout.setSpacing(2)
        header=QHBoxLayout();self.object_title=QLabel('关联素材');self.object_title.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred);header.addWidget(self.object_title,1)
        layout.addLayout(header)
        self.cards=ResourceCards();self.cards.setMouseTracking(True);self.cards.setFlow(QListWidget.Flow.LeftToRight);self.cards.setDragEnabled(False)
        self.cards.setStyleSheet('QListWidget::item {height:54px; padding:0 3px;} QListWidget::item:hover,QListWidget::item:selected {background:#3c3c3c; color:#cccccc;}')
        self.cards.setMinimumWidth(0);self.cards.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.cards.setViewMode(QListWidget.ViewMode.IconMode);self.cards.setWrapping(False);self.cards.setIconSize(QSize(32,32));self.cards.setGridSize(QSize(88,58))
        self.cards.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cards.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.cards.setFixedHeight(70);layout.addWidget(self.cards);panel.layout().addWidget(dock)
        self.dock=dock;dock.hide()
        self.cards.itemClicked.connect(lambda item:self.window.run(lambda:self.pick(item)))
        self.cards.itemEntered.connect(self.refresh_card)
        self.cards.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.cards.customContextMenuRequested.connect(self.card_menu)


    def card_menu(self,pos):
        item=self.cards.itemAt(pos)
        if item is None:return
        menu=self.window.resource_menu(item.data(Qt.ItemDataRole.UserRole))
        menu.exec(self.cards.viewport().mapToGlobal(pos))
        from shiboken6 import isValid
        if isValid(menu):menu.deleteLater()


    def select_object(self,descriptor):
        owner=self.window.source(descriptor['origin'])
        if owner is None:return
        self.object_descriptor=copy.deepcopy(descriptor);self.context=descriptor['origin']
        self.paths=sorted(p for p in descriptor['object_paths'] if p in owner.files and p.lower().endswith('.png'))
        self.cards.clear();self.thumbnail_bytes.clear();self.object_title.setText(descriptor['name']+f' · {len(self.paths)} 张素材')
        self.object_title.setToolTip(self.window.tr('单击切换素材','Click to switch texture'))
        from .selector_taxonomy import chinese_name,local_names
        from .semantics import identities
        names=local_names(owner.files);aliases=identities()[0]
        for index,path in enumerate(self.paths):
            identity=aliases.get(path,path.split('/textures/')[-1].removesuffix('.png'))
            namespace=path.split('/')[1] if path.startswith('assets/') else 'minecraft'
            entry={'kind':'png','origin':self.context,'path':path,'name':chinese_name(identity,path,namespace,names),'_object_context':copy.deepcopy(descriptor)}
            item=QListWidgetItem(entry['name']);item.setToolTip(path);item.setData(Qt.ItemDataRole.UserRole,entry);self.cards.addItem(item)
            if index<24:self.decorate_card(item,owner.files[path])
        self.dock.setVisible(bool(self.paths))


    def decorate_card(self,item,raw):
        from .sky_view import thumbnail
        descriptor=item.data(Qt.ItemDataRole.UserRole);key=(descriptor['origin'],descriptor['path'])
        if self.thumbnail_bytes.get(key)==raw:return
        try:item.setIcon(QIcon(QPixmap.fromImage(thumbnail(raw,32))))
        except ValueError:item.setIcon(QIcon())
        self.thumbnail_bytes[key]=raw


    def refresh_card(self,item):
        descriptor=item.data(Qt.ItemDataRole.UserRole);owner=self.window.source(descriptor['origin'])
        if owner and descriptor['path'] in owner.files:self.decorate_card(item,owner.files[descriptor['path']])


    def pick(self,item):
        descriptor=item.data(Qt.ItemDataRole.UserRole)
        owner=self.window.source(descriptor['origin'])
        if owner and item.icon().isNull() and descriptor['path'] in owner.files:self.decorate_card(item,owner.files[descriptor['path']])
        self.window.edit_descriptor(descriptor)


    def show_resources(self,descriptor):
        context=descriptor.get('_object_context')
        if context is None and descriptor.get('kind')=='png':
            from .animation_editor import state_paths
            owner=self.window.source(descriptor['origin'])
            paths=state_paths(owner.files,descriptor['path']) if owner else []
            if paths:context={**descriptor,'object_paths':paths}
        if context:
            if self.object_descriptor!=context:self.select_object(context)
            for i in range(self.cards.count()):
                item=self.cards.item(i)
                if item.data(Qt.ItemDataRole.UserRole)['path']==descriptor['path']:self.cards.setCurrentItem(item);break
            return
        self.object_descriptor=None;self.cards.clear();self.thumbnail_bytes.clear();self.paths=[];self.context=None;self.dock.hide()
        self.object_title.setText('关联素材');self.object_title.setToolTip('')


    def sync(self):
        if self.context and self.window.source(self.context) is None:
            self.cards.clear();self.thumbnail_bytes.clear();self.paths=[];self.context=None;self.object_descriptor=None;self.dock.hide()
        elif self.context:
            owner=self.window.source(self.context)
            for index in range(self.cards.count()-1,-1,-1):
                item=self.cards.item(index)
                descriptor=item.data(Qt.ItemDataRole.UserRole);path=descriptor['path']
                if path not in owner.files:
                    self.cards.takeItem(index);self.thumbnail_bytes.pop((self.context,path),None)
                elif (self.context,path) in self.thumbnail_bytes or self.cards.visualItemRect(item).intersects(self.cards.viewport().rect()):
                    self.decorate_card(item,owner.files[path])
            self.paths=[path for path in self.paths if path in owner.files]
            if not self.paths:self.dock.hide()



def install(window):window.resource_editors=ResourceEditors(window)
