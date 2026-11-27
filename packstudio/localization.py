"""Display-only localization. Resource IDs, editable text and source bytes stay intact."""
import json
import re
from functools import lru_cache
from pathlib import Path
from PySide6.QtCore import QObject,QEvent,Qt,QSignalBlocker,QSize,QRectF
from PySide6.QtGui import QAction,QActionGroup,QIcon,QPixmap,QPainter,QPen,QColor
from PySide6.QtWidgets import (QApplication,QWidget,QLabel,QAbstractButton,QLineEdit,
    QComboBox,QTabWidget,QTabBar,QDockWidget,QMenu,QToolButton,QAbstractItemView,QStyledItemDelegate,QToolTip,QPlainTextEdit,QStatusBar)

CJK=re.compile('[\u4e00-\u9fff]')

@lru_cache(maxsize=1)
def catalog():
    return json.loads((Path(__file__).parent/'data/ui_en.json').read_text('utf8'))

@lru_cache(maxsize=1)
def game_names():
    from .semantics import translations
    zh,en=translations()
    return {value:en[key] for key,value in zh.items() if key in en}

@lru_cache(maxsize=1)
def fragments():
    names={**game_names(),**catalog()}
    return names,re.compile('|'.join(re.escape(k) for k in sorted(names,key=len,reverse=True) if CJK.search(k)))

@lru_cache(maxsize=16384)
def text(value,language):
    if not value:return value
    # Existing bilingual labels keep their technical suffix, choosing one language.
    if language=='en' and value in catalog():return catalog()[value]
    if ' / ' in value and CJK.search(value.split(' / ',1)[0]):
        left,right=value.split(' / ',1)
        if not CJK.search(right):return left if language=='zh' else right
    if language=='zh' or not CJK.search(value):return value
    if value in catalog():return catalog()[value]
    if value in game_names():return game_names()[value]
    names,pattern=fragments()
    # Paths remain literal even when a pack name or a folder contains Chinese.
    chunks=re.split(r'((?:[A-Za-z]:[\\/]|assets/)[^\n]*?)(?= · |\n|$)',value)
    return ''.join(chunk if i%2 else pattern.sub(lambda m:names[m[0]],chunk) for i,chunk in enumerate(chunks))

def item_text(value,language,descriptor=None):
    d=descriptor if isinstance(descriptor,dict) else {}
    if d.get('kind') in ('root','file','folder') and not d.get('origin','').startswith('@'):
        return value
    if d.get('path') and d.get('kind') in ('png','component'):
        from .naming import overrides,defaults
        from .semantics import identities
        code=identities()[0].get(d['path'],d['path'].split('/textures/')[-1].removesuffix('.png'))
        custom=overrides()[0].get(code)
        if custom and custom['name']!=defaults()['entries'].get(code,{}).get('name'):return value
    if d.get('kind')=='game_object' and language=='en' and '/state/' not in d.get('path',''):
        from .selector_taxonomy import english_name
        return d.get('name_en') or english_name(d.get('object_id',''),d.get('preview_path',''))
    if d.get('kind')=='png' and value.startswith(Path(d.get('path','')).name):
        # File rows keep their literal filenames; semantic names remain in
        # tooltips/search and the object selector, not appended by the delegate.
        return value
    return text(value,language)

class NameDelegate(QStyledItemDelegate):
    def __init__(self,manager,parent):super().__init__(parent);self.manager=manager
    def initStyleOption(self,option,index):
        super().initStyleOption(option,index)
        option.text=item_text(option.text,self.manager.window.lang,index.data(Qt.ItemDataRole.UserRole))

    def helpEvent(self,event,view,option,index):
        tip=index.data(Qt.ItemDataRole.ToolTipRole)
        if tip:
            QToolTip.showText(event.globalPos(),text(tip,self.manager.window.lang),view);return True
        return super().helpEvent(event,view,option,index)

