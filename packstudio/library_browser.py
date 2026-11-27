"""Presentation-only semantic browser; descriptors still point at original pixels."""
from collections import defaultdict
from pathlib import Path
from PySide6.QtCore import Qt,QSize,QPointF
from PySide6.QtGui import QIcon,QPixmap,QPainter,QPolygonF,QTransform,QColor
from PySide6.QtWidgets import QComboBox,QToolButton,QMenu,QHBoxLayout,QTreeWidgetItem,QStyle
from .semantics import describe,category,block_category,grouped_parts,GROUPS,part_group,part_name,variant_id,animation_family,particle_usage
from .versions import VERSIONS,source_version
from .core import decode

def install(window):
    w=window;layout=w.search.parentWidget().layout();row=QHBoxLayout()
    w.library_mode=QComboBox();w.library_mode.addItems([w.tr('文件树','File tree'),w.tr('选择器','Selector')]);w.library_mode.setMinimumContentsLength(4);w.library_mode.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);row.addWidget(w.library_mode)
    layout.insertLayout(1,row)
    w.vanilla_version=QComboBox();w.vanilla_version.addItem(w.tr('全版本','All versions'),'all')
    for version in VERSIONS:w.vanilla_version.addItem(version,version)
    w.vanilla_version.setToolTip('按素材源版本筛选；未知版本只在全版本显示。')
    def change_original():
        if (w.current_source or '').startswith('@vanilla'):w.clear_editor()
        w._category_icons={};w.refresh()
    layout.insertWidget(3,w.vanilla_version);w.vanilla_version.currentTextChanged.connect(change_original)
    w.library_mode.currentIndexChanged.connect(lambda:mode_changed(w))
    w.tree.setIconSize(QSize(24,24));w._category_icons={}
    from .selector import install as install_selector,mode_changed
    install_selector(w,layout)

def builtin_version(w,origin=None):
    origin=origin if origin is not None else (getattr(w,'current_source','') or '')
    if origin.startswith('@vanilla:'):return origin.split(':',1)[1]
    selected=w.vanilla_version.currentData() if hasattr(w,'vanilla_version') else None
    return selected if selected in VERSIONS else w.working_version

def source_versions(w,d):
    if d.get('origin','').startswith('@vanilla'):return {builtin_version(w,d['origin'])}
    owner=w.source(d.get('origin'))
    if owner is None:return set()
    paths=[b['path'] for b in d.get('bindings',[])] or [d.get('path','')]
    return {v for p in paths if (v:=owner.asset_versions.get(p,owner.source_version)) in VERSIONS}

def category_icon(w,name):
    if name in w._category_icons:return w._category_icons[name]
    if not any(key in name for key in ('方块','物品','实体','GUI','粒子','贴图','子集')):
        return w.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
    version=builtin_version(w);path='assets/minecraft/textures/'
    target='block/stone.png' if '方块' in name else 'item/diamond_sword.png' if '物品' in name else 'entity/creeper/creeper.png' if '实体' in name else 'gui/sprites/hud/crosshair.png' if name=='GUI' else 'environment/sun.png' if '贴图' in name else 'item/book.png' if '子集' in name else 'particle/critical_hit.png'
    data=w.vanilla.get(version,path+target) or w.vanilla.get('1.21.11',path+target)
    if not data:return w.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
    im=decode(data);pix=QPixmap(32,32);pix.fill(Qt.GlobalColor.transparent);p=QPainter(pix)
    if '方块' in name:
        # Project the real stone texture onto three faces, no generated artwork.
        source=QPolygonF([QPointF(0,0),QPointF(im.width(),0),QPointF(im.width(),im.height()),QPointF(0,im.height())])
        for pts,shade in [([(16,1),(30,8),(16,15),(2,8)],0), ([(2,8),(16,15),(16,31),(2,24)],70), ([(16,15),(30,8),(30,24),(16,31)],35)]:
            dest=QPolygonF([QPointF(*q) for q in pts]);transform=QTransform();QTransform.quadToQuad(source,dest,transform)
            p.save();p.setTransform(transform);p.drawImage(0,0,im);p.fillRect(im.rect(),QColor(0,0,0,shade));p.restore()
    elif '实体' in name:p.drawImage(4,4,im.copy(8,8,8,8).scaled(24,24))
    else:p.drawImage(2,2,im.scaled(28,28,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation))
    p.end();icon=QIcon(pix);w._category_icons[name]=icon;return icon

