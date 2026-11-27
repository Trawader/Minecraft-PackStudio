"""Exercise actual tool event handlers without opening GUI windows."""
import sys
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QEvent,Qt,QPoint,QRect,QPointF
from PySide6.QtGui import QContextMenuEvent
import packstudio.tool_hints as module
from packstudio.tool_hints import ToolHint
queued=[];opened=[]
original_timer=module.QTimer;original_tip=module.QToolTip
module.QTimer=NS(singleShot=lambda delay,context,fn:queued.append(fn));module.QToolTip=NS(hideText=lambda:None)
button=NS(contextMenuPolicy=lambda:Qt.ContextMenuPolicy.CustomContextMenu,rect=lambda:QRect(0,0,30,28),customContextMenuRequested=NS(emit=lambda p:opened.append(p)))
h=NS(button=button,timer=NS(stop=lambda:None,start=lambda:None));h.open_context=lambda pos:ToolHint.open_context(h,pos)
def event(kind,button=Qt.MouseButton.RightButton,reason=QContextMenuEvent.Reason.Mouse):
    return NS(type=lambda:kind,button=lambda:button,position=lambda:QPointF(8,9),accept=lambda:None,reason=lambda:reason,Reason=QContextMenuEvent.Reason)
try:
    for name in ('brush','eraser','picker','rectangle','wand','burn','lighten','gradient'):
        queued.clear();opened.clear()
        assert ToolHint.eventFilter(h,button,event(QEvent.Type.MouseButtonPress))
        assert not queued
        assert ToolHint.eventFilter(h,button,event(QEvent.Type.MouseButtonRelease))
        assert len(queued)==1 and not opened
        assert ToolHint.eventFilter(h,button,event(QEvent.Type.ContextMenu))
        assert len(queued)==1
        queued.pop()();assert opened==[QPoint(8,9)]
        assert not ToolHint.eventFilter(h,button,event(QEvent.Type.MouseButtonPress,Qt.MouseButton.LeftButton))
    queued.clear()
    assert ToolHint.eventFilter(h,button,event(QEvent.Type.ContextMenu,reason=QContextMenuEvent.Reason.Keyboard))
    assert len(queued)==1
    assert not ToolHint.eventFilter(h,object(),event(QEvent.Type.MouseButtonRelease))
    print('PASS deferred right-release, duplicate suppression, keyboard menu, left-click isolation, target isolation')
finally:module.QTimer=original_timer;module.QToolTip=original_tip
import ast
for path in Path('packstudio').rglob('*.py'):ast.parse(path.read_text('utf-8-sig'))
print('PASS application syntax')
