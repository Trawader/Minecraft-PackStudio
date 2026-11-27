from pathlib import Path
from .release import APP_TITLE
import os
from PySide6.QtCore import Qt, QSettings, QSignalBlocker
from PySide6.QtGui import QColor, QPainter, QShortcut, QKeySequence, QFont, QAction
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QTabWidget,QListWidget,QListWidgetItem,QTreeWidget,QTreeWidgetItem,QSplitter,QComboBox,QLineEdit,QFileDialog,QInputDialog,QMessageBox,QColorDialog,QCheckBox)
from .core import *
from .canvas import Canvas,ScreenPicker
from .preview import Preview
from .models import ModelLibrary,GROUPS
from dataclasses import replace as replace_face
from PySide6.QtWidgets import QDialog, QHeaderView,QMenu,QWidgetAction,QSpinBox
from .appearance import ColorSwatch,tool_icon
from .panels import AssetTree
from PySide6.QtCore import QSize

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setFont(QFont('Microsoft YaHei UI',9))
        settings_file=os.environ.get('PACKSTUDIO_SETTINGS_FILE')
        if not settings_file and getattr(sys,'frozen',False):
            settings_file=str(ROOT/'config/settings.ini')
        self.settings=QSettings(settings_file,QSettings.Format.IniFormat) if settings_file else QSettings('PackStudio','Editor')
        self.lang=self.settings.value('language','zh');self.labels=[];self.layers=[]
        asset_root=self.settings.value('vanilla','')
        if asset_root and Path(asset_root)==ROOT/'reference'/'各版本assets':asset_root=''
        self.vanilla=Vanilla(asset_root or None)
        self.current=None;self.dirty=False;self.refreshing=False;self.pickers=[];self.project_path=None;self.working_version='1.8.9'
        self.setWindowTitle(APP_TITLE);self.resize(1380,880)
        central=QWidget();layout=QVBoxLayout(central);self.setCentralWidget(central)
        self.tabs=QTabWidget();layout.addWidget(self.tabs)
        self.pages=[]
        for zh,en in [('资源与绘制','Assets & paint'),('合成与导出','Compose & export')]:
            page=QWidget();box=QVBoxLayout(page);self.tabs.addTab(page,zh if self.lang=='zh' else en);self.pages.append(box);self.labels.append((self.tabs,zh,en,len(self.pages)-1))
        self.report=QLabel()
        self.build_editor();self.build_preview();self.build_export();self.build_settings();self.build_menus()
        for key,fn in [('Ctrl+Z',self.canvas.undo),('Ctrl+Shift+Z',self.canvas.redo)]:QShortcut(QKeySequence(key),self,activated=fn)
        self.setStyleSheet('QMainWindow,QWidget {font-size: 13px;} QPushButton {padding: 7px 12px;} QTreeWidget,QListWidget {border:1px solid #666;} QTabBar::tab {padding:10px 18px;}')
        self.statusBar().showMessage(self.tr('导入材质包开始；上层覆盖下层，缺失资源回退原版。','Import a pack to begin. Top layers win; missing assets fall back to vanilla.'))
    def tr(self,zh,en):return zh if self.lang=='zh' else en
    def label(self,box,zh,en):
        w=QLabel(self.tr(zh,en));w.setWordWrap(True);box.addWidget(w);self.labels.append((w,zh,en,None));return w
    def button(self,box,zh,en,fn):
        w=QPushButton(self.tr(zh,en));box.addWidget(w);w.clicked.connect(lambda checked=False:self.run(fn));self.labels.append((w,zh,en,None));return w
    def run(self,fn):
        try:fn()
        except Exception as e:QMessageBox.warning(self,self.tr('操作未完成','Operation failed'),str(e))
    def changed(self):self.dirty=True;self.setWindowModified(True)
    def build_menus(self):
        def menu(zh,en):
            m=self.menuBar().addMenu(self.tr(zh,en));self.labels.append((m.menuAction(),zh,en,None));return m
        def action(m,zh,en,fn,key=None):
            a=QAction(self.tr(zh,en),self);m.addAction(a);a.triggered.connect(lambda checked=False:self.run(fn));self.labels.append((a,zh,en,None))
            if key:a.setShortcut(QKeySequence(key))
            return a
        file=menu('项目','Project')
        action(file,'打开项目…','Open project…',self.open_project,'Ctrl+O')
        action(file,'打开项目文件夹…','Open project folder…',self.open_project_folder)
        action(file,'保存项目','Save project',self.save,'Ctrl+S')
        action(file,'项目另存为…','Save project as…',lambda:self.save_as(True),'Ctrl+Shift+S')
        imports=menu('导入','Import')
        action(imports,'材质包 ZIP…','Pack ZIP…',self.add_zip);action(imports,'材质包文件夹…','Pack folder…',self.add_folder);action(imports,'PNG…','PNG…',self.add_png)
        action(imports,'OGG 音效…','OGG sounds…',self.add_ogg)
        self.preview_action=QAction(self.tr('开启单物体预览','Show object preview'),self)
        self.preview_action.setCheckable(True);self.preview_action.setChecked(self.settings.value('preview',True,type=bool));self.preview_action.toggled.connect(self.toggle_preview)
        self.toggle_preview(self.preview_action.isChecked())
        self.settings_action=QAction(self.tr('设置','Settings'),self);self.menuBar().addAction(self.settings_action)
        self.settings_action.triggered.connect(lambda:(self.settings_dialog.show(),self.settings_dialog.raise_()))
        self.labels.append((self.settings_action,'设置','Settings',None))
    def toggle_preview(self,enabled):
        self.preview_panel.setVisible(enabled);self.settings.setValue('preview',enabled)
    def add_zip(self):
        paths,_=QFileDialog.getOpenFileNames(self,'ZIP',str(ROOT/'reference'),'ZIP (*.zip)')
        for path in paths:self.add_pack(path)
    def add_ogg(self):
        paths,_=QFileDialog.getOpenFileNames(self,self.tr('导入音效','Import sounds'),'','OGG (*.ogg)')
        if not paths:return
        from .import_drop import import_paths
        import_paths(self,paths)
    def add_folder(self):
        path=QFileDialog.getExistingDirectory(self,self.tr('材质包目录','Pack folder'),str(ROOT/'reference'))
        if path:self.add_pack(path)
    def add_pack(self,path):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            layer=import_pack(path);fmt,matches=identify(layer,self.vanilla)
            self.layers.insert(0,layer);self.changed();self.refresh()
            self.tabs.setCurrentIndex(0);self.statusBar().showMessage(self.tr(f'已导入 {layer.name}：{len(layer.files)} 个文件，格式 {fmt}。',f'Imported {layer.name}: {len(layer.files)} files, format {fmt}.'))
            self.report.setText(self.tr(f'{layer.name}\n{len(layer.files)} 个文件；pack_format = {fmt}\n原版路径匹配：{matches}\n导出可选择低版本声明或不作适配。路径匹配不等于兼容性验证。',f'{layer.name}\n{len(layer.files)} files; pack_format = {fmt}\nVanilla path matches: {matches}\nExport with a legacy declaration or without adaptation. Path matches do not verify compatibility.'))
        finally:QApplication.restoreOverrideCursor()
    def add_png(self):
        path,_=QFileDialog.getOpenFileName(self,'PNG','','PNG (*.png)')
        if not path:return
        target,ok=QInputDialog.getText(self,self.tr('资源路径','Resource path'),'assets/minecraft/...',text=self.current[0] if self.current else 'assets/minecraft/textures/blocks/stone.png')
        if not ok:return
        target=safe_path(target)
        if not target.startswith('assets/') or not target.endswith('.png'):raise ValueError('Expected assets/.../*.png')
        data=Path(path).read_bytes();decode(data)
        self.layers.insert(0,Layer(Path(path).stem,{target:data},kind='png',source=str(Path(path).resolve())))
        self.changed();self.refresh()
    def build_editor(self):
        box=self.pages[0];split=QSplitter();box.addWidget(split);self.editor_split=split
        left=QWidget();v=QVBoxLayout(left);self.search=QLineEdit();self.search.setPlaceholderText('搜索 / Search');v.addWidget(self.search)
        self.defaults=QCheckBox(self.tr('显示原版资源','Show vanilla resources'));v.addWidget(self.defaults);self.labels.append((self.defaults,'显示原版资源','Show vanilla resources',None))
        self.tree=AssetTree();self.tree.setHeaderLabels(['资源 / Resources']);v.addWidget(self.tree);split.addWidget(left)
        self.tree.setIndentation(14);self.tree.header().setStretchLastSection(False);self.tree.header().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemClicked.connect(lambda item,column:item.setExpanded(not item.isExpanded()) if item.data(0,Qt.ItemDataRole.UserRole) is None else None)
        right=QWidget();rv=QVBoxLayout(right);self.caption=QLabel();rv.addWidget(self.caption)
        paint_area=QHBoxLayout();rv.addLayout(paint_area,1)
        row=QVBoxLayout();row.setSpacing(4);paint_area.addLayout(row)
        self.canvas=Canvas();paint_area.addWidget(self.canvas,1);self.canvas.changed.connect(lambda:self.run(self.commit_canvas));self.canvas.picked.connect(self.set_color)
        from .editor_controls import tools,palette
        for button in tools(self).values():row.addWidget(button)
        row.addStretch();row=QHBoxLayout();row.setSpacing(5);rv.addLayout(row)
        for button in palette(self):row.addWidget(button)
        row.addStretch()
        row=QHBoxLayout();rv.addLayout(row)
        self.button(row,'屏幕吸色','Screen picker',self.screen_pick)
        row.addWidget(self.tool_buttons['wand'])
        self.button(row,'取消选区','Deselect',self.canvas.clear_selection)
        self.button(row,'撤销','Undo',lambda:self.canvas.undo());self.button(row,'重做','Redo',lambda:self.canvas.redo())
        self.canvas_zoom_label=QLabel(f'{self.canvas.zoom*100:g}%');row.addWidget(self.canvas_zoom_label)
        self.canvas.zoomChanged.connect(lambda zoom:self.canvas_zoom_label.setText(f'{zoom*100:.1f}%'))
        row=QHBoxLayout();rv.addLayout(row)
        self.button(row,'提取为顶部组件层','Extract top component layer',self.extract);self.button(row,'替换当前图像','Replace current image',self.replace);self.button(row,'导出当前 PNG','Export current PNG',self.export_png)
        self.label(rv,'选区：左键新建，Shift 加选，Alt 减选，Esc 取消。鼠标拖动选区，回车放置。指针工具：Alt+滚轮围绕鼠标缩放，中键平移。','Selection: left replaces, Shift adds, Alt subtracts, Esc clears. Mouse moves, Enter places. Pointer tool: Alt+wheel zooms at cursor; middle drag pans.')
        split.addWidget(right);split.setSizes([360,950]);self.search.textChanged.connect(self.filter_tree);self.defaults.toggled.connect(self.refresh)
        self.tree.itemSelectionChanged.connect(lambda:self.run(self.select_resource))
    def set_tool(self,tool):
        if getattr(self,'large_view_only',False):return
        self.canvas.set_tool(tool)
        if hasattr(self,'gradient_button'):self.gradient_button.setChecked(tool=='gradient')
        for key,button in self.tool_buttons.items():
            modes=getattr(button,'group_modes',[key]);button.setChecked(tool in modes)
            if tool in modes and hasattr(button,'group_modes'):
                button.active_mode=tool;button.setIcon(tool_icon(tool));button.setToolTip({'bucket':'油漆桶','fill':'填充','burn':'加深','dodge':'减淡','lighten':'变明','darken':'变暗','eraser':'橡皮擦','magic_eraser':'魔术橡皮擦'}[tool])
    def activate_palette(self,index,color):
        self.active_palette_index=index;self.settings.setValue('palette-v2/active',index);self.set_color(color)
    def set_color(self,color):
        color=QColor(color)
        if not color.isValid():return
        self.canvas.color=color;self.color_button.set_color(color)
        if hasattr(self,'active_palette_index'):
            for i,button in enumerate(self.palette_buttons):
                button.setChecked(i==self.active_palette_index)
                if i==self.active_palette_index:
                    button.set_color(color);self.settings.setValue(f'palette-v2/{i}',color.name(QColor.NameFormat.HexArgb))
    def choose_color(self):
        from .color_editor import choose_color
        color=choose_color(self.canvas.color,self)
        if color.isValid():self.set_color(color)
    def tone_amount(self,tool):
        amount,ok=QInputDialog.getInt(self,self.tr('工具幅度','Tool strength'),self.tr('幅度（%）','Strength (%)'),self.canvas.amounts[tool],1,100,1)
        if ok:self.canvas.amounts[tool]=amount
    def rectangle_settings(self,button,pos):
        menu=self.rectangle_menu();menu.exec(button.mapToGlobal(pos));menu.deleteLater()
    def rectangle_menu(self):
        menu=QMenu(self)
        for mode,zh,en in [('normal','矩形选区','Rectangle selection'),('opaque','魔法矩形（仅非透明像素）','Magic rectangle (non-transparent pixels)')]:
            from .appearance import tool_icon
            action=menu.addAction(tool_icon('magic_select' if mode=='opaque' else 'select'),self.tr(zh,en));action.setCheckable(True);action.setChecked(self.canvas.rectangle_mode==mode)
            action.triggered.connect(lambda checked=False,value=mode:self.set_rectangle_mode(value))
        return menu
    def set_rectangle_mode(self,mode):
        self.canvas.rectangle_mode=mode;self.set_tool('select')
        self.update_rectangle_tooltip()
    def update_rectangle_tooltip(self):
        label=self.tr('魔法矩形','Magic rectangle') if self.canvas.rectangle_mode=='opaque' else self.tr('矩形选区','Rectangle selection')
        self.tool_buttons['select'].setToolTip(label)
        from .appearance import tool_icon
        self.tool_buttons['select'].setIcon(tool_icon('magic_select' if self.canvas.rectangle_mode=='opaque' else 'select'))
    def wand_settings(self,button,pos):
        menu=QMenu(self);panel=QWidget();row=QHBoxLayout(panel)
        row.addWidget(QLabel(self.tr('容差','Tolerance')));spin=QSpinBox();spin.setRange(0,255);spin.setValue(self.canvas.wand_tolerance);row.addWidget(spin)
        spin.valueChanged.connect(lambda value:setattr(self.canvas,'wand_tolerance',value))
        action=QWidgetAction(menu);action.setDefaultWidget(panel);menu.addAction(action)
        for zh,en,field in [('连续','Contiguous','wand_contiguous'),('消除锯齿','Anti-alias','wand_antialias')]:
            action=menu.addAction(self.tr(zh,en));action.setCheckable(True);action.setChecked(getattr(self.canvas,field))
            action.toggled.connect(lambda checked,key=field:setattr(self.canvas,key,checked))
        menu.exec(button.mapToGlobal(pos))
    def screen_pick(self):
        shots=[(s,s.grabWindow(0)) for s in QApplication.screens()]
        if any(p.isNull() for s,p in shots):raise ValueError('Screen capture unavailable')
        self.pickers=[]
        for screen,pix in shots:
            picker=ScreenPicker(screen,pix);picker.picked.connect(self.screen_color);picker.rejected.connect(self.close_pickers);self.pickers.append(picker)
        for picker in self.pickers:picker.show();picker.activateWindow()
    def close_pickers(self):
        for picker in self.pickers:picker.hide();picker.deleteLater()
        self.pickers=[]
    def screen_color(self,color):self.set_color(color);self.close_pickers()
    def refresh(self,*args):
        self.refreshing=True
        def walk(item):
            for i in range(item.childCount()):
                child=item.child(i);yield child;yield from walk(child)
        expanded={item.data(0,Qt.ItemDataRole.UserRole+1) for item in walk(self.tree.invisibleRootItem()) if item.isExpanded()}
        scroll=self.tree.verticalScrollBar().value()
        self.stack.clear()
        for layer in self.layers:
            item=QListWidgetItem(f'{layer.name}  [{layer.kind}]');item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Checked if layer.enabled else Qt.CheckState.Unchecked);self.stack.addItem(item)
        paths={p for l in self.layers for p in (list(l.files) if l.kind!='component' else [l.target]) if p.endswith('.png')}
        if self.defaults.isChecked():paths|={p for p in self.vanilla.paths(self.working_version) if p.endswith('.png')}
        self.tree.clear()
        folders={};selected=None
        for path in sorted(paths):
            parent=self.tree.invisibleRootItem();parts=path.split('/')
            for i,part in enumerate(parts[:-1]):
                key='/'.join(parts[:i+1])
                if key not in folders:
                    folder=QTreeWidgetItem([part]);folder.setData(0,Qt.ItemDataRole.UserRole+1,key);parent.addChild(folder);folders[key]=folder
                    folder.setExpanded(key in expanded or (not expanded and i<3))
                parent=folders[key]
            item=QTreeWidgetItem([parts[-1]]);item.setToolTip(0,path);item.setData(0,Qt.ItemDataRole.UserRole,(path,None));item.setData(0,Qt.ItemDataRole.UserRole+1,path);parent.addChild(item)
            if self.current==(path,None):selected=item
            for name,regions in components(path):
                child=QTreeWidgetItem([name]);child.setData(0,Qt.ItemDataRole.UserRole,(path,regions));item.addChild(child)
                if self.current==(path,regions):selected=child
            item.setExpanded(path in expanded)
        if selected:self.tree.setCurrentItem(selected)
        self.refreshing=False;self.filter_tree()
        self.tree.verticalScrollBar().setValue(scroll)
    def filter_tree(self):
        query=self.search.text().lower()
        def visit(item,ancestor=False):
            match=ancestor or query in item.text(0).lower() or query in item.toolTip(0).lower()
            children=[visit(item.child(i),match) for i in range(item.childCount())]
            visible=match or any(children);item.setHidden(not visible)
            if query and any(children):item.setExpanded(True)
            return visible
        for i in range(self.tree.topLevelItemCount()):visit(self.tree.topLevelItem(i))
    def result(self):return compose(self.layers,self.vanilla,self.working_version)
    def select_resource(self):
        if self.refreshing:return
        item=self.tree.currentItem()
        if not item or item.data(0,Qt.ItemDataRole.UserRole) is None:return
        self.current=item.data(0,Qt.ItemDataRole.UserRole);self.load_canvas()
    def load_canvas(self):
        path,regions=self.current;files,provenance=self.result();data=files.get(path) or self.vanilla.get(self.working_version,path)
        if data is None:raise ValueError(f'Missing resource: {path}')
        atlas=decode(data);self.atlas_size=(atlas.width(),atlas.height());self.edit_parts=[]
        if regions:
            parts=[atlas.copy(*pixel_rect(r,atlas)) for r in regions]
            image=QImage(max(p.width() for p in parts),sum(p.height() for p in parts),QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.transparent);painter=QPainter(image);y=0
            for part in parts:painter.drawImage(0,y,part);self.edit_parts.append((0,y,part.width(),part.height()));y+=part.height()
            painter.end()
        else:image=atlas
        self.canvas.set_image(image);self.edit_layer=None
        self.caption.setText(f'{path} · {image.width()} × {image.height()}\n'+ ' → '.join(provenance.get(path,[self.tr('原版回退','Vanilla fallback')])))
        self.preview.image=atlas
        self.auto_model()
    def commit_canvas(self):
        if not self.current:return
        path,regions=self.current
        if self.edit_layer is None or not any(l is self.edit_layer for l in self.layers):
            self.edit_layer=Layer(self.tr('编辑：','Edit: ')+Path(path).name,kind='component' if regions else 'png',target=path,regions=regions or [])
            self.layers.insert(0,self.edit_layer)
        if regions:self.edit_layer.files={str(i):png(self.canvas.image.copy(*rect)) for i,rect in enumerate(self.edit_parts)}
        else:self.edit_layer.files={path:png(self.canvas.image)}
        self.changed();self.refresh()
        self.update_edit_preview()
    def extract(self):
        if not self.current:return
        path,regions=self.current
        if not regions:
            if not self.canvas.selection:raise ValueError(self.tr('请框选区域或选择已有组件。','Select a rectangle or a known component.'))
            rectangles=self.canvas.selection_rectangles()
            regions=[(x/self.canvas.image.width(),y/self.canvas.image.height(),w/self.canvas.image.width(),h/self.canvas.image.height()) for x,y,w,h in rectangles];parts=[self.canvas.image.copy(*rect) for rect in rectangles]
        else:
            view=self.canvas.view_image();parts=[view.copy(*rect) for rect in self.edit_parts]
        name,ok=QInputDialog.getText(self,self.tr('组件名称','Component name'),'Name',text=Path(path).stem)
        if ok:
            self.layers.insert(0,Layer(name,{str(i):png(p) for i,p in enumerate(parts)},'component',path,regions));self.changed();self.refresh()
    def replace(self):
        if getattr(self,'large_view_only',False):return
        if not self.current:return
        path,_=QFileDialog.getOpenFileName(self,'PNG','','PNG (*.png)')
        if path:
            image=decode(Path(path).read_bytes())
            if image.size()!=self.canvas.view_size():
                if QMessageBox.question(self,self.tr('尺寸转换','Resize'),self.tr('用最近邻缩放到当前区域大小？','Resize to current region using nearest neighbour?'))!=QMessageBox.StandardButton.Yes:return
                image=image.scaled(self.canvas.view_size())
            self.canvas.checkpoint();self.canvas.replace_view(image);self.canvas.update();self.commit_canvas()
    def export_png(self):
        if getattr(self,'large_view_only',False):return
        if self.canvas.image.isNull():return
        path,_=QFileDialog.getSaveFileName(self,'PNG','component.png','PNG (*.png)')
        if path:
            from .task_progress import encode_image
            self.protect_source(path);Path(path).write_bytes(encode_image(self,self.canvas.view_image()))
    def build_preview(self):
        self.preview_panel=QWidget();box=QVBoxLayout(self.preview_panel);self.editor_split.addWidget(self.preview_panel);self.editor_split.setSizes([260,740,380])
        self.label(box,'当前编辑贴图 · 单物体预览','Current texture · Object preview')
        self.model_library=ModelLibrary(self.vanilla);self.model_key=None;self.model_selecting=False
        row=QHBoxLayout();box.addLayout(row);self.preview_category=QComboBox();row.addWidget(self.preview_category)
        for label,key in [('方块 / Blocks','block'),('实体 / Entities','entity'),('物品模型 / Item models','item')]:self.preview_category.addItem(label,key)
        self.preview_group=QComboBox();row.addWidget(self.preview_group)
        self.preview_model=QComboBox();self.preview_model.setMinimumContentsLength(15);box.addWidget(self.preview_model)
        self.texture_binding=QComboBox();box.addWidget(self.texture_binding);self.texture_binding.currentIndexChanged.connect(lambda:self.run(self.update_edit_preview));self.binding_model=None
        row=QHBoxLayout();box.addLayout(row);self.model_id=QLineEdit();self.model_id.setPlaceholderText('物品 / 方块 ID · minecraft:anvil');row.addWidget(self.model_id)
        self.button(row,'按 ID 查找','Find ID',self.find_model_id)
        row=QHBoxLayout();box.addLayout(row);self.button(row,'按当前 PNG 自动识别','Auto-detect PNG',self.auto_model)
        self.model_info=QLabel();self.model_info.setWordWrap(True);box.addWidget(self.model_info)
        self.preview=Preview();box.addWidget(self.preview,1)
        self.preview_category.currentIndexChanged.connect(lambda:self.run(self.fill_model_groups))
        self.preview_group.currentIndexChanged.connect(lambda:self.run(self.fill_model_options))
        self.preview_model.currentIndexChanged.connect(lambda:self.run(self.choose_model))
        self.model_id.returnPressed.connect(lambda:self.run(self.find_model_id))
        self.label(box,'拖动旋转，Alt+滚轮缩放。优先读取包内模型与关联贴图，缺失贴图显示紫黑格。实体参考模型为静态姿态。','Drag to rotate; Alt+wheel to zoom. Pack models and linked textures take priority. Missing textures show a checker. Entity reference models use static poses.')
        self.fill_model_groups()
    def sync_model_library(self):
        files,_=self.result();self.model_library.update(files);return files
    def fill_model_groups(self):
        if self.model_selecting:return
        self.preview_group.blockSignals(True);self.preview_group.clear()
        groups={entry[1] for entry in self.model_library.entries.values() if entry[0]==self.preview_category.currentData()}
        for key in GROUPS:
            if key in groups:self.preview_group.addItem(self.tr(*GROUPS[key]),key)
        self.preview_group.blockSignals(False);self.fill_model_options()
    def fill_model_options(self):
        if self.model_selecting:return
        self.preview_model.blockSignals(True);self.preview_model.clear()
        for key,entry in self.model_library.entries.items():
            if entry[:2]==(self.preview_category.currentData(),self.preview_group.currentData()):self.preview_model.addItem(entry[2],key)
        self.preview_model.blockSignals(False);self.choose_model()
    def choose_model(self):
        if self.model_selecting:return
        self.model_key=self.preview_model.currentData();self.update_edit_preview()
    def select_model_key(self,key):
        entry=self.model_library.entries.get(key)
        if not entry:
            self.model_key=None;self.preview.clear_model(self.tr('未找到可用模型，可按 ID 或分类手动选择。','No matching model. Choose a category or enter an ID.'));self.model_info.setText(self.tr('未识别；不会用立方体冒充。','Unrecognized; no cube substitution.'));return
        self.model_selecting=True
        self.preview_category.setCurrentIndex(self.preview_category.findData(entry[0]));self.model_selecting=False;self.fill_model_groups()
        self.preview_group.setCurrentIndex(self.preview_group.findData(entry[1]));self.preview_model.setCurrentIndex(self.preview_model.findData(key));self.model_key=key;self.update_edit_preview()
    def auto_model(self):
        if getattr(self,'large_view_only',False):return
        if not self.current:return
        self.sync_model_library();path=self.current[0];key=self.model_library.identify(path,self.canvas.image)
        self.select_model_key(key)
    def find_model_id(self):
        self.sync_model_library();key=self.model_library.from_id(self.model_id.text().strip())
        if not key:raise ValueError(self.tr('没有找到此 ID 的模型。可在分类列表选择。','No model found for this ID. Try the category list.'))
        self.select_model_key(key)
    def build_export(self):
        box=self.pages[1];self.label(box,'上方优先。组件写入下方图集，缺失内容回退原版。目标版本只用于保存材质包副本。','Top wins. Components patch lower atlases; missing content falls back to vanilla. The target version applies only to resource pack copies.')
        self.stack=QListWidget();box.addWidget(self.stack);self.stack.itemChanged.connect(self.toggle_layer)
        self.stack.itemDoubleClicked.connect(lambda item:self.run(self.open_layer))
        row=QHBoxLayout();box.addLayout(row);self.button(row,'上移','Move up',lambda:self.move_layer(-1));self.button(row,'下移','Move down',lambda:self.move_layer(1));self.button(row,'移除','Remove',self.remove_layer);self.button(row,'编辑此层','Edit layer',self.open_layer)
        self.description=QLineEdit('Created with Pack Studio');box.addWidget(self.description)
        row=QHBoxLayout();box.addLayout(row);self.label(row,'材质包副本版本','Resource pack copy version');self.version=QComboBox();self.version.addItem(self.tr('请选择版本','Choose version'),'');
        for version in VERSIONS:self.version.addItem(version,version)
        self.version.addItem(self.tr('保留原始格式（跟随底包）','Preserve original format (follow base pack)'),'unchanged')
        row.addWidget(self.version)
        self.label(box,'不作适配：保留原格式和资源路径。低版本选项目前仅写入格式声明，不转换高版本内容；高版本转低版本可能异常，适配等待后续更新。','No adaptation preserves original metadata and resource paths. Legacy options currently write only the format declaration, without converting newer content; incompatibilities may occur. Conversion is planned for a later update.')
        row=QHBoxLayout();box.addLayout(row);self.button(row,'检查合成结果','Inspect composition',self.inspect);self.button(row,'保存材质包副本 ZIP','Save resource pack copy ZIP',self.export)
        self.export_info=QLabel();self.export_info.setWordWrap(True);box.addWidget(self.export_info)
    def toggle_layer(self,item):
        if self.refreshing:return
        self.layers[self.stack.row(item)].enabled=item.checkState()==Qt.CheckState.Checked;self.edit_layer=None;self.changed()
    def move_layer(self,delta):
        i=self.stack.currentRow();j=i+delta
        if 0<=i<len(self.layers) and 0<=j<len(self.layers):self.layers[i],self.layers[j]=self.layers[j],self.layers[i];self.edit_layer=None;self.changed();self.refresh();self.stack.setCurrentRow(j)
    def remove_layer(self):
        i=self.stack.currentRow()
        if i>=0:self.layers.pop(i);self.edit_layer=None;self.changed();self.refresh()
    def open_layer(self):
        i=self.stack.currentRow()
        if i<0:return
        layer=self.layers[i]
        if layer.kind=='component':
            self.current=(layer.target,layer.regions);self.load_canvas();self.edit_layer=layer
            parts=[decode(layer.files[str(j)]) for j in range(len(layer.regions))]
            # Display the layer itself, independent of higher layers.
            image=QImage(max(p.width() for p in parts),sum(p.height() for p in parts),QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.transparent);p=QPainter(image);y=0;self.edit_parts=[]
            for part in parts:p.drawImage(0,y,part);self.edit_parts.append((0,y,part.width(),part.height()));y+=part.height()
            p.end();self.canvas.set_image(image)
        elif layer.kind=='png':
            path=next(iter(layer.files));self.current=(path,None);self.load_canvas();self.canvas.set_image(decode(layer.files[path]));self.edit_layer=layer
        else:
            self.tabs.setCurrentIndex(0);return
        self.update_edit_preview();self.tabs.setCurrentIndex(0)
    def update_edit_preview(self):
        if not self.current:return
        path,regions=self.current
        if not regions or self.canvas.regions:self.preview.image=QImage(self.canvas.image)
        else:
            base=self.preview_files().get(path) or self.vanilla.get(self.working_version,path)
            atlas=decode(base);painter=QPainter(atlas);painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            for region,rect in zip(regions,self.edit_parts):
                x,y,w,h=pixel_rect(region,atlas);painter.drawImage(x,y,self.canvas.image.copy(*rect).scaled(w,h))
            painter.end();self.preview.image=atlas
        if not self.model_key:return
        files=self.sync_model_library()
        def texture(name):return self.model_library.get(name)
        try:
            faces=self.model_library.faces(self.model_key,path)
            binding_key=(self.model_key,path)
            if self.binding_model!=binding_key:
                self.binding_model=binding_key;self.texture_binding.blockSignals(True);self.texture_binding.clear()
                self.texture_binding.addItem(self.tr('按模型关联贴图','Use model texture links'),'linked')
                self.texture_binding.addItem(self.tr('当前 PNG 铺到全部面','Apply current PNG to all faces'),'all')
                for name in sorted({f.texture for f in faces if f.texture}):self.texture_binding.addItem(self.tr('替换：','Replace: ')+name.split('/textures/')[-1],name)
                if not any(f.texture==path for f in faces):self.texture_binding.setCurrentIndex(1)
                self.texture_binding.blockSignals(False)
            binding=self.texture_binding.currentData()
            if binding and binding!='linked':faces=[replace_face(f,texture=path) if binding=='all' or f.texture==binding else f for f in faces]
            self.preview.set_model(faces,texture,path,self.preview.image)
            source=self.tr('包内模型','Pack model') if self.model_key in files else self.tr('参考实体模型','Reference entity model') if self.model_key.startswith('xml:') else self.tr('原版模型 ','Vanilla model ')+self.model_library.version
            note=f'{source} · {len(faces)} '+self.tr('个面','faces')
            if self.preview.missing:note+='\n'+self.tr('缺少贴图：','Missing textures: ')+', '.join(self.preview.missing)
            if binding=='all':note+='\n'+self.tr('预览试贴：当前 PNG 应用到所有面，不修改模型文件。','Preview override: current PNG on all faces; model files stay unchanged.')
            self.model_info.setText(note)
        except (ValueError,KeyError,TypeError) as e:self.preview.clear_model(str(e));self.model_info.setText(str(e))
    def preview_files(self):return self.result()[0]
    def inspect(self):
        version=self.version.currentData();files,provenance=compose(self.layers,self.vanilla,version if version in VERSIONS else self.working_version)
        metadata=self.tr('保留原 pack.mcmeta（如有）','Preserve original pack.mcmeta, if present') if version=='unchanged' else self.tr('写入低版本 pack.mcmeta','Write legacy pack.mcmeta')
        self.export_info.setText(f'{len(files)} '+self.tr('个文件','files')+' · '+metadata+'\n'+'\n'.join(f'{p}: {" → ".join(s)}' for p,s in provenance.items() if len(s)>1))
    def protect_source(self,path):
        if any(l.source and Path(path).resolve()==Path(l.source).resolve() for l in self.layers):raise ValueError(self.tr('请选择新文件，不能覆盖参考源文件。','Choose a new file; reference inputs cannot be overwritten.'))
    def export(self):
        from .export_dialog import ExportDialog
        dialog=ExportDialog(self);self.export_dialog=dialog
        try:dialog.exec()
        finally:
            if self.export_dialog is dialog:self.export_dialog=None
            dialog.deleteLater()
    def save(self):
        if self.project_path:self.write_project(self.project_path)
        else:self.save_as(False)
    def project_directory(self):
        directory=ROOT/'projects';directory.mkdir(parents=True,exist_ok=True);return directory
    def save_as(self,copy=False):
        initial=Path(self.project_path) if self.project_path else self.project_directory()/'project.MCPSD'
        if initial.is_dir():initial=initial/'project.MCPSD'
        initial=initial.with_suffix('.MCPSD')
        path,_=QFileDialog.getSaveFileName(self,self.tr('项目另存为' if copy else '保存项目','Save project as' if copy else 'Save project'),str(initial),self.tr('项目文件 (*.MCPSD)','Project file (*.MCPSD)'))
        if not path:return
        target=Path(path)
        if target.suffix.lower()!='.mcpsd':target=target.with_suffix('.MCPSD')
        if copy and self.project_path and target.resolve()==self.project_path.resolve():raise ValueError(self.tr('请选择不同于当前项目的位置。','Choose a location different from the current project.'))
        self.write_project(target,copy)
    def write_project(self,path,copy=False,folder=False):
        target=Path(path)
        folder=folder or target.is_dir()
        actual=target/'project.packstudio' if folder else target
        self.protect_source(actual)
        if folder:target.mkdir(parents=True,exist_ok=True)
        save_project(actual,self.layers,self.working_version)
        if not copy:
            self.project_path=target;self.dirty=False;self.setWindowModified(False);self.setWindowTitle(f'{target.name} [*]')
        self.statusBar().showMessage(self.tr('已保存：','Saved: ')+str(target))
    def discard_ok(self):
        if not self.dirty:return True
        box=QMessageBox(self);box.setWindowTitle(self.tr('未保存的项目','Unsaved project'))
        box.setIcon(QMessageBox.Icon.Question);box.setText(self.tr('项目有未保存的修改，是否保存？','Save changes to this project?'))
        save=box.addButton(self.tr('保存','Save'),QMessageBox.ButtonRole.AcceptRole)
        discard=box.addButton(self.tr('不保存',"Don't save"),QMessageBox.ButtonRole.DestructiveRole)
        cancel=box.addButton(self.tr('取消','Cancel'),QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save);box.setEscapeButton(cancel);box.exec()
        if box.clickedButton() is discard:return True
        if box.clickedButton() is not save:return False
        try:self.save()
        except Exception as error:
            QMessageBox.warning(self,self.tr('保存失败','Save failed'),str(error));return False
        return not self.dirty
    def open_project(self):
        if not self.discard_ok():return
        path,_=QFileDialog.getOpenFileName(self,self.tr('打开项目','Open project'),str(self.project_directory()),'Pack Studio (*.MCPSD *.mcpsd *.packstudio)')
        if path:self.read_project(path)
    def open_project_folder(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.project_directory()))):
            raise ValueError(self.tr('无法打开项目文件夹','Could not open the project folder'))
    def read_project(self,path):
        target=Path(path);layers,version=load_project(target/'project.packstudio' if target.is_dir() else target)
        self.layers=layers;self.working_version=version;self.current=None;self.edit_layer=None;self.project_path=target
        self.refresh();self.dirty=False;self.setWindowModified(False);self.canvas.set_image(QImage());self.preview.image=None;self.preview.clear_model();self.model_key=None;self.caption.clear()
        self.version.setCurrentIndex(0);self.setWindowTitle(f'{target.name} [*]');self.tabs.setCurrentIndex(0)
    def build_settings(self):
        self.settings_dialog=QDialog(self);self.settings_dialog.setWindowTitle(self.tr('设置','Settings'));self.settings_dialog.resize(580,260)
        box=QVBoxLayout(self.settings_dialog);self.label(box,'界面语言','Interface language');language=QComboBox();self.language_combo=language;language.addItems(['简体中文','English']);language.setCurrentIndex(0 if self.lang=='zh' else 1);box.addWidget(language);language.currentIndexChanged.connect(self.language_changed)
        self.rulers_toggle=QCheckBox(self.tr('显示图片尺幅（像素标尺）','Show image rulers (pixels)'));box.addWidget(self.rulers_toggle)
        self.labels.append((self.rulers_toggle,'显示图片尺幅（像素标尺）','Show image rulers (pixels)',None))
        self.canvas.show_rulers=self.settings.value('image-rulers',False,type=bool);self.rulers_toggle.setChecked(self.canvas.show_rulers)
        def toggle_rulers(enabled):
            self.canvas.show_rulers=enabled;self.settings.setValue('image-rulers',enabled);self.canvas.update()
        self.rulers_toggle.toggled.connect(toggle_rulers)
        self.label(box,'原版素材','Vanilla assets')
        self.root_label=QLabel(str(self.vanilla.root) if self.vanilla.root else self.tr('使用程序内置素材','Using built-in assets'));box.addWidget(self.root_label)
        self.button(box,'选择可选外部素材目录','Choose optional external assets',self.choose_root)
        self.button(box,'恢复内置素材','Use built-in assets',self.use_builtin_assets)
        box.addStretch()
    def language_changed(self,index):
        self.lang='zh' if index==0 else 'en';self.settings.setValue('language',self.lang)
        for widget,zh,en,tab in self.labels:
            if widget in self.tool_buttons.values():widget.setToolTip(self.tr(zh,en));widget.setText('')
            elif tab is None:widget.setText(self.tr(zh,en))
            else:widget.setTabText(tab,self.tr(zh,en))
        self.update_rectangle_tooltip()
        self.version.setItemText(self.version.findData('unchanged'),self.tr('保留原始格式（跟随底包）','Preserve original format (follow base pack)'))
        for i in range(self.preview_group.count()):
            key=self.preview_group.itemData(i);self.preview_group.setItemText(i,self.tr(*GROUPS[key]))
        if hasattr(self,'language_combo'):
            blocker=QSignalBlocker(self.language_combo);self.language_combo.setCurrentIndex(index);del blocker
        if hasattr(self,'localizer'):
            for i,action in enumerate(self.language_actions):action.setChecked(i==index)
            self.localizer.refresh()
    def choose_root(self):
        root=QFileDialog.getExistingDirectory(self,self.tr('原版目录','Vanilla root'),str(self.vanilla.root or ROOT))
        if root:
            self.vanilla=Vanilla(root);self.model_library=ModelLibrary(self.vanilla);self.settings.setValue('vanilla',root);self.root_label.setText(root);self.refresh();self.auto_model()
    def use_builtin_assets(self):
        self.vanilla=Vanilla();self.model_library=ModelLibrary(self.vanilla);self.settings.remove('vanilla')
        self.root_label.setText(self.tr('使用程序内置素材','Using built-in assets'));self.refresh();self.auto_model()
    def closeEvent(self,event):
        if self.discard_ok():self.close_pickers();event.accept()
        else:event.ignore()
