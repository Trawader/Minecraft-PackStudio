"""Uniform dock headers and hover-gated native docking gestures."""
from PySide6.QtCore import Qt,QSize,QEvent,QObject,QTimer,QPoint,QRect,QRectF,QParallelAnimationGroup,QPropertyAnimation,QEasingCurve
from PySide6.QtGui import QCursor,QPainter,QPen,QIcon,QColor,QPainterPath,QRegion
from PySide6.QtWidgets import QWidget,QLabel,QHBoxLayout,QDockWidget,QSizePolicy,QToolButton,QStyle,QApplication,QAbstractButton,QMainWindow
from shiboken6 import isValid
import time


class DockHeader(QWidget):
    def __init__(self,dock,close_button=False):
        super().__init__(dock);self.setObjectName('studioDockHeader')
        layout=QHBoxLayout(self);layout.setContentsMargins(10,0,10,0)
        self.label=QLabel(dock.windowTitle());self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.label.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Preferred)
        layout.addWidget(self.label);dock.windowTitleChanged.connect(self.label.setText)
        if close_button:
            close=QToolButton(self);self.close_button=close
            close.setFixedSize(24,24)
            close.setStyleSheet('QToolButton {padding:0;border:0;background:transparent;} QToolButton:hover {background:#484848;border-radius:4px;}')
            close.setToolTip('关闭 / Close');close.clicked.connect(dock.close);layout.addWidget(close)
        # The title is already visible; do not spawn a duplicate title tooltip.
        self.setStyleSheet('#studioDockHeader {background:#181818;border:0;border-bottom:1px solid #303030;} QLabel {background:transparent;border:0;}')
        self.fit()
    def fit(self):
        self.setFixedHeight(max(32,self.fontMetrics().height()+14))
        if hasattr(self,'close_button'):
            logical=max(12,self.fontMetrics().height()-3)
            self.close_button.setIconSize(QSize(logical,logical))
            ratio=self.devicePixelRatioF();size=round(logical*ratio)
            pixmap=self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton).pixmap(size,size)
            painter=QPainter(pixmap);painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(pixmap.rect(),QColor('#bcbcbc'));painter.end();pixmap.setDevicePixelRatio(ratio)
            self.close_button.setIcon(QIcon(pixmap))
    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange,QEvent.Type.StyleChange):self.fit()
    def minimumSizeHint(self):return QSize(120,self.height())
    def sizeHint(self):return QSize(self.fontMetrics().horizontalAdvance(self.label.text())+24,self.height())
    # The application drag controller handles press/move/release uniformly.
    # Unhandled gestures, including double-click, still reach QDockWidget.
    def mousePressEvent(self,event):event.ignore()
    def mouseMoveEvent(self,event):event.ignore()
    def mouseReleaseEvent(self,event):event.ignore()
    def mouseDoubleClickEvent(self,event):
        if self.parentWidget().property('floatingOnly'):event.accept()
        else:event.ignore()


class NativeFloatingTitle(QObject):
    """Use OS chrome while floating, retaining the compact docked header."""
    def __init__(self,dock):
        super().__init__(dock);self.dock=dock;self.header=dock.titleBarWidget();self.busy=False
        dock.topLevelChanged.connect(self.schedule);self.schedule()
    def schedule(self,*args):QTimer.singleShot(0,self,self.sync)
    def sync(self):
        dock=self.dock
        if self.busy or not isValid(dock):return
        controller=getattr(QApplication.instance(),'dock_hover_controller',None)
        if controller and controller.dock is dock:
            QTimer.singleShot(50,self,self.sync);return
        self.busy=True
        try:
            floating=dock.isFloating();visible=dock.isVisible();geometry=dock.geometry()
            if floating and dock.titleBarWidget() is not None:
                self.header=dock.titleBarWidget();dock.setTitleBarWidget(None);self.header.hide()
                dock.setProperty('nativeFloatingTitle',True);dock.clearMask()
                dock.setWindowFlags(Qt.WindowType.Window|Qt.WindowType.WindowTitleHint|Qt.WindowType.WindowSystemMenuHint|Qt.WindowType.WindowMinMaxButtonsHint|Qt.WindowType.WindowCloseButtonHint)
                dock.setGeometry(geometry)
                if visible:dock.show()
            elif not floating and dock.titleBarWidget() is None:
                dock.setProperty('nativeFloatingTitle',False);dock.setTitleBarWidget(self.header);self.header.show()
        finally:self.busy=False