def synthetic(w,parent,label):
    item=QTreeWidgetItem([label]);parent.addChild(item)
    item.setData(0,Qt.ItemDataRole.UserRole,{'origin':'@category','path':label,'kind':'folder','name':label})
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled & ~Qt.ItemFlag.ItemIsSelectable)
    item.setIcon(0,category_icon(w,label));return item

def copy_item(source,parent):
    item=QTreeWidgetItem(parent,[source.text(0)])
    item.setData(0,Qt.ItemDataRole.UserRole,source.data(0,Qt.ItemDataRole.UserRole))
    item.setToolTip(0,source.toolTip(0));item.setIcon(0,source.icon(0))
    item.setChildIndicatorPolicy(source.childIndicatorPolicy())
    for i in range(source.childCount()):copy_item(source.child(i),item)
    return item

def expansion_paths(tree):
    result=set();todo=[(tree.topLevelItem(i),()) for i in range(tree.topLevelItemCount())]
    while todo:
        node,prefix=todo.pop();path=prefix+(node.text(0),)
        if node.isExpanded():result.add(path)
        todo.extend((node.child(i),path) for i in range(node.childCount()))
    return result

def restore_expansion(tree,paths):
    todo=[(tree.topLevelItem(i),()) for i in range(tree.topLevelItemCount())]
    while todo:
        node,prefix=todo.pop();path=prefix+(node.text(0),)
        if path in paths:node.setExpanded(True)
        todo.extend((node.child(i),path) for i in range(node.childCount()))

def quiet_category(path):
    p=path.lower();stem=Path(p).stem
    if any(t in p for t in ('/gui/title/','/gui/background','/mcpatcher/sky/','/optifine/sky/','/environment/','/colormap/','/lightmap/','/shaders/')) or any(t in stem for t in ('panorama','background','vignette','lightmap')):
        return '背景与光影 / Backgrounds and lighting'
    if '/mcpatcher/' in p or '/optifine/' in p or '/misc/' in p or '/effect/' in p:
        return '其他效果贴图 / Other effect textures'
    return None

def normalize_friendly(w,subsets):
    # Sources within Particles use one semantic hierarchy, regardless of atlas/sprites.
    categories=[subsets.child(i) for i in range(subsets.childCount())]
    for category_node in categories:
        if not category_node.text(0).startswith('粒子'):continue
        for i in range(category_node.childCount()):
            source=category_node.child(i);children=source.takeChildren();groups={};sheets=[]
            def group(label):
                if label not in groups:groups[label]=synthetic(w,source,label)
                return groups[label]
            for child in children:
                d=child.data(0,Qt.ItemDataRole.UserRole) or {};path=d.get('path','')
                if d.get('kind')=='png' and path.endswith('/particle/particles.png'):
                    w.populate_components(child,d)
                    for section in child.takeChildren():
                        parent=group(section.text(0));section.setText(0,'图集区域 / Atlas regions');parent.addChild(section)
                    child.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator);sheets.append(child)
                elif d.get('origin')=='@category' and child.text(0)=='其他 / Other':
                    for entry in child.takeChildren():group(GROUPS['other']).addChild(entry)
                else:
                    kind=part_group(path)
                    if d.get('bindings'):
                        kind=part_group(d['bindings'][0]['path'])
                    group(GROUPS[kind]).addChild(child)
            if sheets:
                parent=group('完整图集 / Complete atlases')
                for sheet in sheets:parent.addChild(sheet)
    # Keep visually noisy images out of the main list, at the end of each source.
    todo=[subsets]
    while todo:
        node=todo.pop();children=[node.child(i) for i in range(node.childCount())];buckets={}
        for child in children:
            d=child.data(0,Qt.ItemDataRole.UserRole) or {}
            label=quiet_category(d.get('path','')) if d.get('kind')=='png' else None
            if label and node.text(0)!=label:
                if label not in buckets:buckets[label]=synthetic(w,node,label)
                node.takeChild(node.indexOfChild(child));buckets[label].addChild(child)
            elif child.childCount():todo.append(child)
        for bucket in buckets.values():
            node.takeChild(node.indexOfChild(bucket));node.addChild(bucket);bucket.setExpanded(False)

