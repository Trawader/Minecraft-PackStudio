"""V3 source-first selector, sharing library UIDs and original file descriptors."""
from PySide6.QtCore import Qt,QSignalBlocker
from PySide6.QtWidgets import QComboBox,QCheckBox,QTreeWidgetItem,QListWidgetItem
from .object_catalog import TOP
from .game_objects import entries
from .semantics import parts,describe,grouped_parts
from .versions import source_version

ROLE=Qt.ItemDataRole.UserRole


def install(w,layout):
    w.tree.itemExpanded.connect(lambda item:w.run(lambda:expand_states(w,item)))
    def remember(item):
        if w.refreshing or w.library_mode.currentIndex()!=0 or item is None:return
        descriptor=item.data(0,ROLE) or {}
        if descriptor.get('origin'):w._selector_recent_origin=descriptor['origin']
    w.tree.itemExpanded.connect(remember)
    w.tree.currentItemChanged.connect(lambda item,previous:remember(item))
    w.selector_source=QComboBox();w.selector_source.setToolTip('选择当前来源材质包')
    w.selector_full=QCheckBox('显示完整目录')
    w.selector_source.currentIndexChanged.connect(lambda:w.refresh())
    w.selector_full.toggled.connect(lambda:w.refresh())
    layout.insertWidget(2,w.selector_source);layout.insertWidget(3,w.selector_full)
    w.selector_source.hide();w.selector_full.hide()


def complete(source):
    return source.kind=='pack' and 'pack.mcmeta' in source.files and any(p.startswith('assets/') for p in source.files)


def controls(w):
    active=w.library_mode.currentIndex()==1
    w.selector_source.setVisible(active);w.selector_full.setVisible(active)
    w.vanilla_version.setVisible(not active)
    w.defaults.setVisible(not active)


def mode_changed(w):
    if w.library_mode.currentIndex()==1:
        item=w.tree.currentItem()
        descriptor=item.data(0,ROLE) if item else None
        uid=getattr(w,'_selector_recent_origin',None) or (descriptor or {}).get('origin') or w.current_source
        owner=w.source(uid) if uid else None
        if owner and complete(owner):
            w._selector_pending_source=getattr(owner,'library_uid','') or owner.uid
    w.refresh()