def configure(dock,close_button=False,floating_only=False):
    dock.setProperty('floatingOnly',floating_only)
    dock.setAllowedAreas(Qt.DockWidgetArea.NoDockWidgetArea if floating_only else Qt.DockWidgetArea.AllDockWidgetAreas)
    dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable|QDockWidget.DockWidgetFeature.DockWidgetFloatable|QDockWidget.DockWidgetFeature.DockWidgetClosable)
    dock.setTitleBarWidget(DockHeader(dock,close_button))
    dock.corner_style=FloatingCorners(dock)
    dock.native_title=NativeFloatingTitle(dock)
    if floating_only:
        def enforce_floating():
            if isValid(dock) and not dock.isFloating():
                hidden=dock.isHidden();dock.setFloating(True)
                if hidden:dock.hide()
        dock.topLevelChanged.connect(lambda floating:QTimer.singleShot(0,enforce_floating) if not floating else None)
        # Also reject old saved layouts which recorded this tool as docked.
        QTimer.singleShot(0,enforce_floating)
    app=QApplication.instance()
    if not hasattr(app,'dock_hover_controller'):
        app.dock_hover_controller=DockHoverController(app);app.installEventFilter(app.dock_hover_controller)


class FloatingCorners(QObject):
    """Use Windows rounded window corners; clip only when unavailable."""
    def __init__(self,dock):
        super().__init__(dock);self.dock=dock;self.native=False;self.pending=False
        dock.installEventFilter(self);dock.topLevelChanged.connect(self.schedule)
    def eventFilter(self,obj,event):
        if event.type() in (QEvent.Type.Show,QEvent.Type.WinIdChange):self.schedule()
        elif event.type()==QEvent.Type.Resize and not self.native:self.clip()
        return False
    def schedule(self,*args):
        if not self.pending:self.pending=True;QTimer.singleShot(0,self.apply)
    def apply(self):
        self.pending=False;dock=self.dock
        if not isValid(dock):return
        if dock.property('nativeFloatingTitle'):dock.clearMask();self.native=True;return
        self.native=False
        if dock.isFloating():
            import sys
            if sys.platform=='win32':
                import ctypes
                from ctypes import wintypes
                try:
                    corner=ctypes.c_int(2)  # DWMWCP_ROUND; preserve native resize borders.
                    fn=ctypes.windll.dwmapi.DwmSetWindowAttribute
                    fn.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
                    fn.restype=ctypes.c_long
                    self.native=fn(int(dock.winId()),33,ctypes.byref(corner),ctypes.sizeof(corner))==0
                except (OSError,AttributeError):pass
        if self.native or not dock.isFloating():dock.clearMask()
        else:self.clip()
    def clip(self):
        dock=self.dock
        if not isValid(dock):return
        if not dock.isFloating() or dock.property('nativeFloatingTitle'):dock.clearMask();return
        if self.native:return
        path=QPainterPath();path.addRoundedRect(QRectF(dock.rect()),8,8)
        dock.setMask(QRegion(path.toFillPolygon().toPolygon()))


class DockDropPreview(QWidget):
    """Workspace-local highlight, always below the floating drag window."""
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # This is a child overlay, not a translucent native window. Setting
        # WA_TranslucentBackground also disables background restoration and
        # leaves blue trails in the parent's backing store when it moves.
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent,False)
        self.setStyleSheet('background:transparent;border:0;')
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    def moveEvent(self,event):
        parent=self.parentWidget()
        if parent:parent.update(QRect(event.oldPos(),self.size()).united(self.geometry()))
        super().moveEvent(event)
    def resizeEvent(self,event):
        parent=self.parentWidget()
        if parent:parent.update(QRect(self.pos(),event.oldSize()).united(self.geometry()))
        super().resizeEvent(event)
    def hideEvent(self,event):
        if self.parentWidget():self.parentWidget().update(self.geometry())
        super().hideEvent(event)
    def paintEvent(self,event):
        painter=QPainter(self);color=self.palette().highlight().color()
        color.setAlpha(65);painter.fillRect(self.rect(),color)
        color.setAlpha(210);painter.setPen(QPen(color,2));painter.drawRect(self.rect().adjusted(1,1,-2,-2))


