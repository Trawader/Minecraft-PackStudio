"""Shared tool creation and palette wiring for every editing surface."""
from PySide6.QtCore import Qt,QSize
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QPushButton,QMenu,QWidgetAction,QWidget,QFormLayout,QSpinBox
from .appearance import tool_icon,ColorSwatch
from .capabilities import TOOLS


def tools(window):
    window.tool_buttons={}
    for key,label in (*TOOLS,('dodge','减淡'),('darken','变暗')):
        button=QPushButton(window);button.setCheckable(True);button.setIcon(tool_icon(key));button.setIconSize(QSize(20,20));button.setFixedSize(30,28)
        button.setToolTip(label);button.setAccessibleName(label)
        button.clicked.connect(lambda checked=False,t=key:window.set_tool(t));window.tool_buttons[key]=button
        if key in ('burn','dodge','lighten','darken'):
            button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            button.customContextMenuRequested.connect(lambda pos,t=key:window.tone_amount(t))
    button=window.tool_buttons['select'];button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    button.customContextMenuRequested.connect(lambda pos:window.rectangle_settings(window.tool_buttons['select'],pos))
    button=window.tool_buttons['wand'];button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    button.customContextMenuRequested.connect(lambda pos:window.wand_settings(window.tool_buttons['wand'],pos))
    window.update_rectangle_tooltip();return window.tool_buttons


def brush_settings(window,button,pos):
    menu=QMenu(window);action=QWidgetAction(menu);body=QWidget();form=QFormLayout(body)
    size=QSpinBox();size.setRange(1,128);size.setValue(window.canvas.brush_size)
    form.addRow(window.tr('粗细（像素）','Size (pixels)'),size)
    alpha=QSpinBox();alpha.setRange(0,255);alpha.setValue(window.canvas.brush_opacity)
    form.addRow(window.tr('不透明度（Alpha）','Opacity (Alpha)'),alpha)
    color=QPushButton(window.tr('颜色','Color'));form.addRow(color)
    size.valueChanged.connect(lambda value:setattr(window.canvas,'brush_size',value))
    def set_alpha(value):
        window.canvas.brush_opacity=value
    def choose():
        window.choose_color()
    alpha.valueChanged.connect(set_alpha);color.clicked.connect(choose)
    action.setDefaultWidget(body);menu.addAction(action);menu.exec(button.mapToGlobal(pos));menu.deleteLater()


def palette(window):
    window.color_button=ColorSwatch(window.canvas.color);window.color_button.hide()
    window.palette_buttons=[];window.active_palette_index=max(0,min(7,int(window.settings.value('palette-v2/active',0))))
    for index,value in enumerate(('#ff5555','#ffaa00','#ffff55','#55cc55','#55dddd','#5555ff','#bb55ff','#ffffff')):
        color=QColor(window.settings.value(f'palette-v2/{index}',value))
        button=ColorSwatch(color if color.isValid() else QColor(value));button.setCheckable(True)
        button.colorSelected.connect(lambda color,i=index:window.activate_palette(i,color))
        button.colorEdited.connect(lambda color,i=index:window.activate_palette(i,color));window.palette_buttons.append(button)
    window.activate_palette(window.active_palette_index,window.palette_buttons[window.active_palette_index].color)
    return window.palette_buttons


def size_settings(window,button,pos,field='eraser_size'):
    menu=QMenu(window);action=QWidgetAction(menu);body=QWidget();form=QFormLayout(body)
    size=QSpinBox();size.setRange(1,128);size.setValue(getattr(window.canvas,field,1))
    form.addRow(window.tr('粗细（像素）','Size (pixels)'),size)
    size.valueChanged.connect(lambda value:setattr(window.canvas,field,value))
    action.setDefaultWidget(body);menu.addAction(action);menu.exec(button.mapToGlobal(pos));menu.deleteLater()
