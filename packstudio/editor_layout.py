"""Compact canvas chrome and bounded, scrollable editing controls."""
from PySide6.QtCore import Qt,QObject,QEvent,QTimer,QSize,QSignalBlocker,QPointF
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QScrollArea,QPushButton,QMenu,QWidgetAction,QSizePolicy,QDoubleSpinBox,QLabel)
from PySide6.QtGui import QImage,QPixmap,QColor,QAction
from .appearance import tool_icon


class ControlSizer(QObject):
    def __init__(self,panel,content,scroll):
        super().__init__(panel);self.panel=panel;self.content=content;self.scroll=scroll;self.pending=False
        panel.installEventFilter(self);content.installEventFilter(self);self.schedule()
    def eventFilter(self,obj,event):
        if event.type() in (QEvent.Type.Resize,QEvent.Type.LayoutRequest,QEvent.Type.Show):self.schedule()
        return False
    def schedule(self):
        if self.pending:return
        self.pending=True;QTimer.singleShot(0,self.adjust)
    def adjust(self):
        self.pending=False
        height=min(max(36,self.content.sizeHint().height()+4),max(64,int(self.panel.height()*.42)))
        if not any(not self.content.layout().itemAt(i).widget().isHidden() for i in range(self.content.layout().count())):height=0
        if self.scroll.height()!=height:self.scroll.setFixedHeight(height)


def add_menu_mark(button):
    image=QImage(4,4,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.transparent)
    for y in range(4):
        for x in range(3-y,4):image.setPixelColor(x,y,QColor('#bbbbbb'))
    mark=QLabel(button);mark.setPixmap(QPixmap.fromImage(image));mark.setFixedSize(4,4)
    mark.setStyleSheet('background:transparent; border:0; padding:0;')
    mark.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
    mark.move(button.width()-7,button.height()-7);mark.show();button.menu_mark=mark


class ToolMenu(QMenu):
    """Native menu rows; right-clicking a row edits that tool's properties."""
    def __init__(self,window):
        super().__init__(window);self.editor_window=window;self.properties={}
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.RightButton:
            action=self.actionAt(event.position().toPoint());mode=self.properties.get(action)
            if mode is not None:
                owner=self.editor_window
                self.close()
                if mode=='eraser':
                    from .editor_controls import size_settings
                    button=owner.tool_buttons['eraser']
                    QTimer.singleShot(0,owner,lambda:size_settings(owner,button,button.rect().bottomRight()))
                else:QTimer.singleShot(0,owner,lambda:owner.run(lambda:owner.tone_amount(mode)))
            event.accept();return
        super().mouseReleaseEvent(event)


def mode_menu(window,button,modes):
    from .localization import text
    menu=ToolMenu(window)
    for mode,label in modes:
        action=menu.addAction(tool_icon(mode),text(label,window.lang))
        action.triggered.connect(lambda checked=False,t=mode:window.set_tool(t))
        if mode in window.canvas.amounts or mode=='eraser':menu.properties[action]=mode
    return menu