class Localizer(QObject):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.busy=False
        QApplication.instance().installEventFilter(self)
    def owned(self,obj):
        while obj is not None:
            if obj is self.window:return True
            obj=obj.parent()
        return False
    def field(self,obj,key,getter,setter):
        values=getattr(obj,'_locale_values',None)
        if values is None:values={};obj._locale_values=values
        current=getter();saved=values.get(key)
        original=saved[0] if saved and current==saved[1] else current
        # Recover initial English labels when a window was constructed in English.
        if not saved and not CJK.search(current):
            original=next((zh for zh,en in catalog().items() if en==current),original)
        target=text(original,self.window.lang);values[key]=(original,target)
        if current!=target:setter(target)
    def apply(self,obj):
        if isinstance(obj,QWidget):
            self.field(obj,'tip',obj.toolTip,obj.setToolTip)
            self.field(obj,'title',obj.windowTitle,obj.setWindowTitle)
        if isinstance(obj,(QLabel,QAbstractButton,QAction)):
            self.field(obj,'text',obj.text,obj.setText)
        if isinstance(obj,QAction):self.field(obj,'tip',obj.toolTip,obj.setToolTip)
        if isinstance(obj,QStatusBar):self.field(obj,'message',obj.currentMessage,obj.showMessage)
        if isinstance(obj,QPlainTextEdit) and obj.property('localizeSummary'):
            self.field(obj,'summary',obj.toPlainText,obj.setPlainText)
        if isinstance(obj,QLineEdit):self.field(obj,'placeholder',obj.placeholderText,obj.setPlaceholderText)
        if isinstance(obj,QComboBox) and obj is not self.window.language_combo:
            # Never translate editable values, imported source names or raw config paths.
            if obj.isEditable() or obj is getattr(self.window,'selector_source',None):return
            blocker=QSignalBlocker(obj)
            for i in range(obj.count()):self.field(obj,('item',i),lambda i=i:obj.itemText(i),lambda s,i=i:obj.setItemText(i,s))
        if isinstance(obj,(QTabWidget,QTabBar)):
            for i in range(obj.count()):self.field(obj,('tab',i),lambda i=i:obj.tabText(i),lambda s,i=i:obj.setTabText(i,s))
        if isinstance(obj,QAbstractItemView) and not isinstance(obj.itemDelegate(),NameDelegate):
            obj.setItemDelegate(NameDelegate(self,obj))
    def refresh(self):
        if self.busy:return
        self.busy=True
        try:
            for obj in [self.window,*self.window.findChildren(QObject)]:self.apply(obj)
            for view in self.window.findChildren(QAbstractItemView):view.viewport().update()
        finally:self.busy=False
    def eventFilter(self,obj,event):
        if not self.busy and event.type() in (QEvent.Type.Show,QEvent.Type.Paint,QEvent.Type.ActionAdded,QEvent.Type.ActionChanged,QEvent.Type.ToolTip) and self.owned(obj):
            self.busy=True
            try:
                self.apply(obj)
                if isinstance(obj,QMenu):
                    for action in obj.actions():self.apply(action)
            finally:self.busy=False
        return False

def globe_icon():
    icon=QIcon()
    for size in (16,24,32,48):
        icon.addFile(str(Path(__file__).parent/'assets'/f'globe-{size}.png'))
    return icon


def install(window):
    bar=window.menuBar()
    menu=QMenu('',bar);menu.setIcon(globe_icon());menu.setToolTipsVisible(True)
    action=menu.menuAction();action.setObjectName('language-globe');action.setToolTip('语言 / Language')
    # A regular icon-only menu follows Window, so geometry and font/DPI sizing
    # are managed by QMenuBar rather than a far-right corner widget.
    actions_in_bar=bar.actions();position=actions_in_bar.index(window.settings_action)+1
    if position<len(actions_in_bar):bar.insertMenu(actions_in_bar[position],menu)
    else:bar.addMenu(menu)
    group=QActionGroup(menu);group.setExclusive(True);actions=[]
    for index,label in enumerate(('简体中文','English')):
        action=menu.addAction(label);action.setCheckable(True);group.addAction(action)
        action.setChecked(index==(0 if window.lang=='zh' else 1));action.triggered.connect(lambda checked=False,i=index:window.language_changed(i));actions.append(action)
    window.language_menu=menu;window.language_action=menu.menuAction();window.language_actions=actions;window.localizer=Localizer(window);window.localizer.refresh()
