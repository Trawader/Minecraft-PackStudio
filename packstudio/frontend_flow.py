"""Keep visible actions consistent with the current document and project."""
from PySide6.QtCore import QObject,QEvent,QTimer,Qt
from PySide6.QtWidgets import QLabel,QPushButton
from PySide6.QtGui import QAction


class EmptyHint(QLabel):
    def __init__(self,parent):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter);self.setWordWrap(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet('color:#999999; background:transparent; padding:12px; border:0;')
        parent.installEventFilter(self);self.fit()
    def fit(self):self.setGeometry(self.parentWidget().rect())
    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.Resize:self.fit()
        return False
    def display(self,text,visible):
        if self.text()!=text:self.setText(text)
        self.setVisible(visible)
        if visible:self.raise_()


class FrontendFlow(QObject):
    def __init__(self,window):
        super().__init__(window);self.window=window
        self.library_hint=EmptyHint(window.tree.viewport())
        self.project_hint=EmptyHint(window.project_tree.viewport())
        self.canvas_hint=EmptyHint(window.canvas)
        file_menu=window.menuBar().actions()[0].menu()
        self.project_undo=QAction('撤销资源操作',window)
        self.project_undo.triggered.connect(lambda:window.run(window.undo_resource))
        self.project_undo.setToolTip('撤销资源操作')
        self.export_buttons=window.compose_panel.findChildren(QPushButton)
        self.timer=QTimer(self);self.timer.setInterval(150);self.timer.timeout.connect(self.sync);self.timer.start()
        file_menu.aboutToShow.connect(self.sync)
        for signal in (window.canvas.changed,window.canvas.selectionChanged,window.canvas.zoomChanged):signal.connect(self.schedule)
        window.canvas.viewChanged.connect(self.schedule)
        self.sync()
    def schedule(self,*args):QTimer.singleShot(0,self.sync)
    def sync(self):
        w=self.window;c=w.canvas;loaded=not c.image.isNull();large=getattr(w,'large_view_only',False);editable=loaded and not c.read_only and not large
        self.canvas_hint.display(w.tr('从素材库或项目打开贴图','Open a texture from the library or project'),not loaded)
        library_empty=not any(not w.tree.topLevelItem(i).isHidden() for i in range(w.tree.topLevelItemCount()))
        library_text=w.tr('尚无素材\n通过“导入”菜单添加，或拖入材质包','No assets yet\nUse Import or drop a resource pack') if not w.sources and not w.defaults.isChecked() else w.tr('没有匹配素材\n请调整搜索或筛选条件','No matching assets\nAdjust the search or filters')
        self.library_hint.display(library_text,library_empty)
        project_empty=not any(not w.project_tree.topLevelItem(i).isHidden() for i in range(w.project_tree.topLevelItemCount()))
        self.project_hint.display(w.tr('项目为空\n在素材上右键加入项目，再合成导出','Project is empty\nRight-click an asset to add a project copy') if not w.layers else w.tr('没有匹配的项目文件','No matching project files'),project_empty)
        for key,button in w.tool_buttons.items():
            button.setAccessibleName(button.toolTip())
            button.setEnabled(loaded if key=='mouse' else loaded and not large if key in ('picker','select','wand') else editable)
        for button in w.palette_buttons:button.setAccessibleName(button.toolTip())
        w.canvas_zoom_input.setAccessibleName(w.tr('画板缩放比例','Canvas zoom'));w.canvas_zoom_input.setEnabled(loaded)
        for button,history in zip(w.history_buttons,(c.history,c.future)):
            button.setAccessibleName(button.toolTip());button.setEnabled(bool(history) and loaded and not (c.read_only and history[-1]['pixel_edit']))
        w.recolor_panel.toggle.setEnabled(True)
        from .capabilities import sync_editor
        sync_editor(w)
        w.export_png_action.setEnabled(loaded and bool(w.current) and not large)
        w.undo_batch_action.setEnabled(bool(getattr(w,'batch_recolor_history',[])))
        self.project_undo.setEnabled(bool(w.resource_history))
        for button in self.export_buttons:button.setEnabled(bool(w.layers))
        history=getattr(w,'operation_history',None)
        if history:history.flush();history.sync()


def install(window):window.frontend_flow=FrontendFlow(window)