def decorate(w):
    if not hasattr(w,'library_mode'):return
    from .selector import controls
    controls(w)
    if w.library_mode.currentIndex()==1:return
    friendly=w.library_mode.currentIndex()==1
    for key,item in list(w.tree_items.items()):
        d=item.data(0,Qt.ItemDataRole.UserRole) or {}
        if d.get('kind')=='png':
            info=describe(d['path']);owner=w.source(d['origin']);version=source_version(owner,w.working_version) if owner else builtin_version(w,d['origin'])
            if owner:version=owner.asset_versions.get(d['path'],version)
            code=variant_id(d['path'],version);d['semantic_id']=code;item.setData(0,Qt.ItemDataRole.UserRole,d)
            item.setToolTip(0,info['name']+'\n布局版本 / Layout: '+version+'\n'+d['path'])
            if friendly:item.setText(0,info['name'])
    if not friendly:return
    roots=w.tree.takeTopLevelItem(0) if w.tree.topLevelItemCount() else None
    originals=[]
    if roots:originals.append(roots)
    while w.tree.topLevelItemCount():originals.append(w.tree.takeTopLevelItem(0))
    w._semantic_original_roots=originals
    invisible=w.tree.invisibleRootItem();packs=synthetic(w,invisible,'完整材质包 / Complete packs');subsets=synthetic(w,invisible,'子集 / Subsets')
    all_categories={};collections={};source_categories=[]
    for root in originals:
        d=root.data(0,Qt.ItemDataRole.UserRole);owner=w.source(d['origin']);paths=owner.files if owner else w.vanilla.paths(builtin_version(w,d['origin']))
        complete=any(p.endswith('pack.mcmeta') for p in paths) and any('/textures/' in p for p in paths)
        if complete:packs.addChild(root)
        leaves=[];todo=[root]
        while todo:
            item=todo.pop();desc=item.data(0,Qt.ItemDataRole.UserRole) or {}
            if desc.get('kind')=='png':leaves.append(item)
            else:todo.extend(item.child(i) for i in range(item.childCount()))
        leaves.sort(key=lambda item:(animation_family(item.data(0,Qt.ItemDataRole.UserRole)['path']) or ('','',0)))
        for item in leaves:
            desc=item.data(0,Qt.ItemDataRole.UserRole);cat=category(desc['path']);code=describe(desc['path'])['code']
            hierarchy=[cat]+([block_category(code)] if cat.startswith('方块') else [])+[root.text(0)]
            parent=subsets;prefix=()
            for level,label in enumerate(hierarchy):
                # Different packs can have identical display names. Keep their
                # children separate using the source identity, never the label.
                prefix+= (d['origin'] if level==len(hierarchy)-1 else label,)
                if prefix not in all_categories:all_categories[prefix]=synthetic(w,parent,label)
                parent=all_categories[prefix]
            marker=parent.data(0,Qt.ItemDataRole.UserRole)
            marker={**marker,'whole_pack':complete};parent.setData(0,Qt.ItemDataRole.UserRole,marker)
            if not any(origin==d['origin'] and node is parent for origin,titles,node in source_categories):
                source_categories.append((d['origin'],hierarchy[:-1],parent))
            group=part_group(desc['path'])
            family=animation_family(desc['path'])
            if group=='other' and family:
                prefix+=('其他 / Other',)
                if prefix not in all_categories:all_categories[prefix]=synthetic(w,parent,'其他 / Other')
                parent=all_categories[prefix]
            if (group!='other' or family) and ('/gui/sprites/' in desc['path'] or '/particle/' in desc['path'] and not desc['path'].endswith('/particles.png')):
                group_label=family[1]+' · 动画帧' if family else GROUPS[group]
                if family:group='animation:'+family[0]
                key=(d['origin'],tuple(hierarchy[:-1]),group)
                if key not in collections:
                    node=QTreeWidgetItem([group_label]);parent.addChild(node);collections[key]=node
                    node.setData(0,Qt.ItemDataRole.UserRole,{**desc,'kind':'component','name':group_label,'bindings':[],'regions':[]})
                parent=collections[key];data=parent.data(0,Qt.ItemDataRole.UserRole)
                data['bindings'].append({'path':desc['path'],'region':[0,0,1,1]});data['regions'].append([0,0,1,1]);parent.setData(0,Qt.ItemDataRole.UserRole,data)
            child=copy_item(item,parent)
            if group!='other' and ('/gui/sprites/' in desc['path'] or '/particle/' in desc['path']):child.setText(0,part_name(desc['path']))
            if family:
                child.setText(0,describe(desc['path'])['name'])
                version=source_version(owner,w.working_version) if owner else builtin_version(w,d['origin'])
                usage=particle_usage(version).get(Path(desc['path']).stem,'尚未在粒子定义中找到引用')
                child.setToolTip(0,child.toolTip(0)+'\n触发效果 ID / Used by: '+usage)
            # A subset retains the exact resource descriptor, not a detached image.
            if not complete:w.tree_items[w.descriptor_key(desc)]=child
    normalize_friendly(w,subsets)
    w._friendly_original_children=[]
    for i in range(packs.childCount()):
        root=packs.child(i);origin=root.data(0,Qt.ItemDataRole.UserRole)['origin'];w._friendly_original_children.extend(root.takeChildren());destinations={}
        for source_origin,titles,node in source_categories:
            if source_origin!=origin:continue
            parent=root
            for depth,title in enumerate(titles):
                key=tuple(titles[:depth+1])
                if key not in destinations:destinations[key]=synthetic(w,parent,title)
                parent=destinations[key]
            for child in range(node.childCount()):copy_item(node.child(child),parent)
    packs.setExpanded(True);subsets.setExpanded(True)
    from .browser_icons import decorate_folders
    decorate_folders(w)
    restore_expansion(w.tree,getattr(w,'friendly_expansion',set()))
    # Discard descriptors belonging to detached original trees before Qt frees them.
    w.tree_items={};todo=[packs,subsets]
    while todo:
        node=todo.pop();d=node.data(0,Qt.ItemDataRole.UserRole)
        if d and d['origin']!='@category':w.tree_items[w.descriptor_key(d)]=node
        todo.extend(node.child(i) for i in range(node.childCount()))