def install(window):
    panel=window.docks['editor'].widget();layout=panel.layout();retired=[]
    from PySide6.QtGui import QShortcut
    for shortcut in window.findChildren(QShortcut):
        if shortcut.key().toString() in ("Ctrl+Z","Ctrl+Shift+Z"):
            shortcut.setParent(panel);shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
    def empty(box):
        while box.count():
            item=box.takeAt(0)
            if item.layout():empty(item.layout());item.layout().deleteLater()
            elif item.widget():
                widget=item.widget();widget.hide();widget.setParent(window);retired.append(widget)
    empty(layout)
    # Keep old internal APIs for component/project compatibility, remove their
    # unsafe or redundant canvas buttons from the visible workflow.
    window._retired_editor_widgets=retired
    caption_row=QHBoxLayout();layout.addLayout(caption_row)
    action=QAction('导出当前 PNG…',window);action.triggered.connect(lambda:window.run(window.export_png));window.export_png_action=action
    export_button=QPushButton('导出');export_button.setFixedSize(54,24);export_button.setToolTip('导出当前 PNG')
    export_button.clicked.connect(action.trigger);action.changed.connect(lambda a=action:export_button.setEnabled(a.isEnabled()))
    window.export_png_button=export_button
    caption_row.addWidget(window.caption,1);window.caption.show();window.caption.setWordWrap(True)
    reset_button=QPushButton('重置');reset_button.setFixedSize(54,24);reset_button.setToolTip('重置当前素材')
    reset_button.clicked.connect(lambda:window.run(window.canvas.reset_current))
    caption_row.addWidget(export_button);caption_row.addWidget(reset_button);window.reset_material_button=reset_button
    window.caption.setMaximumHeight(42);window.caption.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
    area=QWidget();layout.addWidget(area,1);row=QHBoxLayout(area);row.setContentsMargins(0,0,0,0);row.setSpacing(5)
    tools=QWidget();column=QVBoxLayout(tools);column.setContentsMargins(0,0,0,0);column.setSpacing(2)
    scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(tools);scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);scroll.setFixedWidth(48);scroll.setMinimumHeight(40)
    row.addWidget(scroll);window.tool_scroll=scroll
    visible=('mouse','pencil','eraser','bucket','picker','select','wand','burn','lighten')
    for key in visible:
        button=window.tool_buttons[key];column.addWidget(button);button.show();button.setText('');button.setFixedSize(30,28);button.setIconSize(QSize(20,20))
        button.setProperty('canvasTool',True)
        button.style().unpolish(button);button.style().polish(button);button.update()
        button.setToolTip({'mouse':'移动','pencil':'画笔','eraser':'橡皮','bucket':'油漆桶','picker':'吸管','select':'矩形选区','wand':'魔棒','burn':'加深','lighten':'变明'}[key])
        if key in ('pencil','eraser','bucket','picker','select','wand','burn','lighten'):add_menu_mark(button)
    from .editor_controls import brush_settings
    pencil=window.tool_buttons['pencil'];pencil.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    pencil.customContextMenuRequested.connect(lambda pos:brush_settings(window,pencil,pos))
    recolor=window.recolor_panel
    recolor.toggle.toggled.disconnect(recolor.show_body)
    gradient=QPushButton();gradient.setCheckable(True);column.addWidget(gradient)
    gradient.setToolTip('渐变');gradient.setAccessibleName('渐变');gradient.setProperty('canvasTool',True)
    gradient.setIcon(tool_icon('gradient'));gradient.setIconSize(QSize(20,20));gradient.setFixedSize(30,28)
    window.gradient_button=gradient
    button=recolor.toggle;button.setParent(tools);column.addWidget(button)
    button.setText('');button.setToolTip('调色');button.setAccessibleName('调色')
    button.setIcon(tool_icon('palette'));button.setIconSize(QSize(20,20));button.setFixedSize(30,28)
    button.setProperty('canvasTool',True);button.show()
    from .recolor_window import RecolorWindow
    window.recolor_window=RecolorWindow(window,recolor)
    button.toggled.connect(window.recolor_window.display)
    gradient.clicked.connect(lambda checked=False:window.set_tool('gradient'))
    gradient.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    def gradient_menu(pos):
        menu=QMenu(window)
        menu.addAction(window.tr('颜色设置','Color settings'),lambda:window.recolor_window.display(True,'gradient','colors'))
        menu.addAction(window.tr('过渡设置','Transition settings'),lambda:window.recolor_window.display(True,'gradient','transition'))
        menu.exec(gradient.mapToGlobal(pos));menu.deleteLater()
    gradient.customContextMenuRequested.connect(gradient_menu)
    recolor.select_tool('recolor')
    from .tool_hints import ToolHint
    window.tool_hints=[ToolHint(b) for b in [*window.tool_buttons.values(),gradient,button]]
    window.canvas.setCursor(Qt.CursorShape.ArrowCursor)
    window.preview.setCursor(Qt.CursorShape.ArrowCursor)
    column.addStretch()
    for primary,modes in [('bucket',[('bucket','油漆桶'),('fill','填充')]),('eraser',[('eraser','橡皮擦'),('magic_eraser','魔术橡皮擦')]),('burn',[('burn','加深'),('dodge','减淡')]),('lighten',[('lighten','变明'),('darken','变暗')])]:
        button=window.tool_buttons[primary];button.group_modes=[mode for mode,_ in modes];button.active_mode=primary
        button.clicked.disconnect();button.clicked.connect(lambda checked=False,b=button:window.set_tool(b.active_mode))
        if primary in ('burn','lighten'):button.customContextMenuRequested.disconnect()
        button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        def show_modes(pos,b=button,m=modes):
            menu=mode_menu(window,b,m);menu.exec(b.mapToGlobal(pos));menu.deleteLater()
        button.customContextMenuRequested.connect(show_modes)
    picker=window.tool_buttons['picker'];picker.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    picker.screen_mode=False
    def activate_picker(screen=False):
        picker.screen_mode=screen;window.set_tool('picker');picker.setIcon(tool_icon('screen_picker' if screen else 'picker'))
        picker.setToolTip(window.tr('屏幕吸色','Screen eyedropper') if screen else window.tr('吸管','Eyedropper'))
        if screen:QTimer.singleShot(0,lambda:window.run(window.screen_pick))
    picker.clicked.disconnect();picker.clicked.connect(lambda checked=False:activate_picker(picker.screen_mode))
    def picker_menu(pos):
        menu=QMenu(window)
        menu.addAction(tool_icon('picker'),window.tr('吸管','Eyedropper'),lambda:activate_picker(False))
        menu.addAction(tool_icon('screen_picker'),window.tr('屏幕吸色','Screen eyedropper'),lambda:activate_picker(True))
        menu.exec(picker.mapToGlobal(pos));menu.deleteLater()
    picker.customContextMenuRequested.connect(picker_menu)
    canvas_area=QWidget();box=QVBoxLayout(canvas_area);box.setContentsMargins(0,0,0,0);box.setSpacing(3);row.addWidget(canvas_area,1)
    header=QHBoxLayout();box.addLayout(header);header.addStretch();palette=QWidget();grid=QGridLayout(palette);grid.setContentsMargins(0,0,0,0);grid.setSpacing(3)
    swatches=window.palette_buttons
    for i,button in enumerate(swatches):grid.addWidget(button,i//4,i%4);button.show()
    header.addWidget(palette);window.canvas_palette=palette
    button_width=(palette.sizeHint().width()-caption_row.spacing())//2
    for button in (export_button,reset_button):button.setFixedWidth(button_width)
    box.addWidget(window.canvas,1);window.canvas.show();window.canvas.setMinimumSize(100,100)
    foot=QHBoxLayout();box.addLayout(foot);foot.addStretch()
    related=window.resource_editors
    foot.insertWidget(0,related.object_title,1,Qt.AlignmentFlag.AlignBottom)
    related.object_title.hide();related.dock.visibilityChanged.connect(related.object_title.setVisible)
    zoom=QDoubleSpinBox();zoom.setRange(10,8000);zoom.setDecimals(1);zoom.setSuffix('%');zoom.setSingleStep(25)
    zoom.setKeyboardTracking(False);zoom.setValue(window.canvas.zoom*100);zoom.setFixedWidth(108);zoom.setToolTip('缩放比例：输入百分比或使用上下按钮，范围 10%–8000%')
    foot.addWidget(zoom);window.canvas_zoom_input=zoom
    def sync_zoom(value):
        with QSignalBlocker(zoom):zoom.setValue(value*100)
    def change_zoom(value):
        if window.canvas.image.isNull():sync_zoom(window.canvas.zoom);return
        window.canvas.set_zoom_at(QPointF(window.canvas.width()/2,window.canvas.height()/2),value/100)
    zoom.valueChanged.connect(change_zoom);window.canvas.zoomChanged.connect(sync_zoom)
    window.history_buttons=[]
    for name,tooltip,callback in [('undo','撤销',window.canvas.undo),('redo','重做',window.canvas.redo)]:
        button=QPushButton();button.setIcon(tool_icon(name));button.setIconSize(QSize(24,24));button.setFixedSize(32,28);button.setToolTip(tooltip);button.clicked.connect(callback);foot.addWidget(button);window.history_buttons.append(button)
    content=QWidget();controls=QVBoxLayout(content);controls.setContentsMargins(0,0,0,0);controls.setSpacing(4)
    # Reparenting must not change which frame/resource strips were visible.
    strips=(window.resource_editors.dock,window.animation_editor)
    for widget in strips:
        controls.addWidget(widget)
    window.animation_editor.hide()
    window.resource_editors.dock.hide()
    scroller=QScrollArea();scroller.setWidgetResizable(True);scroller.setFrameShape(QScrollArea.Shape.NoFrame);scroller.setWidget(content)
    scroller.setMinimumWidth(80);scroller.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
    layout.addWidget(scroller);window.editor_controls_scroll=scroller;window.editor_sizer=ControlSizer(panel,content,scroller)
    icon_widgets=set(window.tool_buttons.values())
    window.labels=[entry for entry in window.labels if entry[0] not in retired and entry[0] not in icon_widgets]
    from .batch_recolor import undo_batch
    action=QAction('撤销上次批量调色',window);action.triggered.connect(lambda:window.run(lambda:undo_batch(window)));window.undo_batch_action=action
    window.set_tool(window.canvas.tool)
