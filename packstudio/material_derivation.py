"""Deterministic, reversible colour variants of explicitly supported textures."""
import copy
import hashlib
import re
import base64,zlib
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QImage,QPixmap,QColor,QPainter
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,
    QListWidgetItem,QPushButton,QDialogButtonBox,QMessageBox,QWidget,QSplitter,QGridLayout,QSizePolicy,QSpinBox)
from .core import Layer,decode,png
from .semantics import describe,identities
from .object_catalog import WOODS
from .versions import records,source_version


COLORS='white orange magenta light_blue yellow lime pink gray light_gray cyan purple blue brown green red black'.split()


def family(path):
    code=identities()[0].get(path,path.split('/textures/')[-1].removesuffix('.png'));stem=code.rsplit('/',1)[-1]
    if 'glazed_terracotta' in stem:return None
    if code.startswith('block/'):
        if stem=='glass':return 'stained_glass'
        for kind in ('stained_glass','stained_glass_pane_top','concrete','concrete_powder'):
            if any(stem==color+'_'+kind for color in COLORS):return kind
        for wood in WOODS:
            for part in ('planks','log','log_top','wood','stem','stem_top','hyphae'):
                if stem==wood+'_'+part:return 'wood:'+part
        for finish in ('','polished_'):
            if stem in {finish+stone for stone in ('andesite','diorite','granite')} or not finish and stem=='stone':return 'stone:'+finish
    if code.startswith('item/'):
        match=re.fullmatch(r'(wooden|stone|iron|golden|diamond|netherite)_(sword|axe|pickaxe|shovel|hoe)',stem)
        if match:return 'equipment:'+match[2]
    return None