def populate_parts(w,item,d):
    if d.get('kind')!='png' or item.childCount():return False
    owner=w.source(d['origin']);v=source_version(owner,w.working_version) if owner else builtin_version(w,d['origin'])
    if owner:v=owner.asset_versions.get(d['path'],v)
    groups=grouped_parts(d['path'],v)
    if not groups:return False
    raw=owner.files.get(d['path']) if owner else w.vanilla.get(v,d['path'])
    atlas=decode(raw) if raw else None
    for group,parts in groups.items():
        regions=[r for part in parts for r in part['regions']]
        label=GROUPS[group];data={**d,'kind':'component','name':label,'regions':regions}
        parent=QTreeWidgetItem([label]);item.addChild(parent);parent.setData(0,Qt.ItemDataRole.UserRole,data);w.tree_items[w.descriptor_key(data)]=parent
        for part in parts:
            data={**d,'kind':'component','name':part['name'],'regions':part['regions'],'semantic_id':part['code']}
            child=QTreeWidgetItem([part['name']]);parent.addChild(child);child.setData(0,Qt.ItemDataRole.UserRole,data);child.setToolTip(0,part['name']);w.tree_items[w.descriptor_key(data)]=child
            if atlas:
                from .core import pixel_rect
                icon=QIcon(QPixmap.fromImage(atlas.copy(*pixel_rect(part['regions'][0],atlas)).scaled(24,24,Qt.AspectRatioMode.KeepAspectRatio)))
                child.setIcon(0,icon)
                if parent.icon(0).isNull():parent.setIcon(0,icon)
    return True