class DockMotion(QObject):
    """Animate explicit layout changes, which bypass Qt's native drag animator."""
    def __init__(self,parent):
        super().__init__(parent);self.root=None;self.group=None;self.options=None
    def stop(self):
        if self.group is not None:
            self.group.stop();self.group.deleteLater();self.group=None
        if self.root is not None and isValid(self.root):
            self.root.layout().setEnabled(True)
            if self.options is not None:self.root.setDockOptions(self.options)
        self.root=None;self.options=None
    def capture(self,root):
        # Stop at the current visual positions, not at the previous endpoints.
        starts={d:QRect(d.geometry()) for d in root.findChildren(QDockWidget)
                if d.parentWidget() is root and d.isVisible() and not d.isFloating()}
        self.stop();self.root=root;self.options=root.dockOptions()
        root.setDockOptions(self.options & ~QMainWindow.DockOption.AnimatedDocks)
        return starts
    def play(self,starts,duration=260):
        root=self.root
        if root is None or not isValid(root):self.stop();return
        layout=root.layout();layout.invalidate();layout.activate()
        ends={d:QRect(d.geometry()) for d in starts if isValid(d) and d.parentWidget() is root
              and d.isVisible() and not d.isFloating()}
        group=QParallelAnimationGroup(self)
        for dock,end in ends.items():
            if starts[dock]==end:continue
            animation=QPropertyAnimation(dock,b'geometry',group)
            animation.setDuration(duration);animation.setStartValue(starts[dock]);animation.setEndValue(end)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic);group.addAnimation(animation)
        if not group.animationCount():group.deleteLater();self.stop();return
        # The layout has already computed its final state. Pause its geometry
        # writes while widgets interpolate; retain that state for save/restore.
        layout.setEnabled(False);self.group=group
        group.finished.connect(self.complete);group.start()
    def complete(self):
        root=self.root;self.stop()
        if root is not None and isValid(root):root.layout().activate()