def anchor(image):
    rgba=image.convertToFormat(QImage.Format.Format_RGBA8888);raw=bytes(rgba.constBits())
    count=rgba.width()*rgba.height();step=max(1,count//4096)
    vivid=[];visible=[]
    for pixel in range(0,count,step):
        r,g,b,a=raw[pixel*4:pixel*4+4]
        if a<16:continue
        visible.append((r,g,b,a))
        if max(r,g,b)-min(r,g,b)>24 and 16<max(r,g,b)<240:vivid.append((r,g,b,a))
    samples=vivid or visible
    if not samples:raise ValueError('完全透明的贴图没有可用颜色参考')
    weight=sum(row[3] for row in samples)
    return tuple(round(sum(row[channel]*row[3] for row in samples)/weight) for channel in range(3))


def recolor(image,start,end,strength):
    # Piecewise monotone channel curves preserve black/white endpoints, alpha,
    # dimensions and pixel positions; no resampling, quantization or random input.
    rgba=image.convertToFormat(QImage.Format.Format_RGBA8888);raw=bytearray(rgba.constBits())
    for channel in range(3):
        pivot=max(1,min(254,start[channel]));destination=end[channel];table=[]
        for value in range(256):
            mapped=value*destination/pivot if value<=pivot else destination+(value-pivot)*(255-destination)/(255-pivot)
            table.append(max(0,min(255,round(value+(mapped-value)*strength/100))))
        raw[channel::4]=raw[channel::4].translate(bytes(table))
    return QImage(raw,rgba.width(),rgba.height(),rgba.bytesPerLine(),QImage.Format.Format_RGBA8888).copy()


def render_target(image,mask,raw,target_mask,strength,source_histogram,reference_color,color,custom,mode='distribution',preview=False,cancel=None,ramp=None):
    from .part_derivation import transfer
    target=decode(raw)
    if custom:target=recolor(target,reference_color,color,100)
    if mode=='ramp':
        from .derivation_reference import material_ramp,ramp_transfer
        return ramp_transfer(image,mask,ramp or material_ramp(target,target_mask),strength,source_histogram,cancel)
    if mode!='distribution':
        from .derivation_reference import reference_transfer,aligned
        if mode=='position' and not aligned(image,target):raise ValueError('位置参考需要相同尺寸且轮廓对应的贴图，请改用颜色参考。')
        if preview:
            def shrink(original,selection):
                small=original.scaled(320,200,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation) if original.width()>320 or original.height()>200 else original
                mapped=bytearray(selection[min(original.height()-1,y*original.height()//small.height())*original.width()+min(original.width()-1,x*original.width()//small.width())] for y in range(small.height()) for x in range(small.width()))
                return small,mapped
            image,mask=shrink(image,mask);target,target_mask=shrink(target,target_mask)
        return reference_transfer(image,mask,target,target_mask,strength,mode,cancel)
    return transfer(image,mask,target,target_mask,strength,source_histogram)


def generate_files(image,mask,jobs,strength,source_histogram,metadata,cancel=None,progress=None,mode='distribution'):
    files={}
    for index,job in enumerate(jobs):
        path,raw,target_mask,reference_color,color,custom=job[:6];ramp=job[6] if len(job)>6 else None
        if cancel and cancel.is_set():raise InterruptedError('已取消派生，合成台未修改。')
        if progress:progress(index,len(jobs))
        files[path]=png(render_target(image,mask,raw,target_mask,strength,source_histogram,reference_color,color,custom,mode=mode,cancel=cancel,ramp=ramp))
        if metadata is not None:files[path+'.mcmeta']=metadata
        if cancel and cancel.is_set():raise InterruptedError('已取消派生，合成台未修改。')
    if progress:progress(len(jobs),len(jobs))
    return files


def outlined_preview(image,mask,width=320,height=200):
    """Use the canvas selection contour, at final display size, without internal seams."""
    from .part_derivation import mask_region
    from .canvas import Canvas
    from types import SimpleNamespace
    from PySide6.QtGui import QPen
    preview=image.scaled(width,height,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation)
    state=SimpleNamespace(selection_region=mask_region(mask,image.width()),_selection_outline=None)
    path=Canvas.selection_outline(state)
    painter=QPainter(preview);painter.scale(preview.width()/image.width(),preview.height()/image.height())
    pen=QPen(QColor('#cccccc'));pen.setWidth(1);pen.setCosmetic(True);pen.setStyle(Qt.PenStyle.DashLine)
    painter.setPen(pen);painter.drawPath(path);painter.end();return preview


class DerivationDialog(QDialog):
    def __init__(self,window,descriptor):
        super().__init__(window);self.window=window;self.descriptor=copy.deepcopy(descriptor)
        self.owner=window.source(descriptor['origin']);self.path=descriptor['path'];self.output=None
        if self.owner is None or self.path not in self.owner.files:raise ValueError('来源文件已移除')
        self.original=self.owner.files[self.path];self.metadata=self.owner.files.get(self.path+'.mcmeta')
        self.image=decode(self.original);self.base_color=anchor(self.image)
        self.version=self.owner.asset_versions.get(self.path,source_version(self.owner,window.working_version))
        from .texture_animation import timeline
        if self.metadata is not None:timeline(self.metadata,self.image.width(),self.image.height())
        self.family=family(self.path)
        if self.family is None:raise ValueError('此纹理不属于已支持的调色家族')
        self.ramps={};self.targets={};self.reference_colors={};self.colors={};self.skipped=0;self.custom_colors=set()
        candidates=set(self.owner.files)|set(records(self.version))
        directory=self.path.rsplit('/',1)[0]
        for path in sorted(candidates):
            if path==self.path or not path.endswith('.png') or path.rsplit('/',1)[0]!=directory or family(path)!=self.family:continue
            local=path in self.owner.files
            raw=self.owner.files[path] if local else window.vanilla.get(self.version,path)
            metadata=self.owner.files.get(path+'.mcmeta')
            if metadata is None:metadata=window.vanilla.get(self.version,path+'.mcmeta')
            # A lower metadata file must not accidentally animate a newly static PNG.
            if raw is None or metadata!=self.metadata:self.skipped+=1;continue
            try:color=anchor(decode(raw))
            except ValueError:self.skipped+=1;continue
            self.targets[path]=(raw,metadata,local);self.reference_colors[path]=color;self.colors[path]=color
        if not self.targets:raise ValueError('没有找到同系列且动画配置一致的目标。未生成任何文件。')
        from .part_derivation import part_mask,histogram
        from itertools import islice
        peers=[decode(raw) for raw,_,local in islice((entry for entry in self.targets.values() if entry[2]),8)]
        self.protected=bytearray(self.image.width()*self.image.height())
        self.part_mask=part_mask(self.image,self.family,peers,self.protected)
        self.base_mask=bytes(self.part_mask);self.mask_overrides={};self.mask_revision=0;self.preview_cache=None
        self.source_histogram=histogram(self.image,self.part_mask)
        self.target_masks={path:part_mask(decode(raw),self.family,[self.image]+peers) for path,(raw,_,_) in self.targets.items()}
        self.setWindowTitle('材质派生');screen=window.screen().availableGeometry();self.resize(min(950,screen.width()-32),min(470,screen.height()-64))
        layout=QVBoxLayout(self)
        source=QLabel(window.tr('来源：','Source: ')+describe(self.path)['name']);source.setToolTip(self.path);layout.addWidget(source)
        split=QSplitter();layout.addWidget(split,1)
        left=QWidget();left_box=QVBoxLayout(left);left_box.setContentsMargins(0,0,0,0);split.addWidget(left)
        self.list=QListWidget();self.list.setMinimumWidth(160);left_box.addWidget(self.list,1)
        checks=QHBoxLayout();left_box.addLayout(checks)
        for title,checked in [('全选',True),('全不选',False)]:
            button=QPushButton(title);button.clicked.connect(lambda value=False,c=checked:self.check_all(c));checks.addWidget(button)
        right=QWidget();right_box=QVBoxLayout(right);right_box.setContentsMargins(0,0,0,0);split.addWidget(right);split.setStretchFactor(1,1)
        for path,(_,_,local) in self.targets.items():
            item=QListWidgetItem(describe(path)['name']+(' · 来源内参考' if local else ' · 原版参考'))
            item.setData(Qt.ItemDataRole.UserRole,path);item.setToolTip(path+'\n'+window.tr('点击查看，勾选后生成。','Click to preview; check to generate.'))
            item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Unchecked);self.list.addItem(item)
        previews=QGridLayout();right_box.addLayout(previews,1);self.before=QLabel();self.reference=QLabel();self.after=QLabel()
        for column,(title,label) in enumerate([('原始纹理',self.before),('目标参考',self.reference),('派生结果',self.after)]):
            previews.addWidget(QLabel(title),0,column)
            label.setMinimumSize(100,120);label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Expanding)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter);previews.addWidget(label,1,column)
        self.details=QLabel();self.details.setWordWrap(True);self.details.hide();right_box.addWidget(self.details)
        controls=QGridLayout();right_box.addLayout(controls);controls.setHorizontalSpacing(8);controls.setVerticalSpacing(6)
        self.ramp_buttons=[]
        for index,title in enumerate(('暗部','主体','高光')):
            button=QPushButton(title);button.clicked.connect(lambda checked=False,i=index:self.edit_ramp(i))
            controls.addWidget(button,1,index);controls.setColumnStretch(index,1);self.ramp_buttons.append(button)
        edit=QPushButton(window.tr('调整换色区域','Adjust recoloring area'));edit.clicked.connect(self.edit_parts)
        controls.addWidget(edit,0,0)
        self.ramp_preview=QLabel();self.ramp_preview.setFixedHeight(24);self.ramp_preview.setMinimumWidth(80)
        self.ramp_preview.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.ramp_preview.setToolTip(window.tr('材质色阶','Material palette'));controls.addWidget(self.ramp_preview,0,1)
        restore=QPushButton('恢复参考色');restore.clicked.connect(self.restore_color);controls.addWidget(restore,0,2)
        self.strength=QSpinBox();self.strength.setRange(0,100);self.strength.setSuffix('%');self.strength.setValue(100);self.strength.setMaximumWidth(90)
        self.tolerance=QSpinBox();self.tolerance.setRange(0,255);self.tolerance.setMaximumWidth(80)
        self.tolerance.setToolTip('0 保留原选区；增大后扩展相连近似色。')
        self.mask_timer=QTimer(self);self.mask_timer.setSingleShot(True);self.mask_timer.timeout.connect(lambda:window.run(self.update_mask))
        self.tolerance.valueChanged.connect(lambda:self.mask_timer.start(120))
        self.notice=QLabel(window.tr(f'已跳过 {self.skipped} 项',f'Skipped {self.skipped} targets'));self.notice.setVisible(bool(self.skipped))
        self.notice.setToolTip('已跳过缺少参考或动画配置不一致的目标。');right_box.addWidget(self.notice)
        actions=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.add_button=actions.button(QDialogButtonBox.StandardButton.Ok)
        actions.accepted.connect(lambda:window.run(self.accept));actions.rejected.connect(self.reject)
        bottom=QHBoxLayout();right_box.addLayout(bottom);bottom.addWidget(QLabel('邻色偏差'));bottom.addWidget(self.tolerance);bottom.addSpacing(10);bottom.addWidget(QLabel(window.tr('强度','Strength')));bottom.addWidget(self.strength);bottom.addStretch();bottom.addWidget(actions)
        self.list.itemChanged.connect(self.sync_actions)
        self.sync_actions()
        self.preview_timer=QTimer(self);self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(lambda:window.run(self.preview))
        self.strength.valueChanged.connect(lambda value:self.preview_timer.start(100))
        self.list.currentRowChanged.connect(lambda:window.run(self.preview))
        self.list.setCurrentRow(0)

    def selected_path(self):
        item=self.list.currentItem();return item.data(Qt.ItemDataRole.UserRole) if item else None

    def checked_paths(self):
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count()) if self.list.item(i).checkState()==Qt.CheckState.Checked]

    def sync_actions(self,*args):
        count=len(self.checked_paths())
        self.add_button.setText(self.window.tr('加入合成台','Add to composition')+f' ({count})')
        self.add_button.setEnabled(bool(count))

    def check_all(self,checked):
        self.list.blockSignals(True)
        try:
            for i in range(self.list.count()):self.list.item(i).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        finally:self.list.blockSignals(False)
        self.sync_actions()

    def restore_color(self):
        path=self.selected_path()
        if path:self.colors[path]=self.reference_colors[path];self.custom_colors.discard(path);self.ramps.pop(path,None);self.preview()

    def current_ramp(self,path):
        if path not in self.ramps:
            from .derivation_reference import material_ramp
            target=decode(self.targets[path][0])
            if path in self.custom_colors:target=recolor(target,self.reference_colors[path],self.colors[path],100)
            self.ramps[path]=material_ramp(target,self.target_masks[path])
        return self.ramps[path]

    def edit_ramp(self,index):
        path=self.selected_path()
        if path is None:return
        from .color_editor import choose_color
        ramp=list(self.current_ramp(path));color=choose_color(QColor(*ramp[index]),self)
        if color.isValid():ramp[index]=(color.red(),color.green(),color.blue());self.ramps[path]=tuple(ramp);self.preview()

    def edit_parts(self):
        from .part_derivation import edit_mask
        if self.mask_timer.isActive():self.mask_timer.stop();self.update_mask()
        mask=edit_mask(self,self.image,self.part_mask)
        if mask is not None:
            from .part_derivation import histogram
            self.mask_overrides.update({i:bool(v) for i,v in enumerate(mask) if v!=self.part_mask[i]})
            self.mask_revision+=1;self.part_mask=mask;self.source_histogram=histogram(self.image,mask);self.preview()

    def update_mask(self):
        from .derivation_reference import expand_mask
        from .part_derivation import histogram
        self.mask_revision+=1
        self.part_mask=expand_mask(self.image,self.base_mask,self.tolerance.value(),self.protected,self.mask_overrides)
        self.source_histogram=histogram(self.image,self.part_mask);self.preview()

    def generate(self,path,preview=False):
        mode='ramp';strength=self.strength.value();ramp=self.current_ramp(path)
        image=QImage(self.image);mask=bytes(self.part_mask);raw=self.targets[path][0];target_mask=bytes(self.target_masks[path]);hist=list(self.source_histogram)
        reference=self.reference_colors[path];color=self.colors[path];custom=path in self.custom_colors
        def work(cancel=None,progress=None):
            return render_target(image,mask,raw,target_mask,strength,hist,reference,color,custom,mode=mode,preview=preview,cancel=cancel,ramp=ramp)
        if preview and self.image.width()*self.image.height()>1024*1024:
            from .task_progress import run_progress
            return run_progress(self,'正在生成派生预览',work)
        return work()

    def preview_result(self,path):
        key=(path,self.strength.value(),self.mask_revision,tuple(self.current_ramp(path)))
        if self.preview_cache is None or self.preview_cache[0]!=key:
            result=self.generate(path,preview=True)
            if result.width()>320 or result.height()>200:
                result=result.scaled(320,200,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation)
            self.preview_cache=(key,result)
        return self.preview_cache[1]

    def preview(self):
        path=self.selected_path()
        if path is None:return
        # Preview only visible-size pixels; generation uses the exact same curves.
        small=self.image
        error_text=''
        try:
            result=self.preview_result(path)
        except ValueError as error:result=None;error_text=str(error)
        from PySide6.QtGui import QIcon
        from PySide6.QtCore import QSize
        ramp=self.current_ramp(path);reference=decode(self.targets[path][0])
        from PySide6.QtGui import QLinearGradient
        strip=QPixmap(max(1,self.ramp_preview.width()),24);p=QPainter(strip)
        gradient=QLinearGradient(0,0,strip.width(),0)
        for stop,rgb in zip((0,.5,1),ramp):gradient.setColorAt(stop,QColor(*rgb))
        p.fillRect(strip.rect(),gradient);p.end();self.ramp_preview.setPixmap(strip)
        for button,rgb in zip(self.ramp_buttons,ramp):
            swatch=QPixmap(18,18);swatch.fill(QColor(*rgb));button.setIcon(QIcon(swatch));button.setIconSize(QSize(18,18));button.setToolTip(QColor(*rgb).name().upper())
        for widget,image in ((self.before,small),(self.reference,reference),(self.after,result)):
            if image is None:widget.clear();continue
            width,height=max(32,widget.width()-4),max(32,widget.height()-4)
            if widget is self.before:image=outlined_preview(image,self.part_mask,width,height)
            elif widget is self.reference:image=outlined_preview(image,self.target_masks[path],width,height)
            else:image=image.scaled(width,height,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation)
            background=QPixmap(image.size());background.fill(QColor('#bbbbbb'));painter=QPainter(background)
            for y in range(0,image.height(),8):
                for x in range(0,image.width(),8):
                    if (x//8+y//8)%2:painter.fillRect(x,y,8,8,QColor('#888888'))
            painter.drawImage(0,0,image);painter.end();widget.setPixmap(background)
        self.details.setText(error_text);self.details.setVisible(bool(error_text))
        self.before.setToolTip(self.window.tr('线框内为来源图的换色范围','Outline: source recoloring area'))
        self.reference.setToolTip(self.window.tr('线框内用于提取参考色阶','Outline: palette sampling area'))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'preview_timer'):self.preview_timer.start(100)

    def validate_targets(self,chosen):
        owner=self.window.source(self.descriptor['origin'])
        if owner is not self.owner or owner.files.get(self.path)!=self.original or owner.files.get(self.path+'.mcmeta')!=self.metadata:
            raise ValueError('来源已变化，请关闭后重新打开派生窗口')
        for path in chosen:
            raw,metadata,local=self.targets[path]
            current_metadata=owner.files.get(path+'.mcmeta')
            if current_metadata is None:current_metadata=self.window.vanilla.get(self.version,path+'.mcmeta')
            current_raw=owner.files.get(path) if local else self.window.vanilla.get(self.version,path)
            if current_raw!=raw or current_metadata!=metadata or not local and path in owner.files:
                raise ValueError('参考素材已变化，请重新打开派生窗口')
            if self.metadata is None and any(layer.enabled and path+'.mcmeta' in layer.files for layer in self.window.layers):
                raise ValueError('合成台已有目标动画配置，不能以静态派生图覆盖：'+path+'。请先取消勾选此目标。')

    def accept(self):
        if self.mask_timer.isActive():self.mask_timer.stop();self.update_mask()
        chosen=self.checked_paths()
        if not chosen:QMessageBox.information(self,'尚未选择目标','请勾选需要生成的目标。');return
        self.validate_targets(chosen)
        if self.image.sizeInBytes()*len(chosen)>256*1024**2:raise ValueError('本次派生超过 256 MiB 像素预算，请减少勾选目标')
        from .task_progress import run_progress
        image=QImage(self.image);mask=bytes(self.part_mask);strength=self.strength.value();hist=list(self.source_histogram);metadata=self.metadata
        jobs=[(path,self.targets[path][0],bytes(self.target_masks[path]),self.reference_colors[path],self.colors[path],path in self.custom_colors,self.current_ramp(path)) for path in chosen]
        mode='ramp'
        files=run_progress(self,'正在生成派生素材',lambda cancel,progress:generate_files(image,mask,jobs,strength,hist,metadata,cancel,progress,mode=mode))
        self.validate_targets(chosen)
        self.output=Layer(self.owner.name+' · 调色派生',files,source='派生自 '+self.owner.name,source_version=self.version,
            asset_versions={path:self.version for path in chosen},selection={'derivation':{
                'method':'reference-v3','reference_mode':mode,'target_ramps':{p:self.current_ramp(p) for p in chosen},'neighbor_tolerance':self.tolerance.value(),'mask_sha256':hashlib.sha256(self.part_mask).hexdigest(),'masked_pixels':sum(self.part_mask),
                'mask_zlib_base64':base64.b64encode(zlib.compress(bytes(self.part_mask))).decode('ascii'),'size':[self.image.width(),self.image.height()],
                'source_path':self.path,'source_sha256':hashlib.sha256(self.original).hexdigest(),
                'strength':self.strength.value(),'source_color':self.base_color,'target_colors':{path:self.colors[path] for path in chosen}}})
        super().accept()


def open_dialog(window,descriptor):
    dialog=DerivationDialog(window,descriptor)
    try:
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        window.remember();window.layers.insert(0,dialog.output);window.changed();window.refresh()
        window.switch_mode(1);window.browse_layer(dialog.output.uid)
        window.statusBar().showMessage('派生结果已作为独立项目项加入；原始素材未改动。可撤销资源操作或移除该项。')
    finally:dialog.deleteLater()


def add_action(window,menu,descriptor):
    if descriptor.get('kind')!='png' or window.source(descriptor['origin']) is None or family(descriptor['path']) is None:return
    stable=copy.deepcopy(descriptor);action=menu.addAction('同系列调色派生…')
    action.triggered.connect(lambda:window.run(lambda:open_dialog(window,stable)))