def refresh(w):
    w.refreshing=True;w.selection_timer.stop();w.pending_resource=None
    tree_block=QSignalBlocker(w.tree);stack_block=QSignalBlocker(w.stack)
    try:
        selected=getattr(w,'_selector_pending_source',None) or w.selector_source.currentData();w._selector_pending_source=None
        blocker=QSignalBlocker(w.selector_source)
        w.selector_source.clear()
        for source in w.sources:
            if complete(source):w.selector_source.addItem(source.name,source.uid)
        index=w.selector_source.findData(selected)
        if index>=0:w.selector_source.setCurrentIndex(index)
        del blocker
        w.stack.clear()
        for layer in w.layers:
            item=QListWidgetItem(layer.name);item.setData(ROLE,layer.uid)
            item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if layer.enabled else Qt.CheckState.Unchecked);w.stack.addItem(item)
        w.tree.clear();w.tree_items={}
        owner=w.source(w.selector_source.currentData())
        if owner is None:
            item=QTreeWidgetItem(['请先导入完整资源包；独立素材请使用文件树'])
            item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsSelectable);w.tree.addTopLevelItem(item);return
        full=w.selector_full.isChecked();groups={};aggregates={}
        def group(hierarchy):
            parent=w.tree.invisibleRootItem()
            for depth,label in enumerate(hierarchy):
                key=hierarchy[:depth+1]
                if key not in groups:
                    node=QTreeWidgetItem(parent,[label]);groups[key]=node;aggregates[key]=set()
                    d={'origin':owner.uid,'path':'@selector/'+'/'.join(key),'kind':'resource_group','name':label,'resource_paths':[]}
                    node.setData(0,ROLE,d);node.setFlags(node.flags()&~Qt.ItemFlag.ItemIsDragEnabled)
                    w.tree_items[w.descriptor_key(d)]=node
                parent=groups[key]
            return parent
        top=list(TOP)
        if full:top[top.index('准心')]='icons';top[top.index('天空')]='贴图';top.append('其他')
        for label in top:group((label,))
        version=source_version(owner,w.working_version)
        atlases={path for path in owner.files if path.lower().endswith('.png') and grouped_parts(path,owner.asset_versions.get(path,version))}
        for obj in entries(owner,source_version(owner,w.working_version),full):
            if obj['preview'] in atlases:continue
            hierarchy=obj['category'];paths=obj['paths'];label=obj['name']
            parent=group(hierarchy)
            d={'origin':owner.uid,'path':'@object/'+obj['id'],'kind':'game_object','name':label,'name_en':obj.get('name_en'),'object_id':obj['id'],'object_paths':paths,'preview_path':obj['preview'],'state_roots':obj.get('state_roots',[]),'texture_states':obj.get('texture_states',[])}
            d['resolved_states']=obj.get('resolved_states',[])
            child=QTreeWidgetItem(parent,[label]);child.setData(0,ROLE,d);child.setToolTip(0,obj['id']+'\n来源：'+owner.name+'\n'+str(len(paths))+' 个关联文件')
            if d['resolved_states']:child.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            w.tree_items[w.descriptor_key(d)]=child
            for depth in range(len(hierarchy)):aggregates[hierarchy[:depth+1]].update(paths)
        for path in sorted(atlases):
            hierarchy=('粒子',) if '/particle/' in path else ('实体',) if '/entity/' in path or '/models/armor/' in path else ('icons',) if full else ('界面组件',)
            if hierarchy==('实体',):
                from .selector_taxonomy import entity_category
                hierarchy=entity_category(path)
            parent=group(hierarchy);label=describe(path)['name']
            descriptor={'origin':owner.uid,'path':path,'kind':'png','name':label}
            node=QTreeWidgetItem(parent,[label]);node.setData(0,ROLE,descriptor);node.setToolTip(0,path)
            w.tree_items[w.descriptor_key(descriptor)]=node
            # Same regions, names, semantic IDs and grouped component descriptors as file tree.
            w.populate_components(node,descriptor)
            for depth in range(len(hierarchy)):aggregates[hierarchy[:depth+1]].add(path)
        if not full:
            # The old crosshair is an actual region, never a full icons.png selection.
            version=source_version(owner,w.working_version)
            for path in owner.files:
                if not path.endswith('/gui/icons.png'):continue
                version=owner.asset_versions.get(path,version)
                part=next((p for p in parts(path,version) if 'crosshair' in p['code']),None)
                if part:
                    parent=groups[('准心',)]
                    d={'origin':owner.uid,'path':path,'kind':'component','name':part['name'],'regions':part['regions']}
                    child=QTreeWidgetItem(parent,[part['name']]);child.setData(0,ROLE,d);w.tree_items[w.descriptor_key(d)]=child
                    parent.setData(0,ROLE,{**d,'name':'准心'})
        sounds=[p for p in owner.files if p.lower().endswith('.ogg')]
        for path in sorted(sounds):
            hierarchy=('音效',);parent=group(hierarchy)
            d={'origin':owner.uid,'path':path,'kind':'file','name':path.rsplit('/',1)[-1]}
            node=QTreeWidgetItem(parent,[d['name']]);node.setData(0,ROLE,d);node.setToolTip(0,path)
            w.tree_items[w.descriptor_key(d)]=node;aggregates[hierarchy].add(path)
        # Remove empty leaves first so parents with no usable descendants also vanish.
        for key,node in reversed(list(groups.items())):
            if node.childCount():continue
            d=node.data(0,ROLE)
            w.tree_items.pop(w.descriptor_key(d),None)
            parent=node.parent() or w.tree.invisibleRootItem()
            parent.takeChild(parent.indexOfChild(node))
            groups.pop(key)
        for key,node in groups.items():
            d=node.data(0,ROLE)
            if d['kind']=='resource_group':
                d['resource_paths']=sorted(aggregates[key]);node.setData(0,ROLE,d)
            if key in getattr(w,'friendly_expansion',set()):node.setExpanded(True)
        filter(w)
    finally:
        del tree_block,stack_block;w.refreshing=False


def expand_states(w,item):
    d=item.data(0,ROLE) or {}
    if d.get('kind')!='game_object' or not d.get('resolved_states') or item.childCount():return
    owner=w.source(d['origin'])
    if owner is None:return
    for state in d['resolved_states']:
        child_d={**d,'path':d['path']+'/state/'+state['id'],'name':d['name']+' · '+state['name'],
                 'object_paths':state['paths'],'preview_path':state['preview'],'state_roots':[],'texture_states':[],'resolved_states':[],
                 'state_models':state['models'],'state_condition':state['condition'],'state_multipart':state['multipart'],
                 'state_texture_only':state['id'].startswith('texture:'),
                 'export_object_paths':d['object_paths']}
        node=QTreeWidgetItem(item,[state['name']]);node.setData(0,ROLE,child_d)
        node.setToolTip(0,state['root']+'\n'+state['condition']+'\n'+'\n'.join(state['models']))
        w.tree_items[w.descriptor_key(child_d)]=node
    item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicatorWhenChildless)


def filter(w):
    query=w.search.text().strip().lower()
    def visit(item,parent_match=False):
        d=item.data(0,ROLE) or {}
        text=item.text(0)+' '+d.get('path','')+' '+(d.get('name_en') or '')
        from .localization import item_text
        text+=' '+item_text(item.text(0),'en',d)
        if d.get('kind')=='game_object':text+=' '+' '.join(d.get('object_paths',[]))
        if d.get('kind')=='png':text+=' '+describe(d['path'])['search']
        match=parent_match or not query or query in text.lower()
        children=[visit(item.child(i),match) for i in range(item.childCount())]
        item.setHidden(not (match or any(children)))
        if query and any(children):item.setExpanded(True)
        return match or any(children)
    for n in range(w.tree.topLevelItemCount()):visit(w.tree.topLevelItem(n))