class DockHoverController(QObject):
    """One drag owner: stable candidate, persistent preview, explicit split on drop."""
    DWELL=.075
    def __init__(self,app):
        super().__init__(app);self.dock=None;self.header=None;self.dragging=False
        self.target=None;self.armed=False;self.preview=DockDropPreview()
        self.placeholder=None;self.preview_bounds={}
        self.motion=DockMotion(self)
        self.timer=QTimer(self);self.timer.setInterval(25);self.timer.timeout.connect(self.poll)
    def eventFilter(self,obj,event):
        kind=event.type()
        if kind==QEvent.Type.NonClientAreaMouseButtonPress and event.button()==Qt.MouseButton.LeftButton and isinstance(obj,QDockWidget) and obj.isFloating() and not obj.property('floatingOnly'):
            # Preserve hover docking when dragging a native title, while leaving
            # system buttons, resize borders and tool-only windows to the OS.
            point=event.globalPosition().toPoint();frame=obj.frameGeometry()
            top=obj.mapToGlobal(QPoint(0,0)).y();height=max(24,top-frame.top())
            if frame.top()<=point.y()<top and frame.left()+height<point.x()<frame.right()-height*4:
                root=obj.parentWidget()
                if isinstance(root,QMainWindow):
                    self.finish(cancel=True);self.dock=obj;self.root=root;self.header=obj
                    self.press=point;self.offset=point-obj.pos()
                    self.original_state=root.saveState();self.original_geometry=obj.geometry();self.original_floating=True
                    self.timer.start();return True
        if self.dock is not None and kind==QEvent.Type.Close and obj in (self.dock,self.root):
            self.finish(cancel=True);self.motion.stop()
        if kind==QEvent.Type.MouseButtonPress and event.button()==Qt.MouseButton.LeftButton:
            widget=obj
            while isinstance(widget,QWidget) and not isinstance(widget,DockHeader):
                if isinstance(widget,QAbstractButton):return False
                widget=widget.parentWidget()
            if isinstance(widget,DockHeader):
                self.finish(cancel=True)
                dock=widget.parentWidget();root=dock.parentWidget()
                if not isinstance(root,QMainWindow):return False
                # Native movement avoids rebuilding an already floating tool.
                if dock.property('floatingOnly') and dock.isFloating():
                    handle=dock.windowHandle()
                    if handle is not None and handle.startSystemMove():return True
                self.dock=dock;self.root=root;self.header=widget
                self.press=event.globalPosition().toPoint()
                self.offset=self.press-dock.mapToGlobal(QPoint(0,0))
                self.original_state=root.saveState();self.original_geometry=dock.geometry()
                self.original_floating=dock.isFloating();self.timer.start()
                # Consume the press as well: native Qt must not run a second drag.
                return True
        elif kind==QEvent.Type.MouseMove and self.dock:
            self.update_drag(event.globalPosition().toPoint());return True
        elif kind==QEvent.Type.MouseButtonRelease and self.dock and event.button()==Qt.MouseButton.LeftButton:
            self.update_drag(event.globalPosition().toPoint());self.finish();return True
        elif kind==QEvent.Type.KeyPress and self.dock and event.key()==Qt.Key.Key_Escape:
            self.finish(cancel=True);return True
        return False
    def bounds(self,dock):return QRect(dock.mapToGlobal(QPoint(0,0)),dock.size())
    def target_bounds(self,dock):
        return self.preview_bounds.get(dock,self.bounds(dock))
    def in_edge(self,target,pos,retain=False):
        dock,side=target
        if not isValid(dock) or not dock.isVisible() or dock.isFloating():return False
        # Keep hit testing in the pre-preview layout. Otherwise moving the
        # target to make space would immediately invalidate its own hover.
        if retain and self.placeholder is not None and target==self.target:
            if self.bounds(self.placeholder).adjusted(-22,-22,22,22).contains(pos):return True
        rect=self.target_bounds(dock);extra=22 if retain else 0
        # Logical pixels scale with DPI. A wide entry band and larger exit band
        # prevent small pointer movements from restarting the dwell timer.
        band=max(48,min(96,round(min(rect.width(),rect.height())*.22)))+extra
        outside=24+extra
        if not rect.adjusted(-outside,-outside,outside,outside).contains(pos):return False
        distance=(abs(pos.x()-rect.left()),abs(pos.x()-rect.right()),
                  abs(pos.y()-rect.top()),abs(pos.y()-rect.bottom()))[side]
        return distance<=band
    def edge(self,pos):
        if self.dock.property('floatingOnly'):return None
        if self.target and self.in_edge(self.target,pos,retain=True):return self.target
        choices=[]
        for dock in self.root.findChildren(QDockWidget):
            if dock is self.dock or dock is self.placeholder or dock.property('floatingOnly') or dock.parentWidget() is not self.root or dock.isFloating() or not dock.isVisible():continue
            rect=self.target_bounds(dock)
            distances=(abs(pos.x()-rect.left()),abs(pos.x()-rect.right()),abs(pos.y()-rect.top()),abs(pos.y()-rect.bottom()))
            for side,distance in enumerate(distances):
                if self.in_edge((dock,side),pos):choices.append((distance,dock.objectName(),side,dock))
        if not choices:return None
        best=min(choices,key=lambda item:item[:3]);return best[3],best[2]
    def begin_preview(self):
        target,side=self.target
        # A child overlay can rise above dock contents but never above the
        # floating window. A top-level ToolTip would tint the dragged window.
        if self.preview.parentWidget() is not self.root:self.preview.setParent(self.root)
        self.preview_state=self.root.saveState()
        self.preview_bounds={d:self.bounds(d) for d in self.root.findChildren(QDockWidget)
                             if d.parentWidget() is self.root and not d.isFloating() and d.isVisible()}
        starts=self.motion.capture(self.root)
        gap=QDockWidget('',self.root);gap.setObjectName('_temporary_dock_drop_space')
        gap.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        gap.setTitleBarWidget(QWidget(gap));body=QWidget(gap);gap.setWidget(body)
        gap.setMinimumSize(self.dock.minimumSize().expandedTo(self.dock.minimumSizeHint()))
        self.placeholder=gap
        orientation=Qt.Orientation.Horizontal if side<2 else Qt.Orientation.Vertical
        self.root.splitDockWidget(target,gap,orientation)
        if side in (0,2):self.root.splitDockWidget(gap,target,orientation)
        gap.show()
        rect=self.preview_bounds[target]
        extent=rect.width() if side<2 else rect.height()
        self.root.resizeDocks([gap,target],[max(1,extent//2),max(1,extent//2)],orientation)
        self.motion.play(starts)
    def end_preview(self,commit=False):
        gap=self.placeholder
        if gap is None:return
        starts=self.motion.capture(self.root)
        floating_geometry=self.dock.geometry() if self.dock is not None and isValid(self.dock) else None
        if commit:
            # Replace the temporary space in place, without first collapsing it.
            starts[self.dock]=QRect(self.root.mapFromGlobal(self.dock.mapToGlobal(QPoint(0,0))),self.dock.size())
            gap.setMinimumSize(0,0)
            self.dock.setFloating(False)
            self.root.splitDockWidget(gap,self.dock,Qt.Orientation.Horizontal)
            self.dock.show();self.dock.raise_()
        self.root.removeDockWidget(gap);gap.hide();gap.setParent(None);gap.deleteLater()
        self.placeholder=None;self.preview_bounds={};self.preview.hide()
        if not commit:
            self.root.restoreState(self.preview_state)
            if floating_geometry is not None:self.dock.setGeometry(floating_geometry)
        self.motion.play(starts,280 if commit else 240)
    def update_drag(self,pos):
        if not self.dock or not isValid(self.dock):self.finish(cancel=True);return
        if not self.dragging:
            if (pos-self.press).manhattanLength()<QApplication.startDragDistance():return
            self.motion.stop()
            self.dragging=True
            if not self.dock.isFloating():self.dock.setFloating(True);self.dock.show()
            self.header.grabMouse()
        destination=pos-self.offset
        if self.dock.pos()!=destination:self.dock.move(destination)
        target=self.edge(pos)
        if target!=self.target:
            self.end_preview()
            self.target=target;self.since=time.monotonic();self.armed=False;self.preview.hide()
        if target and not self.armed and time.monotonic()-self.since>=self.DWELL:
            self.armed=True;self.begin_preview()
        if self.armed:
            rect=self.bounds(self.placeholder)
            rect.moveTopLeft(self.root.mapFromGlobal(rect.topLeft()))
            self.preview.setGeometry(rect);self.preview.show();self.preview.raise_()
    def poll(self):
        if not self.dock:return
        if not QApplication.mouseButtons()&Qt.MouseButton.LeftButton:
            # Capture the final location even if release occurred outside the app.
            self.update_drag(QCursor.pos());self.finish();return
        self.update_drag(QCursor.pos())
    def finish(self,cancel=False):
        dock=self.dock;self.timer.stop();self.preview.hide()
        if self.header is not None and isValid(self.header) and QWidget.mouseGrabber() is self.header:self.header.releaseMouse()
        if dock is not None and isValid(dock) and self.dragging:
            if cancel:
                self.end_preview()
                starts=self.motion.capture(self.root)
                self.root.restoreState(self.original_state)
                if self.original_floating:dock.setGeometry(self.original_geometry)
                self.motion.play(starts,240)
            elif self.armed and self.target and self.in_edge(self.target,QCursor.pos(),retain=True):
                self.end_preview(commit=True)
            else:self.end_preview();fit_floating(dock)
        else:self.end_preview()
        self.dock=None
        self.header=None;self.dragging=False;self.target=None;self.armed=False


def fit_floating(dock):
    if not dock.isFloating():return
    area=dock.screen().availableGeometry();margin=12
    dock.resize(min(dock.width(),area.width()-margin*2),min(dock.height(),area.height()-margin*2))
    dock.move(max(area.left()+margin,min(dock.x(),area.right()-dock.width()-margin)),
              max(area.top()+margin,min(dock.y(),area.bottom()-dock.height()-margin)))


def settings_panel(window):
    old=window.settings_dialog;content=QWidget();content.setLayout(old.layout())
    for label in content.findChildren(QLabel):
        label.setWordWrap(True);label.setMinimumWidth(0)
        label.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Preferred)
    dock=QDockWidget(old.windowTitle(),window);dock.setObjectName('studio-settings')
    from PySide6.QtWidgets import QScrollArea
    scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame);scroll.setWidget(content)
    dock.setWidget(scroll);configure(dock,close_button=True,floating_only=True);window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,dock)
    dock.setFloating(True);dock.resize(440,520);dock.hide();old.hide();old.deleteLater()
    window.settings_dialog=dock;action=window.settings_action;action.triggered.disconnect();action.setCheckable(True)
    def toggle(visible):
        if visible:
            from PySide6.QtWidgets import QToolTip
            QToolTip.hideText();dock.resize(440,dock.height());fit_floating(dock);dock.show();dock.raise_()
        else:dock.hide()
    action.triggered.connect(toggle);dock.visibilityChanged.connect(action.setChecked)


