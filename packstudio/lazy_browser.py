"""Path-only library index with on-demand Qt rows; no image decoding to index/search."""
from collections import defaultdict
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import QTreeWidgetItem, QListWidgetItem
from .core import Layer
from .versions import VERSIONS, source_version
from .semantics import describe, parts, hidden_terms, variant_id
from .library_browser import builtin_version

ROLE = Qt.ItemDataRole.UserRole


class ItemMap(dict):
    """Stable descriptor lookup may materialize a path without expanding its parents."""
    def __init__(self, browser):
        super().__init__()
        self.browser = browser

    def __missing__(self, key):
        item = self.browser.locate(key)
        if item is None:
            raise KeyError(key)
        return item

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default


class LibraryIndex:
    def __init__(self, window):
        self.w = window
        self.index = {}
        self.cache = {}
        self.rows = {}
        self.loaded = set()
        self.normal_expanded = set()
        self.filter_key = None
        self.index_builds = 0
        self.search_cache = {}

    def refresh(self):
        w = self.w
        if self.filter_key and not self.filter_key[0]:
            self.normal_expanded = {k for k, i in w.tree_items.items() if i.isExpanded()}
        chosen = w.vanilla_version.currentData()
        sources = list(w.sources)
        if w.defaults.isChecked():
            for version in VERSIONS if chosen == 'all' else [builtin_version(w)]:
                sources.append(Layer(w.tr('原版资源', 'Vanilla resources')+' '+version,
                                     {p: None for p in w.vanilla.paths(version)},
                                     uid='@vanilla:'+version, source_version=version, read_only=True))
        self.sources = {s.uid: s for s in sources}
        self.index = {}
        for source in sources:
            paths = tuple(source.files) if source.kind != 'component' else ()
            cached = self.cache.get(source.uid)
            if cached is None or cached[0] != paths:
                descriptors = {'': {'origin': source.uid, 'path': '', 'kind': 'root', 'name': source.name}}
                children = defaultdict(list)
                for path in sorted(paths):
                    segments = path.split('/')
                    for n in range(1, len(segments)+1):
                        prefix = '/'.join(segments[:n])
                        if prefix in descriptors:
                            continue
                        parent = '/'.join(segments[:n-1])
                        kind = 'folder' if n < len(segments) else 'png' if path.lower().endswith('.png') else 'file'
                        descriptors[prefix] = {'origin': source.uid, 'path': prefix, 'kind': kind, 'name': segments[n-1]}
                        children[parent].append(prefix)
                cached = (paths, descriptors, children)
                self.cache[source.uid] = cached
                self.index_builds += 1
            cached[1]['']['name'] = source.name
            self.index[source.uid] = cached[1:]
        self.cache = {uid: value for uid, value in self.cache.items() if uid in self.sources}
        # Names, tags, source versions and paths may change between explicit refreshes.
        self.search_cache.clear()
        self.filter_key = None
        self.filter()

    def version(self, d):
        owner = self.sources[d['origin']]
        return owner.asset_versions.get(d['path'], source_version(owner, self.w.working_version))

    def make(self, origin, path):
        key = (origin, path)
        if key in self.rows:
            return self.rows[key]
        descriptors, children = self.index[origin]
        d = dict(descriptors[path])
        owner = self.sources[origin]
        label = d['name']
        if not path:
            if sum(s.name == owner.name for s in self.sources.values()) > 1:
                label += ' (from '+self.w.origin_label(owner)+') ['+origin[:6]+']'
            item = QTreeWidgetItem([label])
            self.w.tree.addTopLevelItem(item)
        else:
            parent = self.make(origin, path.rsplit('/', 1)[0] if '/' in path else '')
            item = QTreeWidgetItem(parent, [label])
        item.setData(0, ROLE, d)
        item.setToolTip(0, path+'\nfrom '+self.w.origin_label(owner))
        if path.lower().endswith('.ogg'):
            from PySide6.QtWidgets import QStyle
            item.setIcon(0,self.w.tree.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume))
            item.setToolTip(0,self.w.tr('OGG 音效 · 点击预览／替换','OGG sound · Click to preview / replace')+'\n'+path)
        self.rows[key] = item
        self.w.tree_items[self.w.descriptor_key(d)] = item
        if d['kind'] == 'png':
            info = describe(path)
            d['semantic_id'] = variant_id(path, self.version(d))
            item.setData(0, ROLE, d)
            item.setToolTip(0, info['name']+'\n'+path+'\nfrom '+self.w.origin_label(owner))
            expandable = bool(self.w.component_rules(d))
        else:
            expandable = bool(children.get(path))
        if expandable:
            item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
        return item

    def locate(self, key):
        origin, kind, path, _ = key
        if origin not in self.index or path not in self.index[origin][0]:
            return None
        item = self.make(origin, path)
        if kind == 'component':
            self.w.populate_components(item, item.data(0, ROLE))
            return dict.get(self.w.tree_items, key)
        return item

    def allowed(self, d):
        return self.eligible is None or d['path'] in self.eligible.get(d['origin'],set())

    def populate(self, item):
        d = item.data(0, ROLE) or {}
        if d.get('kind') not in ('folder', 'root'):
            return False
        key = (d['origin'], d['path'])
        if key in self.loaded:
            return True
        self.loaded.add(key)
        descriptors, children = self.index[d['origin']]
        for path in children.get(d['path'], ()):
            if self.allowed(descriptors[path]):
                self.make(d['origin'], path)
        if hasattr(self.w, 'restore_library_order'):
            self.w.restore_library_order(item)
        return True

    def terms(self, d):
        key = (d['origin'], d['path'])
        if key not in self.search_cache:
            text = d['path'].lower()+' '+d['name'].lower()
            component_terms = ''
            if d['kind'] == 'png':
                info = describe(d['path'])
                text += ' '+info['search']
                component_terms = ' '.join(p['name']+' '+p['code']+' '+hidden_terms(p['code'])
                                           for p in parts(d['path'], self.version(d))).lower()
                component_terms += ' '+' '.join(n.lower() for n, _ in self.w.component_rules(d))
            self.search_cache[key] = (text, component_terms)
        return self.search_cache[key]

    def filter(self):
        w = self.w
        query = w.search.text().strip().lower()
        versions = set()
        if w.vanilla_version.currentData() in VERSIONS:
            versions = {w.vanilla_version.currentData()}
        # File-tree search is global; choosing a replacement source must not scope it.
        scope = None
        key = (query, frozenset(versions), (scope['origin'], scope['path']) if scope else None)
        if key == self.filter_key:
            return
        if self.filter_key and not self.filter_key[0]:
            self.normal_expanded = {k for k, i in w.tree_items.items() if i.isExpanded()}
        self.filter_key = key
        self.eligible=None
        if versions or scope:
            self.eligible={}
            for origin,(descriptors,_) in self.index.items():
                if scope and origin!=scope['origin']:continue
                owner=self.sources[origin];allowed=set()
                for path,d in descriptors.items():
                    if d['kind'] in ('root','folder'):continue
                    if scope and scope['path'] and not (path==scope['path'] or path.startswith(scope['path']+'/')):continue
                    if versions and owner.asset_versions.get(path,owner.source_version) not in versions:continue
                    allowed.add(path);parent=path
                    while parent:
                        parent=parent.rsplit('/',1)[0] if '/' in parent else '';allowed.add(parent)
                self.eligible[origin]=allowed
        blocker = QSignalBlocker(w.tree)
        w.tree.clear()
        w.tree_items = ItemMap(self)
        self.rows = {}
        self.loaded = set()
        for origin, (descriptors, children) in self.index.items():
            if not query:
                if self.allowed(descriptors['']):
                    self.make(origin, '')
                continue
            matched_folders = set()
            if query in (self.sources[origin].name+' '+self.sources[origin].source).lower() and self.allowed(descriptors['']):
                self.make(origin,'')
                continue
            for path, d in descriptors.items():
                if not path or any(path.startswith(folder+'/') for folder in matched_folders):
                    continue
                text, component_terms = self.terms(d)
                if (query not in text and query not in component_terms) or not self.allowed(d):
                    continue
                item = self.make(origin, path)
                if d['kind'] == 'folder':
                    matched_folders.add(path)
                if query in component_terms:
                    w.populate_components(item, item.data(0, ROLE))
                    def filter_part(node, parent_match=False):
                        data=node.data(0,ROLE) or {}
                        match=parent_match or query in (node.text(0)+' '+data.get('semantic_id','')+' '+hidden_terms(data.get('semantic_id',''))).lower()
                        children=[filter_part(node.child(i),match) for i in range(node.childCount())]
                        visible=match or any(children);node.setHidden(not visible)
                        if any(children):node.setExpanded(True)
                        return visible
                    for n in range(item.childCount()):filter_part(item.child(n),query in text)
                    item.setExpanded(True)
                parent = item.parent()
                while parent:
                    parent.setExpanded(True)
                    parent = parent.parent()
        if not query:
            for descriptor_key in sorted(self.normal_expanded, key=lambda k: k[2].count('/')):
                origin, _, path, _ = descriptor_key
                if origin not in self.index or path not in self.index[origin][0] or not self.allowed(self.index[origin][0][path]):
                    continue
                item = self.locate(descriptor_key)
                if item:
                    if not self.populate(item):
                        w.populate_components(item, item.data(0, ROLE))
                    item.setExpanded(True)
        del blocker


def refresh(w):
    if not hasattr(w, '_library_index'):
        w._library_index = LibraryIndex(w)
    w.selection_timer.stop()
    w.pending_resource = None
    w.refreshing = True
    blocker = QSignalBlocker(w.stack)
    try:
        selected = {i.data(ROLE) for i in w.stack.selectedItems()}
        w.stack.clear()
        for layer in w.layers:
            item = QListWidgetItem(layer.name)
            item.setData(ROLE, layer.uid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if layer.enabled else Qt.CheckState.Unchecked)
            w.stack.addItem(item)
            item.setSelected(layer.uid in selected)
        w._library_index.refresh()
    finally:
        del blocker
        w.refreshing = False
