"""Reuse the path index for project browsers, retaining their own editing descriptors."""
from dataclasses import replace
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import QTreeWidgetItem
from .lazy_browser import LibraryIndex, ROLE


class Constant:
    def isChecked(self):return False
    def currentData(self):return 'all'


class ProjectView:
    def __init__(self, window, record):
        self.window=window;self.record=record;self.tree=record['tree'];self.search=record['search']
        self.defaults=Constant();self.vanilla_version=Constant()
        self.library_search_scope=None
    @property
    def sources(self):
        return [replace(layer,uid='stage:'+layer.uid) for layer in self.window.layers
                if not self.record['uid'] or layer.uid==self.record['uid']]
    @property
    def tree_items(self):return self.record['items']
    @tree_items.setter
    def tree_items(self,value):self.record['items']=value
    def __getattr__(self,name):return getattr(self.window,name)
    def restore_library_order(self,parent=None):pass
    def populate_components(self,item,d):
        if d.get('kind') in ('root','folder'):self.record['index'].populate(item)
        else:self.window.expand_browser_item(self.record,item)


class ProjectIndex(LibraryIndex):
    def make(self,origin,path):
        existed=(origin,path) in self.rows
        item=super().make(origin,path)
        if existed:return item
        if not path:
            layer=self.sources[origin]
            item.setFlags((item.flags()|Qt.ItemFlag.ItemIsUserCheckable|Qt.ItemFlag.ItemIsDragEnabled)&~Qt.ItemFlag.ItemIsDropEnabled)
            item.setCheckState(0,Qt.CheckState.Checked if layer.enabled else Qt.CheckState.Unchecked)
            if layer.kind=='component':
                d={'origin':origin,'path':layer.target,'kind':'component','name':layer.name,'regions':layer.regions}
                if layer.bindings:d['bindings']=layer.bindings
                child=QTreeWidgetItem(item,[layer.target]);child.setData(0,ROLE,d)
                child.setFlags(child.flags()&~Qt.ItemFlag.ItemIsDragEnabled&~Qt.ItemFlag.ItemIsDropEnabled)
                self.w.tree_items[self.w.descriptor_key(d)]=child
        else:item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsDragEnabled&~Qt.ItemFlag.ItemIsDropEnabled)
        return item

    def filter(self):
        blocker=QSignalBlocker(self.w.tree)
        super().filter()
        # Component-only project items have no ordinary file paths to search.
        query=self.w.search.text().strip().lower()
        if query:
            for origin,layer in self.sources.items():
                if layer.kind=='component' and query in (layer.name+' '+layer.target).lower():
                    self.make(origin,'').setExpanded(True)
        del blocker


def refresh(window,record):
    selected={key for key,item in record['items'].items() if item.isSelected()}
    blocker=QSignalBlocker(record['tree'])
    if 'index' not in record:record['index']=ProjectIndex(ProjectView(window,record))
    record['index'].refresh()
    for key in selected:
        item=record['items'].get(key)
        if item:item.setSelected(True)
    del blocker