def library_widths(window):
    fm=window.search.fontMetrics()
    text_width=max(fm.horizontalAdvance(text) for text in (
        '搜索素材库：名称、路径、小部件','Search library: name, path, component'))
    # Outer margins, input padding, clear button and a small breathing space.
    widened=max(300,text_width+64)
    preferred=round((220+widened)/2)
    return 220,preferred


def default_layout(window):
    docks=window.docks;width=window.contentsRect().width();height=window.contentsRect().height()
    fm=window.fontMetrics()
    minimum,preferred=library_widths(window)
    left=preferred
    right=max(300,min(int(width*.29),fm.horizontalAdvance('普通方块  ·  按模型关联贴图')+110))
    for key in ('library','project'):docks[key].setMinimumWidth(minimum)
    docks['editor'].setMinimumWidth(300);docks['render'].setMinimumWidth(260)
    if width<1000:
        window.tabifyDockWidget(docks['editor'],docks['render']);docks['editor'].raise_()
        window.resizeDocks([docks['library'],docks['editor']],[left,max(360,width-left-12)],Qt.Orientation.Horizontal)
    else:
        window.resizeDocks([docks['library'],docks['editor'],docks['render']],
                           [left,max(360,width-left-right-18),right],Qt.Orientation.Horizontal)
    window.resizeDocks([docks['library'],docks['project']],
                       [max(180,int(height*.48)),max(180,int(height*.52))],Qt.Orientation.Vertical)


class ScreenLayout(QObject):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.initialized=False;window.installEventFilter(self)
    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.Show and not self.initialized:
            self.initialized=True;QTimer.singleShot(0,self.start)
        elif self.initialized and event.type()==QEvent.Type.FontChange:
            QTimer.singleShot(0,self.screen_changed)
        return False
    def start(self):
        w=self.window
        if not w.settings.value('workspace-layout-v4',False,type=bool):
            w.reset_layout();w.settings.setValue('workspace-layout-v4',True)
        if w.windowHandle():w.windowHandle().screenChanged.connect(self.screen_changed)
        self.screen_changed()
        if not w.settings.value('library-width-v32-compact-default',False,type=bool):
            _,preferred=library_widths(w)
            dock=w.docks['library']
            if not dock.isFloating():
                w.resizeDocks([dock],[preferred],Qt.Orientation.Horizontal)
            w.settings.setValue('library-width-v32-compact-default',True)
    def screen_changed(self,*args):
        minimum,_=library_widths(self.window)
        for key in ('library','project'):self.window.docks[key].setMinimumWidth(minimum)
        for dock in self.window.findChildren(QDockWidget):fit_floating(dock)
