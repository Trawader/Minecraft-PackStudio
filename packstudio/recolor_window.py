"""Modeless recolor controls sharing the editor's existing transaction state."""
from PySide6.QtCore import Qt,QSignalBlocker,QTimer
from PySide6.QtWidgets import QDockWidget,QWidget,QVBoxLayout,QScrollArea,QPushButton,QSizePolicy
from PySide6.QtGui import QShortcut,QKeySequence


class RecolorWindow(QDockWidget):
    def __init__(self,window,panel):
        root=window
        super().__init__('调色',root)
        self.panel=panel;self.setObjectName('studio-recolor')
        self.fit_timer=QTimer(self);self.fit_timer.setSingleShot(True);self.fit_timer.timeout.connect(self.fit_page)
        from .dock_chrome import configure
        configure(self,close_button=True,floating_only=True);self.setMinimumSize(200,100)
        content=QWidget();self.setWidget(content);layout=QVBoxLayout(content)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        panel.setMinimumSize(0,0);panel.setMaximumSize(16777215,16777215)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred)
        self.scroll.setWidget(panel);layout.addWidget(self.scroll)
        panel.show();panel.body.show();panel.body.setEnabled(False)
        root.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,self);self.setFloating(True);self.resize(460,370);self.hide()
        self.visibilityChanged.connect(self.visibility)
        for button in panel.findChildren(QPushButton):button.setAutoDefault(False)
        for key,callback in [('Ctrl+Z',panel.canvas.undo),('Ctrl+Shift+Z',panel.canvas.redo)]:
            shortcut=QShortcut(QKeySequence(key),self);shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)
        shortcut=QShortcut(QKeySequence('Escape'),self);shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);shortcut.activated.connect(self.close)

    def reject(self):self.close()

    def visibility(self,visible):
        self.sync_buttons(visible)
        if visible:
            from .capabilities import sync_editor
            sync_editor(self.panel.window)
        if not visible and self.isHidden():self.panel.invalidate()

    def sync_buttons(self,visible):
        kind=getattr(self.panel,'tool_kind','recolor')
        pairs=[('recolor',self.panel.toggle),('gradient',self.panel.window.gradient_button)]
        for name,button in pairs:
            with QSignalBlocker(button):button.setChecked(self.panel.canvas.tool=='gradient' if name=='gradient' else visible and name==kind)

    def display(self,show,kind='recolor',page=None):
        if show:
            if page is not None:self.panel.gradient_page=page
            self.panel.select_tool(kind)
            self.panel.window.set_tool(kind)
            from .localization import text
            self.setWindowTitle(text('渐变' if kind=='gradient' else '调色',getattr(self.parentWidget(),'lang','zh')))
            self.sync_buttons(True)
            from .capabilities import sync_editor
            sync_editor(self.panel.window)
            from .dock_chrome import fit_floating
            fit_floating(self)
            self.show();self.raise_();self.fit_page();QTimer.singleShot(0,self.fit_page)
        else:self.close()

    def request_fit(self):self.fit_timer.start(0)

    def fit_page(self):
        if getattr(self.panel,'tool_kind',None)!='gradient':
            self.panel.body_layout.invalidate();self.panel.body_layout.activate()
            hint=self.panel.body.sizeHint();minimum=self.panel.body.minimumSizeHint()
            margins=self.widget().layout().contentsMargins()
            width=max(180,hint.width(),minimum.width())+margins.left()+margins.right()+4
            height=max(80,hint.height())+(self.titleBarWidget().height() if self.titleBarWidget() else 0)+margins.top()+margins.bottom()+4
            self.resize(width,height)
            from .dock_chrome import fit_floating
            fit_floating(self);return
        controls=self.panel.transition_controls if self.panel.gradient_page=='transition' else self.panel.endpoint_editor
        if controls is None:return
        controls.layout().activate();self.panel.body_layout.activate()
        height=controls.sizeHint().height()+(self.titleBarWidget().height() if self.titleBarWidget() else 0)+48
        if self.panel.gradient_page=='colors':height+=self.panel.first.sizeHint().height()+8
        width=max(360,controls.minimumSizeHint().width()+48)
        self.resize(width,max(220,height))
        from .dock_chrome import fit_floating
        fit_floating(self)

    def closeEvent(self,event):
        self.panel.invalidate()
        self.sync_buttons(False)
        if self.panel.canvas.tool=='recolor':
            self.panel.window.set_tool('mouse')
        event.accept()
