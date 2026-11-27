"""Dockable studio: persistent library, editable project copies and shared views."""
import copy
from .release import APP_TITLE
import logging
import uuid
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QSignalBlocker,QItemSelectionModel
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import (QWidget,QDockWidget,QVBoxLayout,QHBoxLayout,QTreeWidgetItem,
    QLineEdit,QLabel,QMenu,QComboBox,QFileDialog,QMessageBox,QInputDialog,QAbstractItemView,QScrollArea,QStackedWidget)
from .workspace import WorkspaceWindow
from .core import Layer,ROOT,import_pack,identify,decode,png,pixel_rect,components,save_project,load_project,safe_path
from .library import LibraryStore
from .panels import CompositionList,ProjectTree
from shiboken6 import isValid
from .appearance import STYLE,compact_tree
from PySide6.QtWidgets import QToolBar,QStyle,QSplitter,QSizePolicy
from PySide6.QtCore import QSize
from .history_changes import grouped

class StudioWindow(WorkspaceWindow):
    def __init__(self,library_root=None,drafts=True):
        self.studio_ready=False;self.browsers=[];self.docks={};self.library_store=LibraryStore(library_root or ROOT/'library')
        self.drafts_enabled=drafts;self.draft_revision=0;self.draft_saved_revision=-1;self.draft_future=None
        self.draft_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='project-copy') if drafts else None
        self.draft_path=ROOT/'projects'/('Recovery-'+uuid.uuid4().hex[:12]+'.MCPSD')
        super().__init__()
        self.tree.itemSelectionChanged.disconnect();self.tree.assetActivated.connect(lambda d:self.run(lambda:self.edit_descriptor(d)))
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.setDragEnabled(True);self.tree.setAcceptDrops(True);self.tree.setDropIndicatorShown(True)
        self.tree.libraryMoved.connect(lambda d,target:self.run(lambda:self.move_library_asset(d,target)))
        self.tree.selectionCancelled.connect(self.cancel_asset_selection)
        self.library_view_order=json.loads(self.settings.value('library-view-order','{}'))
        self.sources=self.library_store.load()
        order=json.loads(self.settings.value('library-source-order','[]'));self.sources.sort(key=lambda source:order.index(source.uid) if source.uid in order else len(order))
        self.texture_timer=QTimer(self);self.texture_timer.setSingleShot(True);self.texture_timer.timeout.connect(lambda:self.run(self.live_texture))
        self.library_save_timer=QTimer(self);self.library_save_timer.setSingleShot(True)
        self.library_save_timer.timeout.connect(lambda:self.run(self.poll_library_save))
        self.canvas.hovered.connect(self.canvas_hover);self.preview.pixelHovered.connect(self.model_hover)
        self.canvas.strokeUpdated.connect(self.queue_live_texture)
        self.set_tool('mouse')
        self.setup_docks();self.setup_composition_list();self.compact_render_panel();self.setup_panel_controls()
        self.setup_appearance()
        from .dialog_geometry import DialogGeometry
        self.dialog_geometry=DialogGeometry(self)
        from .library_browser import install
        install(self)
        from .naming import install_settings
        install_settings(self)
        from .dock_chrome import settings_panel
        settings_panel(self)
        self.default_dock_state=self.saveState(3)
        self.studio_ready=True;self.refresh()
        from .import_drop import install as install_file_drop
        install_file_drop(self)
        from .resource_editors import install as install_resource_editors
        install_resource_editors(self)
        from .animation_editor import AnimationEditor
        self.animation_editor=AnimationEditor(self)
        from .recolor_panel import RecolorPanel
        self.recolor_panel=RecolorPanel(self)
        from .resource_rules import install as install_resource_rules
        install_resource_rules(self)
        from .editor_layout import install as install_editor_layout
        install_editor_layout(self)
        for dock in (self.resource_rules.dock,self.resource_editors.dock):
            self.window_menu.insertAction(self.reset_workspace_action,dock.toggleViewAction())
        self.default_dock_state=self.saveState(3)
        self.draft_timer=QTimer(self);self.draft_timer.setSingleShot(True);self.draft_timer.timeout.connect(self.save_draft)
        self.draft_poll=QTimer(self);self.draft_poll.setInterval(250);self.draft_poll.timeout.connect(self.check_draft);self.draft_poll.start()
        # The former composition dock no longer exists; start with the unified layout.
        state=self.settings.value('dock-layout-v3')
        if state:self.restoreState(state,3)
        self.resource_rules.dock.hide();self.resource_editors.dock.hide()
        if not self.settings.value('compact-sidebar-v1',False,type=bool):
            self.resizeDocks([self.docks['library'],self.docks['editor'],self.docks['render']],[240,700,350],Qt.Orientation.Horizontal)
            self.settings.setValue('compact-sidebar-v1',True)
        self.labels=[(widget,'提取组件','Extract component',tab) if zh=='提取为顶部组件层' else (widget,zh,en,tab) for widget,zh,en,tab in self.labels]
        from .localization import install as install_language
        install_language(self)
        from .frontend_flow import install as install_frontend_flow
        install_frontend_flow(self)
        from .history_window import History
        self.operation_history=History(self)
        available=self.screen().availableGeometry()
        self.resize(min(self.width(),available.width()-24),min(self.height(),available.height()-60))
        self.statusBar().hide()
        from .dock_chrome import ScreenLayout
        self.screen_layout=ScreenLayout(self)
        self.statusBar().showMessage(self.tr('导入先存入素材库；可直接编辑，或右键加入项目建立独立副本。','Imports enter the library. Edit directly or add an independent copy to the project.'))
    def setup_docks(self):
        # Detach each existing pane exactly once; no reparenting during later interaction.
        self.tabs.currentChanged.disconnect(self.switch_mode)
        library_panel=self.editor_split.widget(0);editor_panel=self.editor_split.widget(1)
        self.right_stack.removeWidget(self.preview_panel)
        scroll=self.right_stack.widget(0)
        if isinstance(scroll,QScrollArea):scroll.takeWidget()
        for panel in (library_panel,editor_panel,self.preview_panel,self.compose_panel):panel.setParent(None)
        old=self.takeCentralWidget();old.hide();self.legacy_container=old
        placeholder=QWidget();placeholder.setMaximumSize(0,0);self.setCentralWidget(placeholder)
        self.setDockNestingEnabled(True)
        self.make_dock('library','素材库','Asset library',library_panel,Qt.DockWidgetArea.LeftDockWidgetArea)
        self.make_dock('editor','画板','Canvas',editor_panel,Qt.DockWidgetArea.RightDockWidgetArea)
        self.splitDockWidget(self.docks['library'],self.docks['editor'],Qt.Orientation.Horizontal)
        project_panel,record=self.create_browser();self.project_tree=record['tree'];self.project_browser=record
        self.project_split=QWidget();project_layout=QVBoxLayout(self.project_split);project_layout.setContentsMargins(0,0,0,0);project_layout.setSpacing(0)
        project_layout.addWidget(project_panel,1)
        self.make_dock('project','合成台','Composition',self.project_split,Qt.DockWidgetArea.LeftDockWidgetArea)
        self.splitDockWidget(self.docks['library'],self.docks['project'],Qt.Orientation.Vertical)
        self.make_dock('render','预览','Preview',self.preview_panel,Qt.DockWidgetArea.RightDockWidgetArea)
        self.splitDockWidget(self.docks['editor'],self.docks['render'],Qt.Orientation.Horizontal)
        self.resizeDocks([self.docks['library'],self.docks['editor'],self.docks['render']],[240,650,390],Qt.Orientation.Horizontal)
        self.resizeDocks([self.docks['library'],self.docks['project']],[240,430],Qt.Orientation.Vertical)
        self.canvas.setMinimumSize(240,180);self.preview.setMinimumSize(200,130)
        self.stack.setMinimumHeight(85)
        # Compact composition controls to keep the two right-hand panels usable.
        self.compose_panel.setStyleSheet('QPushButton {padding:3px 5px;}')
        for widget,zh,en,tab in self.labels:
            if isinstance(widget,QLabel) and (zh.startswith('导入的来源独立保存') or zh.startswith('不作适配：')):
                widget.hide()
            if isinstance(widget,QLabel) and zh.startswith('滚轮缩放'):
                widget.setText(self.tr('素材库中编辑本体；项目中编辑独立副本。左键箭头展开，拖动项目项排序，Delete 删除。','Edit library assets or independent project copies. Expand with arrows, drag project items to reorder, Delete to remove.'))
            if zh=='提取为顶部组件层':
                widget.setText(self.tr('提取组件','Extract component'))
    def setup_appearance(self):
        self.setStyleSheet(STYLE)
        for dock in self.docks.values():
            panel=dock.widget()
            if isinstance(panel,QScrollArea):panel=panel.widget()
            if panel.layout():panel.layout().setContentsMargins(7,7,7,7);panel.layout().setSpacing(6)
        compact_tree(self.tree)
        self.search.setPlaceholderText(self.tr('搜索素材库：名称、路径、小部件','Search library: name, path, component'))
        self.search.setClearButtonEnabled(True);self.search.setMinimumWidth(100)
        self.defaults.setToolTip(self.defaults.text())
        self.docks['library'].setMinimumWidth(160);self.docks['project'].setMinimumWidth(160)
    def focus_library_search(self):
        self.docks['library'].show();self.docks['library'].raise_();self.search.setFocus();self.search.selectAll()
    def make_dock(self,key,zh,en,panel,area):
        dock=QDockWidget(self.tr(zh,en),self);dock.setObjectName('studio-'+key)
        from .dock_chrome import configure
        configure(dock)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable|QDockWidget.DockWidgetFeature.DockWidgetFloatable|QDockWidget.DockWidgetFeature.DockWidgetClosable)
        if key=='render':
            scroll=QScrollArea();scroll.setFrameShape(QScrollArea.Shape.NoFrame);scroll.setWidgetResizable(True);scroll.setWidget(panel);dock.setWidget(scroll)
        else:dock.setWidget(panel)
        self.addDockWidget(area,dock);self.docks[key]=dock;return dock
    def setup_panel_controls(self):
        menu=self.menuBar().addMenu(self.tr('窗口','Window'))
        self.menuBar().removeAction(menu.menuAction());self.menuBar().insertAction(self.settings_action,menu.menuAction())
        self.window_menu=menu
        for dock in self.docks.values():menu.addAction(dock.toggleViewAction())
        action=menu.addAction(self.tr('恢复默认工作区','Reset workspace'));action.triggered.connect(lambda:self.run(self.reset_layout))
        self.reset_workspace_action=action
    def reset_layout(self):
        self.restoreState(self.default_dock_state,3)
        if hasattr(self,'resource_editors'):self.resource_editors.dock.hide()
        for dock in self.docks.values():dock.setFloating(False);dock.show()
        from .dock_chrome import default_layout
        default_layout(self)
    def compact_render_panel(self):
        old=self.preview_panel;panel=QWidget();box=QVBoxLayout(panel);box.setSpacing(4)
        row=QHBoxLayout();box.addLayout(row);row.addWidget(self.preview_category);row.addWidget(self.preview_group)
        row=QHBoxLayout();box.addLayout(row);row.addWidget(self.preview_model);row.addWidget(self.texture_binding)
        row=QHBoxLayout();box.addLayout(row);row.addWidget(self.model_id)
        self.button(row,'查找','Find',self.find_model_id);self.button(row,'自动','Auto',self.auto_model)
        self.model_info.setMaximumHeight(50);box.addWidget(self.model_info);box.addWidget(self.preview,1)
        self.preview.setMinimumSize(180,130);panel.setStyleSheet('QPushButton {padding:3px 5px;}')
        scroll=self.docks['render'].widget();scroll.takeWidget();old.setParent(self.legacy_container);old.hide()
        self.preview_stack=QStackedWidget();self.preview_stack.addWidget(panel);scroll.setWidget(self.preview_stack);self.preview_panel=panel
    def set_preview_page(self,page):
        self.preview_stack.setCurrentWidget(page)
        self.docks['render'].setWindowTitle(self.tr('预览','Preview'))
    def switch_mode(self,index):
        if not self.studio_ready:return super().switch_mode(index)
        key='project' if index==1 else 'render';self.docks[key].show();self.docks[key].raise_()
    def toggle_preview(self,enabled):
        if not self.studio_ready:return super().toggle_preview(enabled)
        self.docks['render'].setVisible(enabled);self.settings.setValue('preview',enabled)
    def setup_composition_list(self):
        old=self.stack;self.stack=CompositionList(self.legacy_container);old.hide();self.stack.hide()
        old_panel=self.compose_panel;compact=QWidget();box=QVBoxLayout(compact);box.setSpacing(4);box.setContentsMargins(0,0,0,0)
        self.version.setParent(self.legacy_container);self.description.setParent(self.legacy_container)
        self.version.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.version.setMinimumContentsLength(12);self.version.setMinimumWidth(0)
        self.version.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.button(box,'导出','Export',self.export)
        old_panel.setParent(self.legacy_container);old_panel.hide()
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setMinimumHeight(46);scroll.setMaximumHeight(60);scroll.setWidget(compact)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame);self.project_split.layout().addWidget(scroll);self.compose_panel=compact
        compact.setStyleSheet('QPushButton {padding:3px 5px;}')
        self.stack.itemChanged.connect(self.toggle_layer)
        self.stack.itemDoubleClicked.connect(lambda item:self.queue_open_layer(item.data(Qt.ItemDataRole.UserRole)))
        self.stack.orderChanged.connect(lambda ids:QTimer.singleShot(0,lambda:self.run(lambda:self.apply_order(ids))))
        self.stack.deleteRequested.connect(self.queue_remove_layers)
        self.stack.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.stack.customContextMenuRequested.connect(self.show_stack_menu)
    def select_project_roots(self):
        if self.refreshing or not self.studio_ready:return
        ids={item.data(Qt.ItemDataRole.UserRole) for item in self.stack.selectedItems()}
        tree=self.project_tree;blocker=QSignalBlocker(tree);tree.clearSelection()
        for index in range(tree.topLevelItemCount()):
            item=tree.topLevelItem(index);d=item.data(0,Qt.ItemDataRole.UserRole)
            item.setSelected(d['origin'][6:] in ids)
        del blocker
    def apply_order(self,ids):
        if self.refreshing:return
        by_id={l.uid:l for l in self.layers}
        if len(ids)!=len(by_id) or set(ids)!=set(by_id):self.refresh();return
        if ids==[l.uid for l in self.layers]:return
        self.remember();self.layers=[by_id[uid] for uid in ids];self.changed();self.refresh()
    def queue_remove_layers(self,ids):
        stable=tuple(ids);self.selection_timer.stop();self.pending_resource=None
        QTimer.singleShot(0,lambda:self.run(lambda:self.remove_layers(stable)))
    def remove_layer(self):self.queue_remove_layers([i.data(Qt.ItemDataRole.UserRole) for i in self.stack.selectedItems()])
    def remove_layers(self,ids):
        ids=set(ids)&{l.uid for l in self.layers}
        if not ids:return
        self.remember();self.cancel_edit_for(ids)
        # Unbind all live views BEFORE removing data or destroying item wrappers.
        for record in list(self.browsers):
            if record['uid'] in ids:self.close_browser(record)
        self.layers=[l for l in self.layers if l.uid not in ids]
        self.changed();self.refresh()
    def merge_selected(self):
        ids={i.data(Qt.ItemDataRole.UserRole) for i in self.stack.selectedItems()}
        refs=sorted({ref for layer in self.layers if layer.uid in ids for ref in self.layer_refs(layer)})
        if len(ids)>=2:
            self.cancel_edit_for(ids)
            for record in list(self.browsers):
                if record['uid'] in ids:self.close_browser(record)
        super().merge_selected()
        merged=self.layers[self.stack.currentRow()];merged.library_refs=refs
    def layer_refs(self,layer):
        return set(layer.library_refs)|({layer.library_uid} if layer.library_uid else set())
    def cancel_edit_for(self,ids):
        audio=getattr(self,'audio_preview',None)
        if audio and audio.descriptor and audio.descriptor['origin'].removeprefix('stage:') in ids:
            audio.stop();self.set_preview_page(self.preview_panel)
        self.selection_timer.stop();self.pending_resource=None
        if hasattr(self,'texture_timer'):self.texture_timer.stop()
        if self.current_source and self.current_source.startswith('stage:') and self.current_source[6:] in ids:self.clear_editor()
    def clear_editor(self):
        history=getattr(self,'operation_history',None)
        if history:history.clear_preview()
        self.edit_bindings=None;self.canvas.read_only=False
        if hasattr(self,'texture_timer'):self.texture_timer.stop()
        super().clear_editor()
        self.preview.image=None;self.preview.hit_faces=[];self.preview.set_highlight(None)
        self.model_library.files={};self.model_library.signature=None;self.model_library.cache.clear()
    def queue_open_layer(self,uid,new=False):QTimer.singleShot(0,lambda:self.run(lambda:self.browse_layer(uid,new)))
    def open_layer(self):
        selected=self.stack.selectedItems();item=selected[0] if selected else None
        if item:self.queue_open_layer(item.data(Qt.ItemDataRole.UserRole))
    def browse_layer(self,uid,new=False):
        if self.source('stage:'+uid) is None:return
        if new:
            panel,record=self.create_browser(uid);dock=QDockWidget(self.tr('项目文件视图','Project file view'),self)
            from .dock_chrome import configure,fit_floating
            configure(dock)
            dock.setWidget(panel);dock.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose,False);record['dock']=dock
            self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,dock);dock.setFloating(True);dock.resize(480,640);fit_floating(dock);dock.show()
            self.window_menu.addAction(dock.toggleViewAction())
            self.populate_browser(record)
        else:
            record=self.project_browser;self.docks['project'].show();self.docks['project'].raise_()
        origin='stage:'+uid
        root=next((item for key,item in record['items'].items() if key[0]==origin and key[1]=='root'),None)
        if root:root.setExpanded(True);record['tree'].setCurrentItem(root,0,QItemSelectionModel.SelectionFlag.NoUpdate);record['tree'].scrollToItem(root)
    def show_stack_menu(self,pos):
        menu=QMenu(self);item=self.stack.itemAt(pos)
        uid=item.data(Qt.ItemDataRole.UserRole) if item else None
        ids=tuple(i.data(Qt.ItemDataRole.UserRole) for i in self.stack.selectedItems())
        if uid and uid not in ids:ids=(uid,)
        for zh,en,fn in [('打开文件夹','Browse files',lambda:self.queue_open_layer(uid)),('在新窗口打开','Open another view',lambda:self.queue_open_layer(uid,True)),('移除','Remove',lambda:self.queue_remove_layers(ids)),('合并选中项','Merge selected',self.merge_selected)]:
            action=menu.addAction(self.tr(zh,en));action.setEnabled(bool(uid));action.triggered.connect(lambda checked=False,f=fn:self.run(f))
        menu.aboutToHide.connect(menu.deleteLater);self.context_popup=menu;menu.popup(self.stack.viewport().mapToGlobal(pos))
    def create_browser(self,uid=None):
        panel=QWidget();layout=QVBoxLayout(panel);search=QLineEdit();search.setPlaceholderText(self.tr('搜索项目文件','Search project files'));layout.addWidget(search)
        layout.setContentsMargins(0,0,0,0);layout.setSpacing(6)
        tree=ProjectTree();tree.setHeaderLabels([self.tr('项目内副本','Project copies')]);tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);layout.addWidget(tree)
        compact_tree(tree);search.setClearButtonEnabled(True)
        tree.setExpandsOnDoubleClick(False)
        record={'uid':uid,'tree':tree,'search':search,'items':{},'dock':None};self.browsers.append(record)
        tree.itemSelectionChanged.connect(lambda:self.queue_browser_selection(record))
        tree.assetActivated.connect(lambda d:self.run(lambda:self.edit_descriptor(d)))
        tree.assetDropped.connect(lambda d:QTimer.singleShot(0,lambda:self.run(lambda:self.add_to_composition(d))))
        tree.selectionCancelled.connect(self.cancel_asset_selection)
        tree.customContextMenuRequested.connect(lambda pos:self.browser_menu(record,pos))
        tree.itemExpanded.connect(lambda item:self.run(lambda:self.expand_browser_item(record,item)))
        tree.deleteRequested.connect(lambda ds:QTimer.singleShot(0,lambda:self.run(lambda:self.delete_descriptors(ds))))
        tree.orderChanged.connect(lambda ids:QTimer.singleShot(0,lambda:self.run(lambda:self.apply_order(ids))))
        tree.itemChanged.connect(lambda item,column:self.project_item_changed(item))
        search.textChanged.connect(lambda:self.filter_browser(record));return panel,record
    def close_browser(self,record):
        tree=record['tree'];blocker=QSignalBlocker(tree);tree.clear();record['items']={};del blocker
        tree.setEnabled(False)
        if record['dock']:
            dock=record['dock'];dock.hide();self.removeDockWidget(dock);dock.deleteLater()
        self.browsers.remove(record)
    def populate_browser(self,record):
        from .lazy_project import refresh
        refresh(self,record)
    def project_item_changed(self,item):
        if self.refreshing:return
        d=item.data(0,Qt.ItemDataRole.UserRole) or {}
        if d.get('kind')!='root':return
        layer=self.source(d['origin'])
        if layer:
            layer.enabled=item.checkState(0)==Qt.CheckState.Checked;self.changed()
    def expand_browser_item(self,record,item):
        d=item.data(0,Qt.ItemDataRole.UserRole) or {}
        if 'index' in record and d.get('kind') in ('root','folder'):
            record['index'].populate(item);return
        if d.get('kind')!='png' or item.childCount():return
        for name,regions in self.component_rules(d):
            child=QTreeWidgetItem([name]);data={**d,'kind':'component','name':name,'regions':regions};child.setData(0,Qt.ItemDataRole.UserRole,data);item.addChild(child);record['items'][self.descriptor_key(data)]=child
    def filter_browser(self,record):
        if 'index' in record:
            blocker=QSignalBlocker(record['tree']);record['index'].filter();del blocker;return
        tree=record['tree'];blocker=QSignalBlocker(tree);query=record['search'].text().lower()
        def visit(item,ancestor=False):
            d=item.data(0,Qt.ItemDataRole.UserRole) or {};match=ancestor or not query or query in d.get('path','').lower() or query in item.text(0).lower()
            children=[visit(item.child(i),match) for i in range(item.childCount())];visible=match or any(children);item.setHidden(not visible)
            if query and any(children):item.setExpanded(True)
            return visible
        for i in range(tree.topLevelItemCount()):visit(tree.topLevelItem(i))
        del blocker
    def queue_browser_selection(self,record):
        if self.refreshing:return
        if record is self.project_browser:
            ids={(item.data(0,Qt.ItemDataRole.UserRole) or {}).get('origin','')[6:] for item in record['tree'].selectedItems()}
            blocker=QSignalBlocker(self.stack)
            for index in range(self.stack.count()):
                entry=self.stack.item(index);entry.setSelected(entry.data(Qt.ItemDataRole.UserRole) in ids)
            del blocker
        item=record['tree'].currentItem();d=item.data(0,Qt.ItemDataRole.UserRole) if item else None
        self.selection_timer.stop();self.pending_resource=None
    def browser_menu(self,record,pos):
        self.selection_timer.stop();self.pending_resource=None;item=record['tree'].itemAt(pos)
        if item:
            d=copy.deepcopy(item.data(0,Qt.ItemDataRole.UserRole));self.context_popup=self.resource_menu(d)
            selected=[copy.deepcopy(i.data(0,Qt.ItemDataRole.UserRole)) for i in record['tree'].selectedItems()] if item.isSelected() else [d]
            action=self.context_popup.actions()[1];action.triggered.disconnect()
            action.triggered.connect(lambda:QTimer.singleShot(0,lambda:self.run(lambda:self.delete_descriptors(selected))))
            self.context_popup.popup(record['tree'].viewport().mapToGlobal(pos))
    def refresh(self,*args):
        if hasattr(self,'library_mode') and self.library_mode.currentIndex()==1:
            from .library_browser import expansion_paths
            self.friendly_expansion=expansion_paths(self.tree)
        self.tree_items={key:item for key,item in self.tree_items.items() if isValid(item)}
        selected={key for key,item in self.tree_items.items() if item.isSelected()}
        super().refresh(*args)
        blocker=QSignalBlocker(self.tree)
        if hasattr(self,'library_mode'):
            from .library_browser import decorate
            decorate(self);self.filter_tree()
        del blocker
        blocker=QSignalBlocker(self.tree);self.tree.clearSelection()
        for key in selected:
            if key in self.tree_items:self.tree_items[key].setSelected(True)
        del blocker
        if hasattr(self,'library_view_order'):self.restore_library_order()
        if not self.studio_ready:return
        self.refreshing=True
        try:
            for record in list(self.browsers):self.populate_browser(record)
        finally:self.refreshing=False
        if hasattr(self,'resource_editors'):self.resource_editors.sync()
        if hasattr(self,'resource_rules'):self.resource_rules.refresh()
    def cancel_asset_selection(self):
        self.library_search_scope=None
        self.selected_asset=None;self.selected_asset_key=None
        self.tree.clearSelection()
        for record in self.browsers:record['tree'].clearSelection()
        self.filter_tree()
    def library_order_key(self,item):
        return repr(self.descriptor_key(item.data(0,Qt.ItemDataRole.UserRole))) if item and item.data(0,Qt.ItemDataRole.UserRole) else '@root'
    def move_library_asset(self,d,target):
        item=self.tree_items.get(self.descriptor_key(d))
        dest=self.tree_items.get(self.descriptor_key(target)) if target else None
        if not item:return
        if d['kind']=='root':
            while dest and dest.parent():dest=dest.parent()
        parent=item.parent() or self.tree.invisibleRootItem()
        if dest and (dest.parent() or self.tree.invisibleRootItem()) is not parent:
            self.statusBar().showMessage(self.tr('仅调整同级显示顺序，不改变资源路径。','Reorder siblings only; resource paths stay unchanged.'));return
        if dest is item:return
        blocker=QSignalBlocker(self.tree)
        parent.takeChild(parent.indexOfChild(item));index=parent.indexOfChild(dest) if dest else parent.childCount();parent.insertChild(index,item)
        self.library_view_order[self.library_order_key(parent)]=[self.library_order_key(parent.child(i)) for i in range(parent.childCount())]
        self.settings.setValue('library-view-order',json.dumps(self.library_view_order))
        if d['kind']=='root':
            ids=[self.tree.topLevelItem(i).data(0,Qt.ItemDataRole.UserRole)['origin'] for i in range(self.tree.topLevelItemCount())]
            self.sources.sort(key=lambda source:ids.index(source.uid) if source.uid in ids else len(ids));self.settings.setValue('library-source-order',json.dumps(ids))
        del blocker
    def restore_library_order(self,parent=None):
        blocker=QSignalBlocker(self.tree)
        parents=[parent] if parent is not None else [self.tree.invisibleRootItem()]+[item for item in self.tree_items.values() if isValid(item) and item.childCount()]
        for parent in parents:
            order=self.library_view_order.get(self.library_order_key(parent))
            if not order:continue
            children=[parent.child(i) for i in range(parent.childCount())]
            ranks={key:index for index,key in enumerate(order)}
            arranged=sorted(children,key=lambda item:ranks.get(self.library_order_key(item),len(order)))
            if all(a is b for a,b in zip(children,arranged)):continue
            expanded=[];todo=list(children)
            while todo:
                node=todo.pop()
                if node.isExpanded():expanded.append(node)
                todo.extend(node.child(i) for i in range(node.childCount()))
            parent_expanded=parent.isExpanded()
            parent.takeChildren();parent.addChildren(arranged)
            parent.setExpanded(parent_expanded)
            for node in expanded:node.setExpanded(True)
        del blocker
    def library_copy_to_project(self,source,reuse=False):
        if reuse:
            existing=next((l for l in self.layers if l.library_uid==source.uid),None)
            if existing:return existing
        layer=self.clone_layer(source);layer.uid=uuid.uuid4().hex;layer.library_uid=source.uid;layer.enabled=True
        layer.name=source.name+' (from '+self.origin_label(source)+')';self.layers.insert(0,layer);return layer
    @grouped('导入素材')
    def add_import(self,source):
        # Persist a library copy; originals are never opened for writing.
        if source.kind!='component' and 'pack.mcmeta' not in source.files:
            unknown=[p for p in source.files if p.lower().endswith('.png') and not p.startswith('assets/')]
            if unknown:source.selection['unmapped_paths']=sorted(set(source.selection.get('unmapped_paths',[]))|set(unknown))
        from .layouts import tag_import
        tag_import(source,self.working_version)
        self.library_store.put(source);self.sources.append(source)
        if not getattr(self,'_batch_import',False):self.refresh()
        self.statusBar().showMessage(self.tr('已导入素材库（未加入项目）：','Imported to library (not added to project): ')+source.name)
    def add_pack(self,path):
        from .task_progress import run_progress
        try:source=run_progress(self,"正在导入材质包",lambda cancel,progress:import_pack(path,cancel,progress))
        except InterruptedError:return
        fmt,_=identify(source,self.vanilla);source.format_hint=fmt if isinstance(fmt,(int,float)) else None;self.add_import(source)
    def add_png(self):
        path,_=QFileDialog.getOpenFileName(self,'PNG','','PNG (*.png)')
        if not path:return
        target,ok=QInputDialog.getText(self,self.tr('资源路径（可留空）','Resource path (optional)'),
            '已知目标可填写 assets/命名空间/目录/文件.png；留空可先导入，合成导出时再指定。',text='')
        if not ok:return
        target=target.strip()
        if target:
            from .export_targets import valid_target
            target=valid_target(target,Path(path).name)
        else:target=safe_path(Path(path).name)
        data=Path(path).read_bytes()
        from .sky_view import oversized,thumbnail
        thumbnail(data) if oversized(data) else decode(data)
        files={target:data}
        metadata=Path(path+'.mcmeta')
        if metadata.is_file():files[target+'.mcmeta']=metadata.read_bytes()
        self.add_import(Layer(Path(path).stem,files,kind='png',source=str(Path(path).resolve())))
    def edit_descriptor(self,d):
        history=getattr(self,'operation_history',None)
        if history:history.clear_preview()
        from .edit_confirmation import large_image
        if not large_image(self,d):return
        if hasattr(self,'recolor_panel'):self.recolor_panel.reset()
        if hasattr(self,'animation_editor'):self.animation_editor.reset()
        d=copy.deepcopy(d)
        from .sounds import is_audio
        if is_audio(d.get('path','')):
            self.resource_editors.show_resources(d)
            self.library_store.flush()
            from .audio_preview import open_sound
            open_sound(self,d);return
        if hasattr(self,'audio_preview'):
            self.audio_preview.stop();self.set_preview_page(self.preview_panel)
        if d.get('kind') in ('png','component'):
            key=(d.get('origin'),d.get('path'),repr(d.get('regions')),repr(d.get('bindings')))
            if key!=getattr(self,'_canvas_selection_key',None):self.canvas.clear_selection()
            self._canvas_selection_key=key
        if d.get('kind')=='game_object':
            if self.source(d['origin']) is None:raise ValueError('来源材质包已移除')
            self.resource_editors.select_object(d)
            paths=self.resource_editors.paths
            if not paths:return
            path=d.get('preview_path')
            if path not in paths:path=paths[0]
            self.edit_descriptor({'kind':'png','origin':d['origin'],'path':path,'name':Path(path).name,'_object_context':d})
            return
        from .sky_view import set_locked,open_view
        if getattr(self,'large_view_only',False) and d.get('kind') in ('png','component'):self.clear_editor()
        self.selector_context=d.get('_object_context')
        if open_view(self,d):return
        if hasattr(self,'resource_rules'):self.resource_rules.inspect(d)
        if d.get('kind')=='resource_group':
            item=self.tree_items.get(self.descriptor_key(d))
            if item:item.setExpanded(True)
            return
        if self.current_source and (self.current_source!=d.get('origin') or self.current and self.current[0]!=d.get('path')):
            self.library_store.flush()
        if d['origin'].startswith('stage:') and d['kind'] in ('root','folder'):
            for record in self.browsers:
                item=record['items'].get(self.descriptor_key(d))
                if item:item.setExpanded(True)
            return
        if hasattr(self,'texture_timer'):self.texture_timer.stop()
        super().edit_descriptor(d)
        if self.selector_context:self.auto_model()
        self.canvas.read_only=self.is_builtin(d)
        if d['kind'] in ('png','component'):
            prefix=self.tr('原版只读 · 加入项目后编辑 · ','Vanilla read-only · Add to project to edit · ') if self.is_builtin(d) else self.tr('项目副本 · ','Project copy · ') if d['origin'].startswith('stage:') else self.tr('素材库本体 · ','Library asset · ')
            if not self.caption.text().startswith(prefix):self.caption.setText(prefix+self.caption.text())
        if hasattr(self,'resource_editors'):self.resource_editors.show_resources(d)
        if hasattr(self,'animation_editor'):self.animation_editor.open(d)
    def clear_editor(self):
        history=getattr(self,'operation_history',None)
        if history:history.clear_preview()
        if hasattr(self,'recolor_panel'):self.recolor_panel.reset()
        if hasattr(self,'animation_editor'):self.animation_editor.reset()
        if hasattr(self,'audio_preview'):
            self.audio_preview.stop();self.set_preview_page(self.preview_panel)
        self.selector_context=None;self.sky_edit_key=None
        self.library_store.flush()
        if getattr(self,'large_view_only',False):
            from .sky_view import set_locked
            set_locked(self,False)
        super().clear_editor()
    def load_canvas(self):
        super().load_canvas()
        panel=getattr(self,'animation_editor',None)
        if panel and panel.descriptor and self.current and (self.current_source,self.current[0])==(panel.descriptor['origin'],panel.descriptor['path']):
            panel.pick(panel.cards.currentRow())
    def export(self):
        if not self.layers:raise ValueError(self.tr('项目为空，请从素材库右键加入项目。','Project is empty. Add assets from the library first.'))
        from .export_dialog import ExportDialog
        dialog=ExportDialog(self);self.export_dialog=dialog
        try:dialog.exec()
        finally:
            if self.export_dialog is dialog:self.export_dialog=None
            dialog.deleteLater()
    def commit_canvas(self):
        self.canvas.timeline_committing=True
        try:return self._commit_canvas_impl()
        finally:self.canvas.timeline_committing=False
    def _commit_canvas_impl(self):
        if getattr(self,'large_view_only',False):return
        if self.is_builtin({'origin':self.current_source or ''}):return
        dirty=self.dirty;new_library=False
        if self.current and self.source(self.current_source) is None:
            from .library_browser import builtin_version
            layer=Layer(self.tr('原版编辑副本','Vanilla edit copy'),source_version=builtin_version(self))
            if self.current[1]:
                data=self.vanilla.get(builtin_version(self),self.current[0])
                if data:layer.files[self.current[0]]=data
            self.sources.append(layer);self.current_source=layer.uid;new_library=True
        super().commit_canvas()
        if self.current_source and not self.current_source.startswith('stage:'):
            owner=self.source(self.current_source)
            if owner:
                self.library_store.queue(owner);self.library_save_timer.start(400)
            self.dirty=dirty;self.setWindowModified(dirty)
            if new_library:self.refresh()
        if hasattr(self,'resource_editors'):self.resource_editors.sync()
    def poll_library_save(self):
        if self.library_store.start():self.library_save_timer.start(50)
    def add_to_composition(self,d):
        from .library_browser import confirm_resolution,builtin_version
        if not confirm_resolution(self,d):return
        owner=self.source(d['origin'])
        if owner is None:
            asset=self.snapshot(d)
            if asset['kind']=='component':
                paths=[b['path'] for b in d['bindings']] if d.get('bindings') else [d['path']]
                owner=Layer(asset['name'],{p:self.vanilla.get(builtin_version(self,d['origin']),p) for p in paths},source_version=builtin_version(self,d['origin']))
            else:owner=Layer(asset['name'],asset['files'],asset['kind'],source_version=builtin_version(self,d['origin']))
            owner.read_only=True
            self.add_import(owner);d={**d,'origin':owner.uid}
        before={layer.uid for layer in self.layers}
        super().add_to_composition(d)
        layer=next(layer for layer in self.layers if layer.uid not in before)
        refs=self.layer_refs(owner) if d['origin'].startswith('stage:') else {owner.uid}
        layer.library_refs=sorted(refs);layer.library_uid=next(iter(refs)) if len(refs)==1 else ''
        if '_insert_index' in d:
            self.layers.remove(layer);self.layers.insert(max(0,min(d['_insert_index'],len(self.layers))),layer);self.refresh()
        from .resource_history import seal
        seal(self,finalize=True)
        self.switch_mode(1);self.browse_layer(layer.uid)
    def extract(self):
        if getattr(self,'large_view_only',False):return
        if self.is_builtin({'origin':self.current_source or ''}):
            self.statusBar().showMessage('原版只读，请先加入项目后编辑副本。');return
        owner=self.source(self.current_source);before={layer.uid for layer in self.layers}
        library_edit=not (self.current_source or '').startswith('stage:');dirty=self.dirty
        super().extract()
        for layer in list(self.layers):
            if layer.uid not in before:
                if library_edit:
                    self.layers.remove(layer);self.library_store.put(layer);self.sources.append(layer);continue
                refs=self.layer_refs(owner) if owner and self.current_source.startswith('stage:') else {owner.uid} if owner else set()
                if not refs:
                    source=self.clone_layer(layer);source.uid=uuid.uuid4().hex;self.library_store.put(source);self.sources.append(source);refs={source.uid}
                layer.library_refs=sorted(refs)
        if library_edit:self.dirty=dirty;self.setWindowModified(dirty)
        self.refresh()
    @grouped('删除素材及关联项目内容')
    def delete_descriptors(self,descriptors):
        descriptors=[d for d in descriptors if d]
        minimal=[d for d in descriptors if not any(a is not d and a['origin']==d['origin'] and a['kind'] in ('root','folder') and (not a['path'] or d['path'].startswith(a['path']+'/')) for a in descriptors)]
        for d in minimal:
            if d:self.delete_resource(d)
    @grouped('删除素材及关联项目内容')
    def delete_resource(self,d):
        if self.is_builtin(d) and d.get('kind')!='root':return
        if d.get('bindings') and not d['origin'].startswith('stage:'):
            for binding in d['bindings']:
                self.delete_resource({**d,'bindings':[],'path':binding['path'],'regions':[binding['region']]})
            return
        if not d['origin'].startswith('stage:'):
            owner=self.source(d['origin'])
            if owner is None:return
            path=d['path']
            matches=lambda p:d['kind']=='root' or p==path or (d['kind']=='folder' and p.startswith(path+'/'))
            affected=[layer for layer in self.layers if owner.uid in self.layer_refs(layer) and (d['kind']=='root' or matches(layer.target) or any(matches(p) for p in layer.files) or any(matches(b['path']) for b in layer.bindings))]
            if affected:
                names='\n'.join(layer.name for layer in affected)
                message=self.tr(f'此素材在当前项目中有 {len(affected)} 个副本引用：\n{names}\n\n移除素材会导致这些副本中的对应内容丢失；对副本的独立编辑也会随对应内容移除。是否继续？',f'This asset is referenced by {len(affected)} project copies:\n{names}\n\nRemoving it also removes the corresponding project content, including its independent edits. Continue?')
                if QMessageBox.warning(self,self.tr('删除素材及项目引用','Remove asset and project references'),message,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Yes:return
            self.clear_editor()
            ids={layer.uid for layer in affected}
            for record in list(self.browsers):
                if record['uid'] in ids:self.close_browser(record)
            if d['kind']=='root':
                self.library_store.remove(owner.uid);self.sources=[source for source in self.sources if source.uid!=owner.uid]
                self.layers=[layer for layer in self.layers if layer.uid not in ids]
            else:
                super().delete_resource(d);self.library_store.put(owner)
                for layer in affected:
                    if layer.bindings:
                        kept=[(b,layer.files[str(i)]) for i,b in enumerate(layer.bindings) if not matches(b['path'])]
                        layer.bindings=[b for b,raw in kept];layer.regions=[b['region'] for b,raw in kept];layer.files={str(i):raw for i,(b,raw) in enumerate(kept)}
                        if kept:layer.target=kept[0][0]['path']
                    elif layer.kind=='component':layer.files={}
                    elif d['kind']=='component' and path in layer.files:
                        image=decode(layer.files[path]);p=QPainter(image);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                        for region in d['regions']:p.fillRect(*pixel_rect(region,image),Qt.GlobalColor.transparent)
                        p.end();layer.files[path]=png(image)
                    else:layer.files={p:data for p,data in layer.files.items() if not matches(p)}
                self.layers=[layer for layer in self.layers if layer.files or layer.uid not in ids]
            # A deleted library source must not be resurrected by project-only undo.
            self.resource_history=[];self.selected_asset=None
            if affected:self.changed()
            self.refresh()
            return
        owner=self.source(d['origin'])
        if owner is None:return
        if d['kind']=='root' or owner.kind=='component':self.remove_layers([owner.uid]);return
        self.cancel_edit_for({owner.uid});super().delete_resource(d)
    def resource_menu(self,d):
        menu=self.resource_menu_base(d)
        selector=getattr(self,'library_mode',None) is not None and self.library_mode.currentIndex()==1
        if selector and not d['origin'].startswith('stage:'):
            for action in list(menu.actions()):
                if action.text() in ('选中','取消选中','替换为选中','Select','Deselect','Replace with selected'):
                    menu.removeAction(action);action.deleteLater()
        if d.get('kind')=='png' and not d['origin'].startswith('stage:'):
            stable=copy.deepcopy(d)
            menu.addAction(self.tr('在文件树中查看','Show in file tree'),lambda:self.run(lambda:self.reveal_in_tree(stable)))
        from .batch_recolor import add_action
        add_action(self,menu,d)
        from .capabilities import replacement
        menu.setToolTipsVisible(True)
        for action in menu.actions():
            if action.text() in ("撤销上次资源／合成操作","Undo resource / composition action"):
                menu.removeAction(action);action.deleteLater();continue
            if action.text() in ("替换为选中","Replace with selected"):
                allowed,reason=replacement(self,d);action.setEnabled(allowed);action.setToolTip(reason)
        return menu
    def reveal_in_tree(self,d):
        if self.is_builtin(d):self.defaults.setChecked(True)
        self.search.clear()
        self.library_mode.setCurrentIndex(0)
        if hasattr(self,'vanilla_version'):self.vanilla_version.setCurrentIndex(0)
        self.refresh()
        item=next((item for item in self.tree_items.values() if (item.data(0,Qt.ItemDataRole.UserRole) or {}).get('origin')==d['origin'] and (item.data(0,Qt.ItemDataRole.UserRole) or {}).get('path')==d['path'] and (item.data(0,Qt.ItemDataRole.UserRole) or {}).get('kind')=='png'),None)
        if item is not None:
            parent=item.parent()
            while parent is not None:parent.setExpanded(True);parent=parent.parent()
            self.tree.setCurrentItem(item);self.tree.scrollToItem(item);self.docks['library'].show()

    def resource_menu_base(self,d):
        if d['origin']=='@category':return QMenu(self)
        if d.get('kind')=='game_object':
            menu=QMenu(self);stable=copy.deepcopy(d)
            for title,fn in [('打开物品关联素材',self.edit_descriptor),('加入项目',self.add_to_composition),('查看关联资源与缺失引用',self.show_resource_group)]:
                action=menu.addAction(title);action.triggered.connect(lambda checked=False,f=fn:self.run(lambda:f(stable)))
            if hasattr(self,'resource_rules'):self.resource_rules.add_action(menu,d)
            menu.aboutToHide.connect(menu.deleteLater);return menu
        if d.get('kind')=='resource_group':
            menu=QMenu(self);stable=copy.deepcopy(d)
            action=menu.addAction(self.tr('加入项目','Add to project'));action.setEnabled(bool(d.get('resource_paths')))
            action.triggered.connect(lambda:self.run(lambda:self.add_to_composition(stable)))
            details=menu.addAction('查看关联资源与缺失引用');details.setEnabled(bool(d.get('resource_paths')))
            details.triggered.connect(lambda:self.run(lambda:self.show_resource_group(stable)))
            if hasattr(self,'resource_rules'):self.resource_rules.add_action(menu,d)
            menu.aboutToHide.connect(menu.deleteLater);return menu
        if d['origin'].startswith('stage:'):
            menu=super().resource_menu(d)
            menu.actions()[2].setText(self.tr('取消选中','Deselect') if self.descriptor_selected(d) else self.tr('选中','Select'))
            for existing in menu.actions():
                if existing.text() in ('添加到合成台','Add to composition'):
                    existing.setText(self.tr('复制为新项目项','Duplicate as project item'))
            # Queue destructive actions until Qt has finished dispatching the menu event.
            action=menu.actions()[1];action.triggered.disconnect();stable=copy.deepcopy(d)
            action.triggered.connect(lambda checked=False:QTimer.singleShot(0,lambda:self.run(lambda:self.delete_resource(stable))))
            if d['kind']=='root':
                for zh,en,fn in [('上移','Move up',lambda:self.move_project_item(d['origin'][6:],-1)),('下移','Move down',lambda:self.move_project_item(d['origin'][6:],1)),('合并选中项','Merge selected',self.merge_selected)]:
                    action=menu.addAction(self.tr(zh,en));action.triggered.connect(lambda checked=False,f=fn:self.run(f))
                action=menu.addAction(self.tr('在新窗口打开','Open another view'));uid=d['origin'][6:];action.triggered.connect(lambda:self.queue_open_layer(uid,True))
            self.add_source_version_menu(menu,d)
            self.add_conversion_menu(menu,d)
            if hasattr(self,'resource_rules'):self.resource_rules.add_action(menu,d)
            from .material_derivation import add_action as add_derivation
            add_derivation(self,menu,d)
            from .material_relations import add_action as add_relations
            add_relations(self,menu,d)
            from .audio_preview import add_actions
            add_actions(self,menu,d)
            return menu
        menu=QMenu(self);stable=copy.deepcopy(d)
        for zh,en,fn in [('加入项目','Add to project',self.add_to_composition),('直接编辑素材','Edit library asset',self.edit_descriptor),('取消选中' if self.descriptor_selected(d) else '选中','Deselect' if self.descriptor_selected(d) else 'Select',self.select_asset),('替换为选中','Replace with selected',self.replace_with_selected)]:
            a=menu.addAction(self.tr(zh,en));a.triggered.connect(lambda checked=False,f=fn:self.run(lambda:f(stable)))
            if fn==self.edit_descriptor:a.setEnabled(not self.is_builtin(d) and (d['kind'] in ('png','component') or d.get('path','').lower().endswith('.ogg')))
            if fn==self.replace_with_selected:a.setEnabled(self.selected_asset is not None and not self.is_builtin(d))
        if not d['origin'].startswith('@vanilla') and (not self.is_builtin(d) or d['kind']=='root'):
            a=menu.addAction(self.tr('删除素材','Delete asset and related copy content'));a.triggered.connect(lambda:QTimer.singleShot(0,lambda:self.run(lambda:self.delete_resource(stable))))
        self.add_source_version_menu(menu,d)
        self.add_conversion_menu(menu,d)
        if d.get('object_paths'):
            action=menu.addAction('查看关联资源与缺失引用')
            action.triggered.connect(lambda:self.run(lambda:self.show_resource_group(stable)))
        from .audio_preview import add_actions
        add_actions(self,menu,d)
        if hasattr(self,'resource_rules'):self.resource_rules.add_action(menu,d)
        from .material_derivation import add_action as add_derivation
        add_derivation(self,menu,d)
        from .material_relations import add_action as add_relations
        add_relations(self,menu,d)
        menu.aboutToHide.connect(menu.deleteLater);return menu
    def show_resource_group(self,d):
        asset=self.snapshot(d);selection=asset.get('selection',{})
        message=QMessageBox(self);message.setWindowTitle(d['name'])
        message.setText(f"关联 {len(asset['files'])} 个文件，{len(selection.get('missing',[]))} 个引用尚未在来源包或原版中找到。")
        detail='资源：\n'+'\n'.join(asset['files'])
        if selection.get('shared_textures'):detail+='\n\n穿戴纹理可能由多件装备共享：\n'+'\n'.join(selection['shared_textures'])
        if selection.get('missing'):detail+='\n\n尚未解析的引用：\n'+'\n'.join(selection['missing'])
        message.setDetailedText(detail);message.exec()
    def add_conversion_menu(self,menu,d):
        if self.is_builtin(d):return
        from .conversion import pack_selection
        if pack_selection(self.source(d['origin']),d) is None:return
        stable=copy.deepcopy(d);action=menu.addAction(self.tr('跨版本处理…','Convert resource pack…'));action.setObjectName('convertWholePack')
        action.triggered.connect(lambda:QTimer.singleShot(0,lambda:self.run(lambda:self.convert_pack_action(stable))))
    def convert_pack_action(self,d):
        if self.is_builtin(d):return
        from .conversion import pack_selection,convert_pack,apply_pack
        from .conversion_dialog import ConversionDialog
        from PySide6.QtWidgets import QDialog,QApplication
        owner=self.source(d['origin']);selection=pack_selection(owner,d)
        if selection is None:raise ValueError(self.tr('请选择完整材质包根目录。','Choose a complete resource pack root.'))
        prefix,working=selection;project=d['origin'].startswith('stage:')
        dialog=ConversionDialog(self,[working],project=project);self.conversion_dialog=dialog
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        report=[]
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:converted=convert_pack(working,self.vanilla,dialog.version.currentData(),self.working_version,report_out=report)
        finally:QApplication.restoreOverrideCursor()
        from .conversion import review_conversion
        if not review_conversion(self,converted,report):return
        self.commit_pack_conversion(d,converted,prefix,dialog.keep_original.isChecked())
        self.statusBar().showMessage(self.tr('跨版本处理完成：','Conversion complete: ')+converted.source_version)
        from .export_history import record
        try:record(self,self.tr('跨版本处理：','Conversion: ')+d['name'],converted.source_version,[working],converted.files,report)
        except OSError as error:
            QMessageBox.warning(self,self.tr('记录保存失败','History could not be saved'),self.tr('转换已完成，但记录未保存：','Conversion completed, but its history could not be saved: ')+str(error))
    def commit_pack_conversion(self,d,converted,prefix='',keep_original=False):
        from .conversion import apply_pack
        owner=self.source(d['origin'])
        if owner is None:raise ValueError('Pack no longer exists')
        project=d['origin'].startswith('stage:')
        if keep_original:
            candidate=self.clone_layer(converted);candidate.uid=uuid.uuid4().hex;candidate.name=d['name']+' → '+converted.source_version
            if not project:candidate.library_uid='';candidate.library_refs=[]
        else:candidate=apply_pack(owner,prefix,converted)
        if not project:self.library_store.put(candidate)
        self.remember()
        if keep_original:
            if project:self.layers.insert(self.layers.index(owner),candidate)
            else:self.sources.append(candidate)
        else:
            if self.source(self.current_source) is owner:self.clear_editor()
            self.cancel_edit_for({owner.uid});self.cancel_asset_selection()
            for key in ('files','source_version','format_hint','asset_versions','layout_confirmations'):setattr(owner,key,getattr(candidate,key))
        if project:self.changed()
        self.refresh()
    def add_source_version_menu(self,menu,d):
        if self.is_builtin(d):return
        from .versions import VERSIONS,source_version
        owner=self.source(d['origin'])
        if not owner:return
        version=owner.asset_versions.get(d['path'],owner.source_version)
        sub=menu.addMenu(self.tr('源版本（识别／校正）：','Source version (detect / override): ')+(version or self.tr('未知','Unknown')))
        for value in VERSIONS:
            action=sub.addAction(value);action.setCheckable(True);action.setChecked(value==version)
            action.triggered.connect(lambda checked=False,v=value:self.run(lambda:self.set_source_version(d,v)))
    def set_source_version(self,d,version):
        owner=self.source(d['origin'])
        if not owner:return
        self.remember()
        if d['kind']=='root':
            owner.source_version=version;owner.asset_versions.clear();owner.layout_confirmations.clear()
            from .layouts import layout_catalog,confirm_layout
            for path in owner.files:
                if version in layout_catalog().get(path,{}):confirm_layout(owner,path,version)
        else:
            paths=[p for p in owner.files if p==d['path'] or (d['kind']=='folder' and p.startswith(d['path']+'/'))]
            for path in paths:owner.asset_versions[path]=version
            from .layouts import layout_catalog,confirm_layout
            for path in paths:
                if version in layout_catalog().get(path,{}):confirm_layout(owner,path,version)
            if d['kind']=='png':
                from .layouts import layout_catalog,confirm_layout
                if version in layout_catalog().get(d['path'],{}):confirm_layout(owner,d['path'],version)
            if owner.kind=='component':owner.source_version=version
        if not d['origin'].startswith('stage:'):self.library_store.put(owner)
        else:self.changed()
        if self.current:self.auto_model()
    def descriptor_items(self,d):
        key=self.descriptor_key(d)
        if d['origin'].startswith('stage:'):return [r['items'][key] for r in self.browsers if key in r['items']]
        return [self.tree_items[key]] if key in self.tree_items else []
    def descriptor_selected(self,d):return any(item.isSelected() for item in self.descriptor_items(d))
    def select_asset(self,d):
        selected=self.descriptor_selected(d)
        for item in self.descriptor_items(d):item.setSelected(not selected)
        if selected:
            if getattr(self,'selected_asset_key',None)==self.descriptor_key(d):self.selected_asset=None;self.selected_asset_key=None
        else:
            super().select_asset(d);self.selected_asset_key=self.descriptor_key(d)
        if not d['origin'].startswith('stage:'):
            self.library_search_scope=copy.deepcopy(d) if not selected and d['kind'] in ('root','folder') else None
            self.filter_tree()
    def move_project_item(self,uid,delta):
        ids=[layer.uid for layer in self.layers];index=ids.index(uid);other=index+delta
        if 0<=other<len(ids):ids[index],ids[other]=ids[other],ids[index];self.apply_order(ids)
    def replace_with_selected(self,d):
        from .capabilities import replacement
        allowed,reason=replacement(self,d)
        if not allowed:raise ValueError(reason)
        from .resource_history import transaction
        with transaction(self,d['origin']):return self._replace_with_selected(d)
    def _replace_with_selected(self,d):
        if self.is_builtin(d):return
        owner=self.source(d['origin']);selected=self.selected_asset
        from .sounds import is_audio
        if is_audio(d.get('path','')):
            sounds=[raw for path,raw in (selected or {}).get('files',{}).items() if is_audio(path)]
            if len(sounds)!=1:raise ValueError('请先选中单个 OGG 音效作为替换来源')
            from .audio_preview import open_sound
            open_sound(self,d);self.audio_preview.replace_bytes(sounds[0]);return
        if d.get('bindings') and owner and owner.kind!='component' and selected:
            from .core import preserve_resolution
            bindings=d['bindings']
            if selected['kind']=='component':values=[selected['files'][str(i)] for i in range(len(selected['regions']))]
            elif all(b['path'] in selected['files'] for b in bindings):values=[selected['files'][b['path']] for b in bindings]
            elif len(bindings)==1 and len(selected['files'])==1:values=list(selected['files'].values())
            else:raise ValueError('请选中对应的同类部件集合，或包含相同资源路径的素材。')
            if len(values)!=len(bindings):raise ValueError('组件数量不一致。')
            if any(decode(raw).size()!=decode(owner.files[b['path']]).copy(*pixel_rect(b['region'],decode(owner.files[b['path']]))).size() for b,raw in zip(bindings,values)):
                if QMessageBox.question(self,'尺寸转换','按较高清一方进行最近邻缩放？不会缩小高清内容。',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Yes:return
            images={}
            for b,raw in zip(bindings,values):
                path=b['path'];atlas=images.get(path)
                if atlas is None:atlas=decode(owner.files[path])
                patch=decode(raw);atlas=preserve_resolution(atlas,patch,b['region']);x,y,width,height=pixel_rect(b['region'],atlas)
                painter=QPainter(atlas);painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source);painter.drawImage(x,y,patch.scaled(width,height));painter.end();images[path]=atlas
            self.remember();owner.files.update({p:png(im) for p,im in images.items()})
            if not d['origin'].startswith('stage:'):self.library_store.put(owner)
            self.clear_editor();self.changed();self.refresh();return
        if owner and owner.kind=='component' and selected:
            values=[selected['files'][str(i)] for i in range(len(selected['regions']))] if selected['kind']=='component' else list(selected['files'].values())
            if len(values)!=len(owner.regions):raise ValueError(self.tr('组件数量不一致。','Component counts differ.'))
            targets=[decode(owner.files[str(i)]) for i in range(len(values))];images=[decode(v) for v in values]
            if any(a.size()!=b.size() for a,b in zip(images,targets)):
                if QMessageBox.question(self,self.tr('尺寸转换','Resize'),self.tr('按较高清的一方进行最近邻缩放？','Keep the higher resolution using nearest-neighbour scaling?'))!=QMessageBox.StandardButton.Yes:return
            self.remember();self.cancel_edit_for({owner.uid});owner.files={str(i):png(image.scaled(max(image.width(),targets[i].width()),max(image.height(),targets[i].height()))) for i,image in enumerate(images)}
            if not d['origin'].startswith('stage:'):self.library_store.put(owner)
            self.edit_descriptor(d);self.changed();self.refresh();return
        super().replace_with_selected(d)
        if owner and not d['origin'].startswith('stage:'):self.library_store.put(owner)
    def snapshot(self,d):
        if d.get('kind')=='resource_group' or d.get('object_paths'):
            from .resource_graph import graph_for
            from .versions import source_version
            owner=self.source(d['origin'])
            if owner is None:raise ValueError('来源材质包已移除')
            seeds=d.get('export_object_paths') or d.get('resource_paths',d.get('object_paths',[]))
            if not seeds:raise ValueError('此分类没有可用资源')
            graph=graph_for(self,owner);paths,missing=graph.closure(seeds,include_callers=False)
            version=source_version(owner,self.working_version)
            vanilla_paths=self.vanilla.paths(version)
            unresolved=sorted(missing-set(vanilla_paths))
            from .selection_state import subset
            selection=subset(owner,paths)
            selection.update({'name':d['name'],'object_id':d.get('object_id'),'seeds':list(seeds),
                       'missing':unresolved,'references':[edge for edge in graph.evidence if edge['source'] in paths],
                       'shared_textures':[p for p in paths if '/models/armor/' in p or '/entity/equipment/' in p]})
            return {'name':d['name'],'files':{p:owner.files[p] for p in sorted(paths)},'kind':'pack',
                    'path':'','regions':[],'origin':self.origin_label(owner),'hint':owner.format_hint,
                    'version':version,'asset_versions':{p:v for p,v in owner.asset_versions.items() if p in paths},'selection':selection}
        owner=self.source(d['origin'])
        if owner and owner.kind=='component':
            from .versions import source_version
            return {'name':owner.name,'files':dict(owner.files),'kind':'component','path':owner.target,'regions':copy.deepcopy(owner.regions),'origin':owner.source,'hint':owner.format_hint,'version':source_version(owner,self.working_version),'asset_versions':dict(owner.asset_versions)}
        asset=super().snapshot(d)
        from .sounds import is_audio
        if owner and is_audio(d.get('path','')):
            from .resource_graph import graph_for
            paths,_=graph_for(self,owner).closure([d['path']])
            asset['files']={path:owner.files[path] for path in paths}
        if owner and asset['kind']!='component':
            for path in list(asset['files']):
                if path.lower().endswith('.png') and path+'.mcmeta' in owner.files:asset['files'][path+'.mcmeta']=owner.files[path+'.mcmeta']
            from .selection_state import subset
            asset['selection']=subset(owner,asset['files'])
        return asset
    def canvas_hover(self,pixel):
        atlas_pixel=self.to_atlas_pixel(pixel)
        self.preview.set_highlight(atlas_pixel,self.canvas.tool=='eraser' or self.canvas.color.alpha()==0)
    def to_atlas_pixel(self,pixel):
        if pixel is None or not self.current:return None
        if not self.current[1]:return pixel
        for rect,region in zip(self.edit_parts,self.current[1]):
            x,y,w,h=rect
            if x<=pixel[0]<x+w and y<=pixel[1]<y+h:
                return round(region[0]*self.atlas_size[0])+pixel[0]-x,round(region[1]*self.atlas_size[1])+pixel[1]-y
        return None
    def model_hover(self,pixel):
        if self.canvas.tool not in ('pencil','eraser'):return
        target=pixel
        if pixel is not None and self.current and self.current[1]:
            target=None
            for rect,region in zip(self.edit_parts,self.current[1]):
                x,y,w,h=rect;ax=round(region[0]*self.atlas_size[0]);ay=round(region[1]*self.atlas_size[1])
                if ax<=pixel[0]<ax+w and ay<=pixel[1]<ay+h:target=(x+pixel[0]-ax,y+pixel[1]-ay);break
        self.canvas.set_hover(target);self.preview.set_highlight(pixel,self.canvas.tool=='eraser')
    def queue_live_texture(self):
        if not self.texture_timer.isActive():self.texture_timer.start(30)
    def live_texture(self):
        if not self.current or self.canvas.image.isNull():return
        from .sky_view import sync_preview
        if sync_preview(self):return
        animation=getattr(self,'animation_editor',None)
        if animation and animation.frames:
            animation.refresh_preview();return
        if getattr(self,'edit_bindings',None) or not self.preview.faces:
            self.preview.flat_image=self.canvas.view_image();self.preview.update();return
        path,regions=self.current
        if not regions or self.canvas.regions:image=QImage(self.canvas.image)
        else:
            data=self.preview_files().get(path) or self.vanilla.get(self.working_version,path)
            if not data:return
            image=decode(data);p=QPainter(image)
            try:
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                for r,rect in zip(regions,self.edit_parts):
                    x,y,w,h=pixel_rect(r,image);p.drawImage(x,y,self.canvas.image.copy(*rect).scaled(w,h))
            finally:p.end()
        self.preview.image=image
        if path in self.preview.textures:self.preview.textures[path]=image
        self.preview.update()
    def is_builtin(self,d):
        origin=d.get('origin','')
        if origin.startswith('@vanilla'):return True
        if origin.startswith('stage:'):return False
        owner=self.source(origin)
        return bool(owner and owner.read_only)
    def update_edit_preview(self):
        if getattr(self,'large_view_only',False):return
        from .sky_view import sync_preview
        if sync_preview(self):return
        if getattr(self,'edit_bindings',None):
            self.preview.flat_image=self.canvas.view_image();self.preview.update();return
        super().update_edit_preview()
        if self.current and not self.preview.faces:
            self.preview.flat_image=self.canvas.view_image();self.preview.update()
        if hasattr(self,'animation_editor'):self.animation_editor.refresh_preview()
    def auto_model(self):
        context=getattr(self,'selector_context',None)
        if not context:return super().auto_model()
        if not self.current or getattr(self,'large_view_only',False):return
        if context.get('state_texture_only'):return super().auto_model()
        self.sync_model_library()
        namespace,identity=context['object_id'].split(':',1)
        kind,_,name=identity.partition('/')
        path=self.current[0]
        if '/textures/entity/' in path or '/textures/models/armor/' in path:
            key=self.model_library.identify(path,self.canvas.image)
            if key and key.startswith('armor:'):
                slot=name.rsplit('_',1)[-1]
                if slot in ('helmet','chestplate','leggings','boots'):key='armor:'+slot
            self.select_model_key(key)
            index=self.texture_binding.findData('linked')
            if key and index>=0:self.texture_binding.setCurrentIndex(index)
            if key is None:self.update_edit_preview()
            return
        candidates=context.get('state_models',[])
        if not candidates and kind in ('block','item'):
            # Inventory icons of blocks (doors, beds, etc.) remain part of the block object.
            folders=('item','block') if '/textures/item' in self.current[0] else ('block','item')
            candidates=[f'assets/{namespace}/models/{folder}/{name}.json' for folder in folders]
        key=next((p for p in candidates if p in self.model_library.entries),None)
        if key is None and kind in ('block','item'):key=self.model_library.from_id(namespace+':'+name)
        if key is None and kind not in ('block','item'):return super().auto_model()
        self.select_model_key(key)
        if key is None:self.update_edit_preview()
        if key:
            # A shared face must never be spread across every face of the selected object.
            index=self.texture_binding.findData('linked')
            if index>=0:self.texture_binding.setCurrentIndex(index)
    def changed(self):
        from .resource_history import seal
        seal(self)
        super().changed();self.draft_revision+=1
        if hasattr(self,'draft_timer') and self.drafts_enabled and not self.draft_timer.isActive():self.draft_timer.start(1200)
    def save_draft(self):
        if not self.drafts_enabled or not self.dirty or self.draft_future is not None or self.draft_saved_revision==self.draft_revision:return
        self.draft_path.parent.mkdir(parents=True,exist_ok=True);layers=[self.clone_layer(l) for l in self.layers]
        revision=self.draft_revision;path=self.draft_path;version=self.working_version
        self.draft_future=self.draft_executor.submit(save_project,path,layers,version,self.referenced_sources())
        self.draft_job=(path,revision)
    def check_draft(self):
        if self.draft_future is None or not self.draft_future.done():return
        try:
            self.draft_future.result()
            if self.draft_job[0]==self.draft_path:self.draft_saved_revision=self.draft_job[1]
        except Exception:logging.exception('Project draft write failed')
        self.draft_future=None
        if self.draft_saved_revision!=self.draft_revision:self.save_draft()
    def clear_recovery(self):
        # Queue removal after any in-flight write, so it cannot recreate the file.
        old=self.draft_path;self.draft_timer.stop()
        self.draft_path=ROOT/'projects'/('Recovery-'+uuid.uuid4().hex[:12]+'.MCPSD')
        self.draft_saved_revision=self.draft_revision
        if self.drafts_enabled:self.draft_executor.submit(lambda path=old:path.unlink(missing_ok=True))

    def write_project(self,path,copy=False,folder=False):
        self.library_store.flush()
        target=Path(path);folder=folder or target.is_dir();actual=target/'project.packstudio' if folder else target;self.protect_source(actual)
        if folder:target.mkdir(parents=True,exist_ok=True)
        save_project(actual,self.layers,self.working_version,self.referenced_sources())
        if not copy:
            self.project_path=target;self.dirty=False;self.setWindowModified(False);self.setWindowTitle(f'{target.name} [*]');self.clear_recovery()
        self.statusBar().showMessage(self.tr('已保存项目：','Project saved: ')+str(target))
    def read_project(self,path):
        target=Path(path);layers,version,legacy_sources=load_project(target/'project.packstudio' if target.is_dir() else target,include_sources=True)
        self.clear_editor()
        if hasattr(self,'operation_history'):self.operation_history.reset()
        for record in list(self.browsers):
            if record['uid']:self.close_browser(record)
        known={s.uid for s in self.sources}
        for source in legacy_sources:
            if source.uid not in known:self.library_store.put(source);self.sources.append(source);known.add(source.uid)
        # Older projects contain only snapshots: register their backing assets in the library.
        for layer in layers:
            if not self.layer_refs(layer) or not self.layer_refs(layer)<=known:
                source=self.clone_layer(layer);source.uid=uuid.uuid4().hex;source.library_uid='';source.library_refs=[]
                self.library_store.put(source);self.sources.append(source);known.add(source.uid)
                layer.library_uid=source.uid;layer.library_refs=[source.uid]
        self.clear_recovery()
        self.layers=layers;self.working_version=version;self.project_path=target;self.resource_history=[];self.refresh();self.dirty=False;self.setWindowModified(False)
        self.version.setCurrentIndex(0);self.setWindowTitle(f'{target.name} [*]');self.draft_path=ROOT/'projects'/('Recovery-'+uuid.uuid4().hex[:12]+'.MCPSD');self.draft_revision+=1
    def close_project(self):
        if not self.discard_ok():return
        self.clear_recovery()
        self.clear_editor()
        if hasattr(self,'operation_history'):self.operation_history.reset()
        for record in list(self.browsers):
            if record['uid']:self.close_browser(record)
        self.layers=[];self.resource_history=[];self.project_path=None;self.selected_asset=None;self.refresh();self.dirty=False;self.setWindowModified(False);self.setWindowTitle(APP_TITLE)
        self.draft_timer.stop();self.draft_path=ROOT/'projects'/('Recovery-'+uuid.uuid4().hex[:12]+'.MCPSD');self.draft_revision=0;self.draft_saved_revision=0
    def remember(self):
        from .resource_history import remember
        remember(self)
    def undo_resource(self):
        history=getattr(self,'operation_history',None)
        if history and not history.busy and history.done and history.done[-1]['kind']=='group':return history.step(barriers=True)
        if not self.resource_history:return
        from .resource_history import LibraryChange,ProjectChange,undo,undo_project
        if isinstance(self.resource_history[-1],LibraryChange):return undo(self,self.resource_history[-1])
        if isinstance(self.resource_history[-1],ProjectChange):return undo_project(self,self.resource_history[-1])
        _,layers=self.resource_history.pop();self.clear_editor();known={source.uid for source in self.sources}
        self.layers=[layer for layer in layers if self.layer_refs(layer)<=known]
        for record in list(self.browsers):
            if record['uid'] and not self.source('stage:'+record['uid']):self.close_browser(record)
        self.changed();self.refresh()
    def referenced_sources(self):
        refs={uid for layer in self.layers for uid in self.layer_refs(layer)}
        return [self.clone_layer(source) for source in self.sources if source.uid in refs]
    def closeEvent(self,event):
        if not self.discard_ok():event.ignore();return
        if hasattr(self,'audio_preview'):self.audio_preview.stop()
        try:self.library_store.close()
        except Exception as error:
            logging.exception('Library save failed on close')
            QMessageBox.warning(self,'保存失败 / Save failed',str(error));event.ignore();return
        self.library_save_timer.stop()
        self.settings.setValue('dock-layout-v3',self.saveState(3));self.selection_timer.stop();self.texture_timer.stop();self.draft_timer.stop();self.draft_poll.stop()
        self.clear_recovery()
        if self.drafts_enabled:self.draft_executor.shutdown(wait=False)
        self.close_pickers();event.accept()
