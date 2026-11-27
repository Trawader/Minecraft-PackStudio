"""Read-only explanations grounded in selected source files, never game simulation."""
import copy
import json
import struct
from PySide6.QtCore import Qt,QSignalBlocker
from PySide6.QtWidgets import (QDockWidget,QWidget,QVBoxLayout,QLabel,QTreeWidget,QTreeWidgetItem,QAbstractItemView,QSplitter,QStyle,
    QCheckBox,QTabWidget,QPlainTextEdit,QFrame)
from .resource_graph import graph_for
from .texture_animation import timeline
from .versions import source_version,records


CONFIG_SUFFIXES=('.json','.properties','.mcmeta','.json5','.jem','.jpm','.cfg','.txt','.yaml','.yml','.toml','.xml','.ini')
PROPERTY_LABELS={'type':'资源类型','items':'匹配物品','matchItems':'匹配物品',
    'matchBlocks':'匹配方块','damage':'损伤条件','damageMask':'损伤掩码',
    'stackSize':'堆叠数量条件','enchantmentIDs':'附魔条件','enchantmentLevels':'附魔等级条件',
    'hand':'手持位置','biomes':'生物群系条件','heights':'高度条件','weight':'权重',
    'texture':'纹理引用','model':'模型引用','tiles':'贴图条目','method':'连接方式'}


def literal(value):
    text=json.dumps(value,ensure_ascii=False) if not isinstance(value,str) else value
    return text if len(text)<=2000 else text[:2000]+'…（完整值见原始配置）'


def describe_config(path,raw,graph,files):
    lines=['配置：'+path,'以下为文件中实际声明的值；条件是否在游戏中生效尚未验证。','']
    if path.endswith('.properties'):
        values=graph.conditions.get(path,{})
        if not values:lines.append('未解析到属性；请查看原始配置。')
        for key,value in list(values.items())[:300]:
            label=PROPERTY_LABELS.get(key)
            if label is None and key.startswith('nbt.'):label='NBT 匹配条件'
            if label is None and key.startswith('components.'):label='组件匹配条件'
            lines.append(f'{label or "其他声明（未解释）"} · {key} = {literal(value)}')
        if len(values)>300:lines.append('属性摘要仅展示前 300 项。')
    elif path.endswith(('.json','.mcmeta')):
        try:data=json.loads(raw.decode('utf-8-sig'))
        except (ValueError,UnicodeError):return '\n'.join(lines+['无法解析 JSON；不修改原文件，原始内容仍可查看。'])
        if not isinstance(data,dict):return '\n'.join(lines+['顶层不是配置对象；仅提供原始内容。'])
        if 'parent' in data:lines.append('父模型声明：'+literal(data['parent']))
        overrides=data.get('overrides')
        if isinstance(overrides,list):
            for i,row in enumerate(overrides[:100]):
                if isinstance(row,dict):
                    lines.append(f'覆盖条目 {i+1}：条件 '+literal(row.get('predicate',{}))+' → 模型 '+literal(row.get('model','未声明')))
            if len(overrides)>100:lines.append('覆盖条件摘要仅展示前 100 项。')
        # Modern item definitions contain nested dispatch/condition nodes. Show their
        # declared discriminators without inventing precedence or server semantics.
        todo=[('$',data)];visited=0
        while todo and visited<500:
            location,value=todo.pop();visited+=1
            if isinstance(value,dict):
                fields={k:value[k] for k in ('type','property','component','predicate','when','threshold','model') if k in value}
                if fields:lines.append(location+'：'+literal(fields))
                todo.extend((location+'.'+str(k),v) for k,v in reversed(list(value.items())) if isinstance(v,(dict,list)))
            elif isinstance(value,list):todo.extend((location+f'[{i}]',value[i]) for i in range(min(len(value),500)-1,-1,-1))
        if todo:lines.append('嵌套结构摘要已截断，完整内容见原始配置。')
        if path.lower().endswith('.png.mcmeta') and 'animation' in data:
            png=files.get(path[:-7],b'')
            if len(png)>=24 and png.startswith(b'\x89PNG\r\n\x1a\n'):
                width,height=struct.unpack('>II',png[16:24])
                try:
                    if not width or not height:raise ValueError('PNG 尺寸无效')
                    frames,interpolate=timeline(raw,width,height)
                    lines.append(f'二维动画：{len(frames)} 个序列条目，{sum(row[2] for row in frames)} tick／循环。')
                    if interpolate:lines.append('声明插值；当前画板只做逐帧预览，原配置保留。')
                    lines.append('在底部资源栏双击对应 PNG，可选择、编辑和播放帧。')
                except ValueError as error:lines.append('二维动画暂不能解析：'+str(error))
            else:lines.append('未找到可读取尺寸的配套 PNG，动画结构尚未核实。')
        if len(lines)==3:lines.append('没有提取到支持的条件字段；请查看原始配置。')
    else:lines.append('此配置格式暂不解释，仅展示原始内容；未据此推断关联或效果。')
    return '\n'.join(lines)