def filter_library(w):
    query=w.search.text().strip().lower();versions=set()
    selected=w.vanilla_version.currentData() if hasattr(w,'vanilla_version') else None
    if selected in VERSIONS:versions={selected}
    scope=getattr(w,'library_search_scope',None) if query else None
    def visit(item,parent_match=False):
        d=item.data(0,Qt.ItemDataRole.UserRole) or {};kind=d.get('kind');path=d.get('path','')
        info=describe(path) if kind=='png' else None
        from .semantics import hidden_terms,parts
        tags=hidden_terms(d.get('semantic_id',''))
        match=parent_match or not query or query in item.text(0).lower() or query in path.lower() or bool(info and query in info['search']) or bool(query and query in tags)
        if query and kind=='png':
            owner=w.source(d['origin']);version=source_version(owner,w.working_version) if owner else builtin_version(w,d['origin'])
            if owner:version=owner.asset_versions.get(path,version)
            if any(query in n.lower() for n,r in w.component_rules(d)) or any(query in hidden_terms(part['code']) for part in parts(path,version)):
                w.populate_components(item,d)
        allowed=not scope or (d.get('origin')==scope['origin'] and (not scope['path'] or path==scope['path'] or path.startswith(scope['path']+'/')))
        if versions and kind not in ('root','folder'):
            allowed=allowed and bool(versions & source_versions(w,d))
        children=[visit(item.child(i),match) for i in range(item.childCount())]
        visible=(match and allowed and d.get('origin')!='@category') or any(children)
        if versions and kind not in ('root','folder'):visible=visible and allowed
        if (query or versions) and kind in ('root','folder'):visible=any(children)
        if versions and kind=='root':visible=visible and bool(versions & source_versions(w,d))
        item.setHidden(not visible)
        if query and any(children):item.setExpanded(True)
        return visible
    for i in range(w.tree.topLevelItemCount()):visit(w.tree.topLevelItem(i))

def confirm_resolution(w,d):
    if d.get('kind')!='component':return True
    if d.get('bindings'):
        return all(confirm_resolution(w,{**d,'path':b['path'],'regions':[b['region']],'bindings':[]}) for b in d['bindings'])
    from .core import compose,pixel_rect
    from PySide6.QtWidgets import QMessageBox
    owner=w.source(d['origin']);data=owner.files.get(d['path']) if owner else w.vanilla.get(builtin_version(w,d['origin']),d['path'])
    if not data:return True
    source=decode(data);files,_=compose(w.layers,w.vanilla,w.working_version)
    target=files.get(d['path']) or w.vanilla.get(w.working_version,d['path'])
    if not target:return True
    target=decode(target)
    sizes=[(pixel_rect(r,source)[2:],pixel_rect(r,target)[2:]) for r in d.get('regions',[])]
    if all(a==b for a,b in sizes):return True
    return QMessageBox.question(w,'组件分辨率 / Component resolution',
        '组件与下层图集的分辨率不同。是否按较高清的一方合成？\n高清组件：先放大下层整张图集；高清图集：放大组件。\n使用最近邻，不缩小高清内容、不平滑。取消将不加入项目。\n'+str(sizes[:4]),
        QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)==QMessageBox.StandardButton.Yes
