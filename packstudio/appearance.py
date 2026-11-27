"""Compact editor chrome and editable, persistent colour swatches."""
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter, QPen
from PySide6.QtWidgets import QPushButton, QColorDialog, QHeaderView, QSizePolicy

STYLE = """QWidget { background:#1f1f1f; color:#cccccc; font-family:'Segoe UI','Microsoft YaHei UI'; font-size:12px; }
QToolBar { background:#181818; border:0; border-right:1px solid #303030; spacing:4px; padding:4px; }
QToolButton { background:transparent; border:0; padding:8px; }
QToolButton:checked { background:#313131; border-left:2px solid #007acc; }
QMainWindow, QMenuBar, QStatusBar { background:#181818; }
QMenuBar::item { padding:5px 10px; background:transparent; }
QMenuBar::item:selected, QMenu::item:selected { background:#37373d; }
QMenu { background:#1f1f1f; border:1px solid #454545; padding:4px; }
QMenu::item { padding:5px 28px 5px 12px; background:transparent; }
QDockWidget { border:0; }
QDockWidget::title { background:#181818; padding:3px 7px; border-bottom:1px solid #303030; }
QDockWidget::close-button, QDockWidget::float-button { padding:2px; }
QMainWindow::separator { background:#181818; width:8px; height:8px; }
QMainWindow::separator:hover, QMainWindow::separator:pressed { background:#3c3c3c; }
QSplitter::handle { background:#2b2b2b; width:8px; height:8px; }
QSplitter::handle:hover, QSplitter::handle:pressed { background:#3c3c3c; }
QTabWidget::pane { border:1px solid #454545; background:#1f1f1f; }
QTabBar::tab { background:#252526; color:#cccccc; border:1px solid #303030; padding:6px 10px; }
QTabBar::tab:hover, QTabBar::tab:selected { background:#3c3c3c; color:#cccccc; border-color:#454545; }
QTreeWidget,QListWidget { background:#181818; border:0; outline:0; }
QTreeWidget::item,QListWidget::item { height:23px; padding:0 3px; }
QTreeWidget::item:hover,QListWidget::item:hover { background:#2a2d2e; }
QTreeWidget::item:selected,QListWidget::item:selected { background:#094771; color:#ffffff; }
QLineEdit,QComboBox,QAbstractSpinBox { background:#313131; border:1px solid #454545; border-radius:3px; padding:4px 6px; selection-background-color:#264f78; }
QLineEdit:focus,QComboBox:focus,QAbstractSpinBox:focus { border:1px solid #007acc; }
QAbstractSpinBox QLineEdit {background:transparent;border:0;padding:0;}
QPushButton { background:#2d2d30; border:1px solid #454545; border-radius:3px; padding:4px 7px; }
QPushButton:hover { background:#3c3c3c; }
QPushButton:checked { background:#094771; border:1px solid #007acc; }
QPushButton:disabled { color:#777777; }
QPushButton[canvasTool="true"] { background:#353535; border:1px solid #484848; border-radius:2px; padding:0px; margin:0px; }
QPushButton[canvasTool="true"]:hover { background:#424242; }
QPushButton[canvasTool="true"]:checked { background:#474747; border:1px solid #169bdb; }
QPushButton[canvasTool="true"]:pressed { background:#4b4b4b; }
QToolTip { background:#252526; color:#cccccc; border:1px solid #454545; padding:4px; }
QScrollArea { border:0; }
QScrollBar:vertical { background:transparent; width:10px; margin:0; }
QScrollBar:horizontal { background:transparent; height:10px; margin:0; }
QScrollBar::handle { background:#424242; min-height:24px; min-width:24px; border-radius:4px; }
QScrollBar::handle:hover { background:#666666; }
QScrollBar::add-line,QScrollBar::sub-line { width:0; height:0; }
QScrollBar::add-page,QScrollBar::sub-page { background:transparent; }
QHeaderView::section { background:#181818; border:0; padding:4px; }
"""

class ColorSwatch(QPushButton):
    colorSelected = Signal(QColor)
    colorEdited = Signal(QColor)

    def __init__(self, color, parent=None):
        super().__init__(parent)
        self.setFixedSize(24,24)
        self.set_color(color)
        self.clicked.connect(lambda:self.colorSelected.emit(QColor(self.color)))

    def set_color(self,color):
        self.color=QColor(color)
        if getattr(self,'opaque_only',False):self.color.setAlpha(255)
        self.setToolTip(self.color.name(QColor.NameFormat.HexArgb)+' · 左键使用 / Left: use · 右键调色 / Right: edit')
        self.update()

    def paintEvent(self,event):
        super().paintEvent(event)
        p=QPainter(self)
        for y in range(4,20,4):
            for x in range(4,20,4):
                p.fillRect(x,y,4,4,QColor('#999999' if (x+y)//4%2 else '#dddddd'))
        p.fillRect(4,4,16,16,self.color)

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.RightButton:
            from .color_editor import choose_color
            color=choose_color(self.color,self)
            if color.isValid():
                self.set_color(color);self.colorEdited.emit(QColor(self.color))
            event.accept();return
        super().mousePressEvent(event)

def tool_icon(tool):
    icon=QIcon()
    if tool=='fill':
        for size in (20,30,40,60):
            bitmap=QPixmap(size,size);bitmap.fill(Qt.GlobalColor.transparent)
            painter=QPainter(bitmap);painter.scale(size/20,size/20)
            painter.fillRect(5,5,10,10,QColor('#bbbbbb'))
            painter.setPen(QPen(QColor('#dddddd'),1,Qt.PenStyle.DashLine));painter.drawRect(2,2,15,15);painter.end()
            icon.addPixmap(bitmap)
        return icon
    if tool=='gradient':
        for size in (20,30,40,60):
            bitmap=QPixmap(size,size);bitmap.fill(Qt.GlobalColor.transparent)
            painter=QPainter(bitmap);painter.scale(size/20,size/20)
            for x in range(4,16):
                gray=round(210-(x-4)*165/11);painter.fillRect(x,6,1,9,QColor(gray,gray,gray))
            painter.setPen(QPen(QColor('#bbbbbb'),1));painter.drawRect(3,5,13,10);painter.end()
            icon.addPixmap(bitmap)
        return icon
    sizes=(24,48,72) if tool in ('undo','redo') else (20,30,40,60)
    prefix=tool if tool in ('undo','redo') else 'tool-'+tool
    for size in sizes:
        bitmap=QPixmap(str(Path(__file__).parent/'assets'/f'{prefix}-{size}.png'))
        for mode in (QIcon.Mode.Normal,QIcon.Mode.Active,QIcon.Mode.Selected):
            for state in (QIcon.State.Off,QIcon.State.On):icon.addPixmap(bitmap,mode,state)
    return icon


def compact_tree(tree):
    tree.setMinimumWidth(120)
    tree.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Expanding)
    tree.setIndentation(12);tree.setUniformRowHeights(True);tree.setHeaderHidden(True)
    tree.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
    tree.header().setStretchLastSection(True)
    tree.setTextElideMode(Qt.TextElideMode.ElideMiddle)