class RulesPanel:
    def __init__(self,window):
        self.window=window;self.descriptor=None;self.graph=None;self.selected=set();self.automatic=False
        self.dock=QDockWidget('配置规则',window);self.dock.setObjectName('v3-resource-rules')
        from .dock_chrome import configure
        configure(self.dock)
        panel=QWidget();layout=QVBoxLayout(panel)
        self.caption=QLabel();self.caption.setWordWrap(True);self.caption.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.caption)
        self.all_configs=QCheckBox('列出来源全部配置（不代表与当前素材有关联）');layout.addWidget(self.all_configs)
        split=QSplitter(Qt.Orientation.Vertical);split.setChildrenCollapsible(False);layout.addWidget(split,1)
        self.tree=QTreeWidget();self.tree.setHeaderHidden(True);self.tree.setMinimumHeight(100)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setDragEnabled(False);self.tree.setAcceptDrops(False)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setToolTip('只读配置文件树');self.nodes={};split.addWidget(self.tree)
        self.tree.setStyleSheet('QTreeWidget {border:1px solid #454545;border-radius:4px;}')
        frame=QFrame();frame.setObjectName('rulesContentFrame');split.addWidget(frame)
        split.setStretchFactor(0,1);split.setStretchFactor(1,2);split.setSizes([180,360])
        frame.setStyleSheet('QFrame#rulesContentFrame {border:1px solid #454545;border-radius:6px;background:#313131;}')
        frame_layout=QVBoxLayout(frame);frame_layout.setContentsMargins(1,1,1,1);frame_layout.setSpacing(0)
        tabs=QTabWidget();frame_layout.addWidget(tabs);tabs.setObjectName('resourceRuleTabs')
        tabs.setDocumentMode(True);tabs.tabBar().setExpanding(True);tabs.tabBar().setUsesScrollButtons(False)
        tabs.setStyleSheet('''
            QTabWidget#resourceRuleTabs::pane {border:1px solid #454545;border-top:0;background:#313131;}
            QTabBar::tab {background:#2d2d30;color:#cccccc;border:1px solid #454545;padding:6px 4px;margin:0;}
            QTabBar::tab:first {border-top-left-radius:6px;}
            QTabBar::tab:last {border-top-right-radius:6px;}
            QTabBar::tab:selected {background:#313131;border-bottom-color:#313131;}
            QTabBar::tab:hover {background:#3c3c3c;}
            QPlainTextEdit {background:#313131;color:#cccccc;border:0;border-radius:0;padding:6px;selection-background-color:#264f78;}
        ''')
        self.summary=QPlainTextEdit();self.raw=QPlainTextEdit();self.references=QPlainTextEdit()
        self.summary.setProperty('localizeSummary',True);self.references.setProperty('localizeSummary',True)
        for title,widget in [('规则说明',self.summary),('原始配置',self.raw),('引用证据',self.references)]:
            widget.setReadOnly(True);tabs.addTab(widget,title)
        self.dock.setWidget(panel);window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,self.dock);self.dock.hide()
        self.caption.setText('打开素材后显示关联规则与原始配置。')
        self.dock.visibilityChanged.connect(lambda visible:self.window.run(self.refresh) if visible else None)
        self.tree.currentItemChanged.connect(lambda *args:self.window.run(self.show_config))
        self.all_configs.toggled.connect(lambda:self.window.run(self.refresh))

    def inspect(self,descriptor,explicit=False):
        descriptor=descriptor.get('_object_context',descriptor)
        if descriptor.get('kind') not in ('game_object','png','resource_group','file','root','folder'):return
        self.descriptor=copy.deepcopy(descriptor)
        self.automatic=not explicit
        blocker=QSignalBlocker(self.all_configs);self.all_configs.setChecked(False);del blocker
        if explicit:self.dock.show();self.dock.raise_()
        self.refresh()

    def refresh(self):
        if not self.descriptor or self.dock.isHidden():return
        owner=self.window.source(self.descriptor['origin'])
        self.summary.clear();self.raw.clear();self.references.clear()
        previous=self.current_path();expanded={path for path,item in self.nodes.items() if item.isExpanded()}
        blocker=QSignalBlocker(self.tree);self.tree.clear();self.nodes={}
        if owner is None:
            self.caption.setText('来源已移除，无法读取配置。');del blocker;return
        self.graph=graph_for(self.window,owner)
        path=self.descriptor.get('path','');kind=self.descriptor.get('kind')
        seeds=self.descriptor.get('resource_paths') or self.descriptor.get('object_paths') or [path]
        if kind in ('root','folder'):seeds=[p for p in owner.files if not path or p.startswith(path+'/')]
        self.selected,missing=self.graph.closure(seeds,include_callers=kind not in ('game_object','resource_group'))
        scope=set(owner.files) if self.all_configs.isChecked() else self.selected
        configs=sorted(p for p in scope if p in owner.files and p.lower().endswith(CONFIG_SUFFIXES))
        if kind=='file' and path in owner.files and path not in configs:configs.insert(0,path)
        for filename in configs:
            parent=self.tree.invisibleRootItem();parts=filename.split('/')
            for i,name in enumerate(parts):
                key='/'.join(parts[:i+1]);leaf=i==len(parts)-1
                item=self.nodes.get(key)
                if item is None:
                    item=QTreeWidgetItem(parent,[name]);self.nodes[key]=item
                    item.setData(0,Qt.ItemDataRole.UserRole,{'kind':'file' if leaf else 'folder','path':key,'origin':self.descriptor['origin']})
                    item.setToolTip(0,key)
                    item.setIcon(0,self.tree.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon if leaf else QStyle.StandardPixmap.SP_DirIcon))
                    if key in expanded:item.setExpanded(True)
                parent=item
        chosen=self.nodes.get(path if kind=='file' else previous)
        if chosen is None and configs:chosen=self.nodes[configs[0]]
        if chosen is not None:
            self.tree.setCurrentItem(chosen);parent=chosen.parent()
            while parent is not None:parent.setExpanded(True);parent=parent.parent()
            self.tree.scrollToItem(chosen)
        del blocker
        self.caption.setText(owner.name+' · '+self.descriptor.get('name',path)+f'\n关联 {len(self.selected)} 个文件；当前列出 {len(configs)} 个配置。')
        version=source_version(owner,self.window.working_version);vanilla=records(version)
        rows=[]
        for edge in self.graph.evidence:
            if edge['source'] not in self.selected:continue
            status='来源内存在' if edge['target'] in owner.files else '原版目录存在（'+version+'）' if edge['target'] in vanilla else '尚未找到'
            rows.append(edge['source']+'\n  → '+edge['target']+'\n  '+edge['reason']+' · '+status)
            if len(rows)>=1000:rows.append('引用列表仅展示前 1000 条。');break
        for issue in self.graph.issues:
            if issue['path'] in self.selected:rows.append(issue['path']+'：'+issue['reason'])
        self.references.setPlainText('\n\n'.join(rows) or '未解析到关联引用；这不代表素材不存在其他扩展规则。')
        self.show_config()

    def current_path(self):
        item=self.tree.currentItem()
        data=item.data(0,Qt.ItemDataRole.UserRole) if item else None
        return data['path'] if data and data['kind']=='file' else None

    def show_config(self):
        self.summary.clear();self.raw.clear()
        if not self.descriptor:return
        owner=self.window.source(self.descriptor['origin']);path=self.current_path()
        if owner is None or path not in owner.files:
            self.summary.setPlainText('没有可展示的关联配置。可勾选“列出来源全部配置”手动查看未识别内容。');return
        raw=owner.files[path];limit=512*1024;preview=raw[:limit]
        try:text=preview.decode('utf-8-sig');encoding_note=''
        except UnicodeError:
            text=preview.decode('utf-8-sig',errors='replace');encoding_note='部分字节无法按 UTF-8 显示，以替代符展示；原文件字节未改动。\n'
        self.raw.setPlainText(encoding_note+text+('\n\n[仅显示前 512 KiB；原文件完整保留]' if len(raw)>limit else ''))
        if len(raw)>limit:description='配置较大，仅提供原文预览，未生成条件摘要。'
        else:description=describe_config(path,raw,self.graph,owner.files)
        if path not in self.selected:description='手动浏览来源配置：尚未确认它与当前素材的关联。\n\n'+description
        self.summary.setPlainText(description)

    def add_action(self,menu,descriptor):
        if descriptor.get('kind') not in ('game_object','png','resource_group','file','root','folder') or self.window.source(descriptor['origin']) is None:return
        stable=copy.deepcopy(descriptor);action=menu.addAction('查看规则与原始配置')
        action.triggered.connect(lambda:self.window.run(lambda:self.inspect(stable,True)))


def install(window):window.resource_rules=RulesPanel(window)
