"""Source library and composition workbench sharing one browser and canvas.

Tree items contain immutable resource descriptions, never model pointers.
Actions resolve sources by UUID after the event has returned to Qt.
"""
import copy
import logging
import uuid
from collections import Counter
from dataclasses import replace
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QSignalBlocker
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QStackedWidget,QScrollArea,QMenu,
    QTreeWidgetItem,QListWidgetItem,QAbstractItemView,QFileDialog,QMessageBox,QInputDialog)
from .ui import Window
from .versions import source_version
from .core import (Layer,import_pack,identify,decode,png,pixel_rect,components,compose,
    save_project,load_project,safe_path,ROOT)

class WorkspaceWindow(Window):
    def __init__(self):
        self.sources=[];self.current_source=None;self.selected_asset=None;self.resource_history=[]
        self.pending_resource=None;self.busy=False;self.tree_items={};self.context_popup=None
        super().__init__()
        for i,(zh,en) in enumerate([('预览','Preview'),('合成','Compose')]):
            self.tabs.setTabText(i,self.tr(zh,en))
            self.labels=[(w,zh if w is self.tabs and tab==i else a,en if w is self.tabs and tab==i else b,tab) for w,a,b,tab in self.labels]
        self.tabs.currentChanged.connect(self.switch_mode)
        self.switch_mode(0);self.refresh()
        self.statusBar().showMessage(self.tr('导入来源后，右键整包、文件夹或 PNG → 添加到合成台。','Import sources, then right-click a pack, folder or PNG → Add to composition.'))
    def run(self,fn):
        history=getattr(self,'operation_history',None)
        if history:history.clear_preview()
        try:return fn()
        except Exception as error:
            logging.exception('Workspace action failed')
            QMessageBox.warning(self,self.tr('操作未完成，项目仍保留','Operation failed; project retained'),str(error))
    def build_editor(self):
        super().build_editor()
        for i,(widget,zh,en,tab) in enumerate(self.labels):
            if zh.startswith('滚轮缩放'):
                zh='滚轮缩放 · 中键平移。编辑当前来源的项目副本；右键添加到合成台，已有合成副本独立保留。'
                en='Wheel: zoom · Middle drag: pan. Edit the project source copy; right-click to stage a separate composition copy.'
                widget.setText(self.tr(zh,en));self.labels[i]=(widget,zh,en,tab)
        # Do not toggle expansion during mouse events. Qt owns double-click expansion.
        self.tree.itemClicked.disconnect()
        self.tree.setExpandsOnDoubleClick(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_resource_menu)
        self.tree.itemExpanded.connect(lambda item:self.run(lambda:self.populate_components(item,item.data(0,Qt.ItemDataRole.UserRole) or {})))
        self.selection_timer=QTimer(self);self.selection_timer.setSingleShot(True)
        self.selection_timer.timeout.connect(lambda:self.run(self.apply_pending_resource))
        self.caption.setWordWrap(True)
    def build_export(self):
        panel=QWidget();box=QVBoxLayout(panel);original=self.pages[1];self.pages[1]=box
        super().build_export();self.pages[1]=original
        row=QVBoxLayout();box.insertLayout(2,row)
        self.button(row,'合并选中项（上层优先）','Merge selected (top wins)',self.merge_selected)
        self.button(row,'重命名显示名称','Rename display label',self.rename_layer)
        self.button(row,'撤销上次资源／合成操作','Undo resource / composition action',self.undo_resource)
        self.label(box,'导入的来源独立保存。添加到合成台会建立副本；同名资源保留来源标记，导出使用原资源路径，上层覆盖下层。','Imported sources are independent. Composition receives copies. Name collisions keep source labels; export uses original resource paths, with top layers winning.')
        self.stack.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.stack.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.stack.customContextMenuRequested.connect(self.show_stack_menu)
        self.right_stack=QStackedWidget();self.preview_panel.setParent(None)
        self.editor_split.addWidget(self.right_stack);self.right_stack.addWidget(self.preview_panel)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(panel);self.right_stack.addWidget(scroll)
        self.editor_split.setSizes([300,700,420]);self.compose_panel=panel
    def switch_mode(self,index):
        if index not in (0,1):return
        self.selection_timer.stop();self.pending_resource=None
        # Move the SAME splitter between mode pages; canvas, selection and zoom survive.
        self.pages[1-index].removeWidget(self.editor_split);self.pages[index].addWidget(self.editor_split)
        self.editor_split.show();self.right_stack.setCurrentIndex(index)
        enabled=self.preview_action.isChecked() if hasattr(self,'preview_action') else True
        self.right_stack.setVisible(index==1 or enabled)
        if index==0:self.preview_panel.setVisible(enabled)
    def toggle_preview(self,enabled):
        self.settings.setValue('preview',enabled)
        self.preview_panel.setVisible(enabled)
        if hasattr(self,'right_stack'):self.right_stack.setVisible(self.tabs.currentIndex()==1 or enabled)
    def source(self,uid):
        if uid and uid.startswith('stage:'):
            return next((l for l in self.layers if l.uid==uid[6:]),None)
        return next((s for s in self.sources if s.uid==uid),None)
    def origin_label(self,layer):return layer.source or layer.name
    def clone_layer(self,layer):return copy.deepcopy(layer)
    def remember(self):
        self.resource_history.append(([self.clone_layer(s) for s in self.sources],[self.clone_layer(l) for l in self.layers]))
        self.resource_history=self.resource_history[-10:]
    def undo_resource(self):
        if not self.resource_history:return
        self.sources,self.layers=self.resource_history.pop();self.clear_editor();self.changed();self.refresh()
    def clear_editor(self):
        self.selection_timer.stop();self.pending_resource=None;self.current=None;self.current_source=None;self.edit_layer=None
        self.canvas.set_image(QImage());self.caption.clear();self.preview.clear_model();self.model_key=None
    def add_pack(self,path):
        # A failed import never modifies the current project.
        layer=import_pack(path);fmt,matches=identify(layer,self.vanilla)
        layer.format_hint=fmt if isinstance(fmt,(int,float)) else None
        self.remember();self.sources.append(layer);self.changed();self.refresh()
        self.statusBar().showMessage(self.tr(f'已导入来源 {layer.name}：{len(layer.files)} 个文件；右键添加到合成台。',f'Imported source {layer.name}: {len(layer.files)} files. Right-click to add to composition.'))
    def add_png(self):
        path,_=QFileDialog.getOpenFileName(self,'PNG','','PNG (*.png)')
        if not path:return
        target,ok=QInputDialog.getText(self,self.tr('资源路径','Resource path'),'assets/minecraft/...',text=self.current[0] if self.current else 'assets/minecraft/textures/blocks/stone.png')
        if not ok:return
        target=safe_path(target)
        if not target.startswith('assets/') or not target.endswith('.png'):raise ValueError('Expected assets/.../*.png')
        data=Path(path).read_bytes();decode(data);self.remember()
        self.sources.append(Layer(Path(path).stem,{target:data},kind='png',source=str(Path(path).resolve())))
        self.changed();self.refresh()
    def descriptor_key(self,d):return (d['origin'],d['kind'],d['path'],repr(d.get('bindings') or d.get('regions')))
    def refresh(self,*args):
        if self.refreshing:return
        self._lazy_active=hasattr(self,'library_mode') and self.library_mode.currentIndex()==0
        if self._lazy_active:
            from .lazy_browser import refresh
            return refresh(self)
        if hasattr(self,'selector_source') and self.library_mode.currentIndex()==1:
            from .selector import refresh
            return refresh(self)
        self.selection_timer.stop();self.pending_resource=None;self.refreshing=True
        tree_block=QSignalBlocker(self.tree);stack_block=QSignalBlocker(self.stack)
        try:
            expanded={key for key,item in self.tree_items.items() if item.isExpanded()}
            scroll=self.tree.verticalScrollBar().value()
            selected_ids={i.data(Qt.ItemDataRole.UserRole) for i in self.stack.selectedItems()}
            self.stack.clear()
            for layer in self.layers:
                item=QListWidgetItem(layer.name);item.setToolTip(self.origin_label(layer))
                item.setData(Qt.ItemDataRole.UserRole,layer.uid);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if layer.enabled else Qt.CheckState.Unchecked);self.stack.addItem(item)
                item.setSelected(layer.uid in selected_ids)
            self.tree.clear();self.tree_items={};selected=None
            duplicates=Counter(p for s in self.sources for p in s.files if p.endswith('.png'))
            names=Counter(s.name for s in self.sources)
            sources=list(self.sources)
            from .library_browser import builtin_version
            if self.defaults.isChecked():
                from .versions import VERSIONS
                chosen=self.vanilla_version.currentData() if hasattr(self,'vanilla_version') else self.working_version
                for version in VERSIONS if chosen=='all' else [builtin_version(self)]:
                    sources.append(Layer(self.tr('原版资源','Vanilla resources')+' '+version,{p:None for p in self.vanilla.paths(version)},uid='@vanilla:'+version,source_version=version,read_only=True))
            for source in sources:
                label=source.name
                if names[label]>1:label+=f' (from {self.origin_label(source)})'
                if sum(s.name==source.name and s.source==source.source for s in sources)>1:label+=' ['+source.uid[:6]+']'
                root=QTreeWidgetItem([label]);self.tree.addTopLevelItem(root)
                desc={'origin':source.uid,'path':'','kind':'root','name':source.name}
                root.setData(0,Qt.ItemDataRole.UserRole,desc);root.setToolTip(0,self.origin_label(source));self.tree_items[self.descriptor_key(desc)]=root
                root.setExpanded(self.descriptor_key(desc) in expanded or not expanded)
                folders={'':root}
                for path in sorted(source.files):
                    if source.kind=='component':continue
                    parts=path.split('/');parent=root
                    for index,part in enumerate(parts[:-1]):
                        prefix='/'.join(parts[:index+1])
                        if prefix not in folders:
                            item=QTreeWidgetItem([part]);parent.addChild(item)
                            d={'origin':source.uid,'path':prefix,'kind':'folder','name':part}
                            item.setData(0,Qt.ItemDataRole.UserRole,d);item.setToolTip(0,prefix);key=self.descriptor_key(d)
                            self.tree_items[key]=item;folders[prefix]=item;item.setExpanded(key in expanded)
                        parent=folders[prefix]
                    label=parts[-1]
                    if duplicates[path]>1:label+=f' (from {self.origin_label(source)})'
                    item=QTreeWidgetItem([label]);parent.addChild(item)
                    d={'origin':source.uid,'path':path,'kind':'png' if path.lower().endswith('.png') else 'file','name':parts[-1]}
                    item.setData(0,Qt.ItemDataRole.UserRole,d);item.setToolTip(0,f'{path}\nfrom {self.origin_label(source)}');key=self.descriptor_key(d);self.tree_items[key]=item;item.setExpanded(key in expanded)
                    if self.current_source==source.uid and self.current==(path,None):selected=item
                    # Index resources without decoding collapsed atlases for thumbnails.
                    # Expansion and semantic search populate component rows on demand.
                    rules=self.component_rules(d) if d['kind']=='png' else ()
                    if rules:
                        item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                        if key in expanded:self.populate_components(item,d)
                    if self.current_source==source.uid and self.current and self.current[0]==path and self.current[1]:
                        self.populate_components(item,d)
                        for j in range(item.childCount()):
                            if item.child(j).data(0,Qt.ItemDataRole.UserRole).get('regions')==self.current[1]:selected=item.child(j)
            if selected:self.tree.setCurrentItem(selected)
            self.filter_tree();self.tree.verticalScrollBar().setValue(scroll)
        finally:
            del tree_block,stack_block
            self.refreshing=False
    def populate_components(self,item,d):
        if getattr(self,'_lazy_active',False) and d.get('kind') in ('root','folder'):
            self._library_index.populate(item)
            return
        if d.get('kind')!='png' or item.childCount():return
        from .library_browser import populate_parts
        if populate_parts(self,item,d):return
        for name,regions in self.component_rules(d):
            child=QTreeWidgetItem([name]);item.addChild(child)
            data={**d,'kind':'component','name':name,'regions':regions};child.setData(0,Qt.ItemDataRole.UserRole,data)
            self.tree_items[self.descriptor_key(data)]=child
    def component_rules(self,d):
        from .library_browser import builtin_version
        owner=self.source(d['origin'])
        version=source_version(owner,self.working_version) if owner else builtin_version(self,d['origin'])
        if owner:version=owner.asset_versions.get(d['path'],version)
        return components(d['path'],version)
    def filter_tree(self,*args):
        # Visibility changes can alter selection. Suppress callbacks while filtering.
        blocker=QSignalBlocker(self.tree)
        if hasattr(self,'selector_source') and self.library_mode.currentIndex()==1:
            from .selector import filter
            filter(self)
        elif getattr(self,'_lazy_active',False):self._library_index.filter()
        else:
            from .library_browser import filter_library
            filter_library(self)
        del blocker
    def select_resource(self):
        if self.refreshing:return
        item=self.tree.currentItem();d=item.data(0,Qt.ItemDataRole.UserRole) if item else None
        self.selection_timer.stop();self.pending_resource=None
        if not d or d['kind'] not in ('png','component'):return
        self.pending_resource=copy.deepcopy(d);self.selection_timer.start(90)
    def apply_pending_resource(self):
        d=self.pending_resource;self.pending_resource=None
        if d:self.edit_descriptor(d)
    def edit_descriptor(self,d):
        from .semantic_edit import open_group
        if open_group(self,d):return
        self.edit_bindings=None
        self.selection_timer.stop();self.pending_resource=None
        if d['kind'] in ('root','folder'):
            item=self.tree_items.get(self.descriptor_key(d))
            if item:item.setExpanded(True)
            return
        if d['kind'] not in ('png','component'):return
        if not d['origin'].startswith('@vanilla') and self.source(d['origin']) is None:raise ValueError(self.tr('该来源已移除。','Source was removed.'))
        # Do not reload an unchanged selected image on a repeated double-click.
        current=(d['path'],d.get('regions'))
        if self.current==current and self.current_source==d['origin'] and not self.canvas.image.isNull():return
        self.current_source=d['origin'];self.current=current
        try:self.load_canvas()
        except Exception:
            self.clear_editor()
            raise
    def editing_files(self):
        source=self.source(self.current_source)
        if source and source.kind!='component':return source.files
        return self.result()[0] if not (self.current_source or '').startswith('@vanilla') else {}
    def load_canvas(self):
        if not self.current:return
        from .library_browser import builtin_version
        path,regions=self.current;files=self.editing_files();data=files.get(path) or self.vanilla.get(builtin_version(self) if (self.current_source or '').startswith('@vanilla') else self.working_version,path)
        if data is None:raise ValueError(f'Missing resource: {path}')
        atlas=decode(data);self.edit_parts=[];self.atlas_size=(atlas.width(),atlas.height());owner=self.source(self.current_source)
        if owner and owner.kind=='component':
            patches=[(pixel_rect(r,atlas),decode(owner.files[str(i)])) for i,r in enumerate(owner.regions)]
            painter=QPainter(atlas)
            try:
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                for (x,y,w,h),im in patches:painter.drawImage(x,y,im.scaled(w,h))
            finally:painter.end()
        direct=bool(regions and (owner is None or owner.kind!='component'))
        if direct:
            rects=[pixel_rect(r,atlas) for r in regions];top=0
            for x,y,width,height in rects:self.edit_parts.append((0,top,width,height));top+=height
            self.canvas.set_atlas(atlas,rects,(self.current_source,path))
        else:
            image=self.join_parts([atlas.copy(*pixel_rect(r,atlas)) for r in regions]) if regions else atlas
            self.canvas.set_image(image)
        self.edit_layer=owner if self.current_source and self.current_source.startswith('stage:') else None
        origin=self.origin_label(owner) if owner else self.tr('原版／合成结果','Vanilla / composition')
        size=self.canvas.view_size()
        self.caption.setText(f'{path} · {size.width()} × {size.height()}\nfrom {origin}')
        self.preview.image=atlas;self.auto_model()
    def join_parts(self,parts):
        image=QImage(max(p.width() for p in parts),sum(p.height() for p in parts),QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent);painter=QPainter(image);y=0;self.edit_parts=[]
        try:
            for part in parts:
                painter.drawImage(0,y,part);self.edit_parts.append((0,y,part.width(),part.height()));y+=part.height()
        finally:painter.end()
        return image
    def commit_canvas(self):
        from .task_progress import encode_image
        from .semantic_edit import commit_group
        if commit_group(self):return
        if not self.current or self.canvas.image.isNull():return
        path,regions=self.current;owner=self.source(self.current_source);new_owner=False
        if owner is None:
            owner=Layer(self.tr('编辑素材','Edited assets'),source=self.tr('项目编辑副本','Project edit copy'))
            self.sources.append(owner);self.current_source=owner.uid;new_owner=True
        if owner.kind=='component':owner.files={str(i):png(self.canvas.image.copy(*r)) for i,r in enumerate(self.edit_parts)}
        elif self.canvas.regions:
            owner.files[path]=encode_image(self,self.canvas.image)
        elif regions:
            data=owner.files.get(path) or self.vanilla.get(self.working_version,path)
            if data is None:raise ValueError(f'Missing atlas: {path}')
            atlas=decode(data);patches=[(pixel_rect(r,atlas),self.canvas.image.copy(*rect)) for r,rect in zip(regions,self.edit_parts)]
            painter=QPainter(atlas)
            try:
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                for (x,y,w,h),part in patches:painter.drawImage(x,y,part.scaled(w,h))
            finally:painter.end()
            owner.files[path]=png(atlas)
        else:owner.files[path]=encode_image(self,self.canvas.image)
        self.changed()
        if new_owner:self.refresh()
        self.update_edit_preview()
    def sync_model_library(self):
        from .library_browser import builtin_version
        files=self.editing_files();owner=self.source(self.current_source)
        version=source_version(owner,self.working_version) if owner else builtin_version(self)
        if owner and self.current:version=owner.asset_versions.get(self.current[0],version)
        self.model_library.update(files,version);return files
    def preview_files(self):return self.editing_owner_files()
    def editing_owner_files(self):
        owner=self.source(self.current_source)
        if owner and owner.kind!='component':return owner.files
        return compose(self.layers,self.vanilla,self.working_version)[0] if not (self.current_source or '').startswith('@vanilla') else {}
    def snapshot(self,d):
        from .semantic_edit import snapshot_group
        group=snapshot_group(self,d)
        if group:return group
        from .library_browser import builtin_version
        owner=self.source(d['origin']);path=d['path'];kind=d['kind']
        if d['origin'].startswith('@vanilla'):files={p:self.vanilla.get(builtin_version(self,d['origin']),p) for p in self.vanilla.paths(builtin_version(self,d['origin'])) if p==path or not path or p.startswith(path+'/')}
        elif owner:files=owner.files
        else:raise ValueError(self.tr('该资源已不存在。','Resource no longer exists.'))
        if kind in ('root','folder'):selected={p:v for p,v in files.items() if not path or p.startswith(path+'/')};layer_kind='pack';regions=[]
        elif kind=='component':
            image=decode(files[path]);regions=d['regions'];selected={str(i):png(image.copy(*pixel_rect(r,image))) for i,r in enumerate(regions)};layer_kind='component'
        else:selected={path:files[path]};layer_kind='png' if kind=='png' else 'pack';regions=[]
        if not selected:raise ValueError(self.tr('没有可用素材。','No assets available.'))
        return {'name':d['name'],'files':dict(selected),'kind':layer_kind,'path':path,'regions':copy.deepcopy(regions),'origin':self.origin_label(owner) if owner else 'Vanilla '+builtin_version(self,d['origin']),'hint':owner.format_hint if owner else 1,'version':owner.asset_versions.get(path,source_version(owner,self.working_version)) if owner else builtin_version(self,d['origin']),'asset_versions':{p:owner.asset_versions[p] for p in selected if owner and p in owner.asset_versions}}
    def add_to_composition(self,d):
        asset=self.snapshot(d);self.remember();name=asset['name']
        label=f'{name} (from {asset["origin"]})'
        if any(l.name==label for l in self.layers):label+=' ['+uuid.uuid4().hex[:6]+']'
        layer=Layer(label,asset['files'],asset['kind'],asset['path'] if asset['kind']=='component' else '',asset['regions'],source=asset['origin'],format_hint=asset['hint'],source_version=asset.get('version',self.working_version),asset_versions=asset.get('asset_versions',{}))
        layer.bindings=copy.deepcopy(asset.get('bindings',[]))
        layer.selection=copy.deepcopy(asset.get('selection',{}))
        owner=self.source(d['origin'])
        if owner:layer.layout_confirmations={p:copy.deepcopy(v) for p,v in owner.layout_confirmations.items() if p in layer.files}
        self.layers.insert(0,layer);self.changed();self.refresh();self.tabs.setCurrentIndex(1);self.stack.setCurrentRow(0)
    def select_asset(self,d):
        self.selected_asset=self.snapshot(d)
        self.statusBar().showMessage(self.tr('已选中替换来源：','Replacement source selected: ')+d['name'])
    def delete_resource(self,d):
        owner=self.source(d['origin'])
        if owner is None:return
        self.remember();path=d['path']
        if d['kind']=='root':self.sources=[s for s in self.sources if s.uid!=owner.uid]
        elif d['kind']=='folder':owner.files={p:v for p,v in owner.files.items() if not p.startswith(path+'/')}
        elif d['kind']=='component':
            image=decode(owner.files[path]);rects=[pixel_rect(r,image) for r in d['regions']];painter=QPainter(image)
            try:
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                for x,y,w,h in rects:painter.fillRect(x,y,w,h,Qt.GlobalColor.transparent)
            finally:painter.end()
            owner.files[path]=png(image)
        else:owner.files.pop(path,None)
        self.clear_editor();self.changed();self.refresh()
    def replace_with_selected(self,d):
        selected=self.selected_asset;owner=self.source(d['origin'])
        if not selected or owner is None:return
        path=d['path']
        if d['kind'] in ('root','folder'):
            if selected['kind']!='pack':raise ValueError(self.tr('文件夹请使用选中的文件夹或整包替换。','Select a folder or pack to replace a folder.'))
            source_prefix=selected['path'];mapping={}
            for name,data in selected['files'].items():
                relative=name[len(source_prefix)+1:] if source_prefix and name.startswith(source_prefix+'/') else name
                mapping[safe_path((path+'/' if path else '')+relative)]=data
            self.remember();owner.files={p:v for p,v in owner.files.items() if path and not p.startswith(path+'/')};owner.files.update(mapping)
            self.clear_editor();self.changed();self.refresh();return
        if d['kind'] not in ('png','component') or selected['kind'] not in ('png','component'):raise ValueError(self.tr('请选中 PNG 或图内组件。','Select a PNG or image component.'))
        if selected['kind']=='component':images=[decode(selected['files'][str(i)]) for i in range(len(selected['regions']))]
        else:images=[decode(next(iter(selected['files'].values())))]
        target_image=decode(owner.files[path]);target_rects=[pixel_rect(r,target_image) for r in d.get('regions',[])] or [(0,0,target_image.width(),target_image.height())]
        if len(images)!=len(target_rects):raise ValueError(self.tr('组件数量不一致，请选择对应的单个组件或组件组。','Component counts differ. Select a corresponding component or group.'))
        if any(im.width()!=r[2] or im.height()!=r[3] for im,r in zip(images,target_rects)):
            if QMessageBox.question(self,self.tr('尺寸转换','Resize'),self.tr('按较高清的一方进行最近邻缩放？不会缩小高清内容。','Use the higher resolution with nearest-neighbour scaling? High-resolution pixels will not be reduced.'))!=QMessageBox.StandardButton.Yes:return
        from .core import preserve_resolution
        regions=d.get('regions') or [(0,0,1,1)]
        for image,region in zip(images,regions):target_image=preserve_resolution(target_image,image,region)
        target_rects=[pixel_rect(r,target_image) for r in regions]
        self.remember();painter=QPainter(target_image)
        try:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            for image,(x,y,w,h) in zip(images,target_rects):painter.drawImage(x,y,image.scaled(w,h))
        finally:painter.end()
        owner.files[path]=png(target_image);self.current=None;self.edit_descriptor(d);self.changed();self.refresh()
    def resource_menu(self,d):
        menu=QMenu(self)
        def add(zh,en,fn,enabled=True):
            action=menu.addAction(self.tr(zh,en));action.setEnabled(enabled)
            action.triggered.connect(lambda checked=False:self.run(lambda:fn(copy.deepcopy(d))))
        add('编辑','Edit',self.edit_descriptor,d['kind']!='file')
        add('删除','Delete',self.delete_resource,not d['origin'].startswith('@vanilla'))
        add('选中','Select as replacement',self.select_asset)
        add('替换为选中','Replace with selected',self.replace_with_selected,self.selected_asset is not None and not d['origin'].startswith('@vanilla'))
        menu.addSeparator();add('添加到合成台','Add to composition',self.add_to_composition)
        if self.resource_history:
            action=menu.addAction(self.tr('撤销上次资源／合成操作','Undo resource / composition action'));action.triggered.connect(lambda:self.run(self.undo_resource))
        menu.aboutToHide.connect(menu.deleteLater)
        return menu
    def show_resource_menu(self,pos):
        if self.refreshing:return
        self.selection_timer.stop();self.pending_resource=None;item=self.tree.itemAt(pos)
        if item is None:return
        d=copy.deepcopy(item.data(0,Qt.ItemDataRole.UserRole))
        if not d:return
        self.context_popup=self.resource_menu(d);self.context_popup.popup(self.tree.viewport().mapToGlobal(pos))
    def show_stack_menu(self,pos):
        menu=QMenu(self)
        for zh,en,fn in [('编辑','Edit',self.open_layer),('移除','Remove',self.remove_layer),('合并选中项','Merge selected',self.merge_selected),('重命名显示名称','Rename label',self.rename_layer)]:
            a=menu.addAction(self.tr(zh,en));a.triggered.connect(lambda checked=False,f=fn:self.run(f))
        menu.aboutToHide.connect(menu.deleteLater);self.context_popup=menu;menu.popup(self.stack.viewport().mapToGlobal(pos))
    def toggle_layer(self,item):
        if self.refreshing:return
        uid=item.data(Qt.ItemDataRole.UserRole);layer=next((l for l in self.layers if l.uid==uid),None)
        if layer:layer.enabled=item.checkState()==Qt.CheckState.Checked;self.changed()
    def move_layer(self,delta):
        index=self.stack.currentRow();other=index+delta
        if 0<=index<len(self.layers) and 0<=other<len(self.layers):
            self.remember();self.layers[index],self.layers[other]=self.layers[other],self.layers[index];self.changed();self.refresh();self.stack.setCurrentRow(other)
    def remove_layer(self):
        ids={i.data(Qt.ItemDataRole.UserRole) for i in self.stack.selectedItems()}
        if not ids:return
        self.remember();self.layers=[l for l in self.layers if l.uid not in ids]
        if self.current_source and self.current_source.startswith('stage:') and self.current_source[6:] in ids:self.clear_editor()
        self.changed();self.refresh()
    def merge_selected(self):
        ids={i.data(Qt.ItemDataRole.UserRole) for i in self.stack.selectedItems()};indices=[i for i,l in enumerate(self.layers) if l.uid in ids]
        if len(indices)<2:raise ValueError(self.tr('使用 Ctrl 或 Shift 选中至少两个合成项。','Use Ctrl or Shift to select at least two composition items.'))
        selected=[self.layers[i] for i in indices]
        context=self.layers[indices[-1]+1:]
        all_files,_=compose(selected+context,self.vanilla,self.working_version)
        touched={p for l in selected if l.enabled for p in ([b['path'] for b in l.bindings] if l.bindings else [l.target] if l.kind=='component' else l.files)}
        files={p:all_files[p] for p in touched}
        if not files:raise ValueError(self.tr('选中项没有启用的资源。','Selected items contain no enabled resources.'))
        self.remember();name=self.tr('合并素材','Merged assets');origin=' + '.join(l.source or l.name for l in selected)
        hints=[l.format_hint for l in selected if isinstance(l.format_hint,(int,float))]
        merged=Layer(name,files,source=origin,format_hint=max(hints) if hints else None)
        for layer in reversed(selected):
            if layer.enabled:
                for path in ([b['path'] for b in layer.bindings] if layer.bindings else [layer.target] if layer.kind=='component' else layer.files):
                    merged.asset_versions[path]=layer.asset_versions.get(path,source_version(layer,self.working_version))
                    if path in layer.layout_confirmations:merged.layout_confirmations[path]=copy.deepcopy(layer.layout_confirmations[path])
                    else:merged.layout_confirmations.pop(path,None)
        from .selection_state import merged as merged_selection
        merged.selection=merged_selection(selected,files)
        first=indices[0];self.layers=[l for l in self.layers if l.uid not in ids];self.layers.insert(first,merged)
        self.changed();self.refresh();self.stack.setCurrentRow(first)
    def rename_layer(self):
        i=self.stack.currentRow()
        if not 0<=i<len(self.layers):return
        layer=self.layers[i];name,ok=QInputDialog.getText(self,self.tr('显示名称（不改资源路径）','Display label (resource paths unchanged)'),self.tr('名称','Name'),text=layer.name)
        if ok and name.strip():self.remember();layer.name=name.strip();self.changed();self.refresh()
    def open_layer(self):
        i=self.stack.currentRow()
        if not 0<=i<len(self.layers):return
        layer=self.layers[i]
        if layer.kind=='component':path=layer.target;regions=layer.regions
        else:
            paths=[p for p in layer.files if p.lower().endswith('.png')]
            if not paths:return
            path=self.current[0] if self.current and self.current[0] in paths else paths[0];regions=None
        self.current=None;self.edit_descriptor({'origin':'stage:'+layer.uid,'path':path,'regions':regions,'kind':'component' if regions else 'png'})
    def extract(self):
        if not self.current:return
        path,regions=self.current;owner=self.source(self.current_source)
        if regions:
            view=self.canvas.view_image();parts=[view.copy(*r) for r in self.edit_parts]
        else:
            rect=self.canvas.selection
            if not rect:raise ValueError(self.tr('请框选区域或选择已有组件。','Select a rectangle or component.'))
            rectangles=self.canvas.selection_rectangles()
            regions=[(x/self.canvas.image.width(),y/self.canvas.image.height(),w/self.canvas.image.width(),h/self.canvas.image.height()) for x,y,w,h in rectangles]
            parts=[self.canvas.image.copy(*rect) for rect in rectangles]
        name,ok=QInputDialog.getText(self,self.tr('组件名称','Component name'),'Name',text=Path(path).stem)
        if not ok:return
        self.remember();self.layers.insert(0,Layer(name,{str(i):png(p) for i,p in enumerate(parts)},'component',path,regions,source=self.origin_label(owner) if owner else '',format_hint=owner.format_hint if owner else None,source_version=owner.asset_versions.get(path,source_version(owner,self.working_version)) if owner else self.working_version))
        self.changed();self.refresh();self.tabs.setCurrentIndex(1)
    def protect_source(self,path):
        target=Path(path).resolve()
        for layer in [*self.sources,*self.layers]:
            if not layer.source:continue
            source=Path(layer.source)
            try:
                if target==source.resolve() or (source.is_dir() and target.is_relative_to(source.resolve())):raise ValueError(self.tr('请选择原来源之外的新文件。','Choose a new file outside the original source.'))
            except OSError:continue
    def write_project(self,path,copy=False,folder=False):
        target=Path(path);folder=folder or target.is_dir();actual=target/'project.packstudio' if folder else target
        self.protect_source(actual)
        if folder:target.mkdir(parents=True,exist_ok=True)
        save_project(actual,self.layers,self.working_version,self.sources)
        if not copy:self.project_path=target;self.dirty=False;self.setWindowModified(False);self.setWindowTitle(f'{target.name} [*]')
        self.statusBar().showMessage(self.tr('已保存：','Saved: ')+str(target))
    def read_project(self,path):
        target=Path(path);layers,version,sources=load_project(target/'project.packstudio' if target.is_dir() else target,include_sources=True)
        self.clear_editor();self.layers=layers;self.sources=sources;self.working_version=version;self.project_path=target;self.selected_asset=None;self.resource_history=[]
        self.refresh();self.dirty=False;self.setWindowModified(False);self.version.setCurrentIndex(0);self.tabs.setCurrentIndex(0);self.setWindowTitle(f'{target.name} [*]')
    def export(self):
        if not self.layers:raise ValueError(self.tr('合成台为空，请先右键添加资源。','Composition is empty. Right-click resources to add them first.'))
        super().export()
