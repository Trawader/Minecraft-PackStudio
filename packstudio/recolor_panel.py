"""Embedded, non-destructive recolor preview and independently reviewed frame masks."""
from dataclasses import replace
from PySide6.QtCore import Qt,QSignalBlocker,QSize
from PySide6.QtGui import QImage,QColor,QRegion,QPainter,QPixmap,QIcon
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QSizePolicy,QPushButton,QComboBox,QLabel,QSpinBox,QCheckBox
from .task_progress import run_progress
from .recolor import Settings,render,gui_background,signature,match_region


class RecolorPanel(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window;self.canvas=window.canvas;self.busy=False
        self.frames=[];self.frame_index=-1;self.output=None;self.output_key=None
        self.settings=Settings();layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.tool_settings={'recolor':self.settings,'gradient':Settings(first='#000000',last='#ffffff',transition='smooth')}
        self.toggle=QPushButton('调色');self.toggle.setCheckable(True);layout.addWidget(self.toggle)
        self.body=QWidget();self.body.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum);layout.addWidget(self.body);layout.addStretch();box=QVBoxLayout(self.body);box.setContentsMargins(0,0,0,0)
        self.body_layout=box;self.endpoint_editor=None;self.active_endpoint='first'
        self.gradient_page='colors';self.transition_controls=None
        row=QHBoxLayout();box.addLayout(row);self.mode=QComboBox()
        for label,value in [('明暗渐变','range'),('透明度','opacity'),('颜色','color'),('空间渐变','spatial')]:self.mode.addItem(label,value)
        row.addWidget(self.mode);self.first=QPushButton('#AA96F8');self.last=QPushButton('#eee6ff')
        row.addWidget(self.first);row.addWidget(self.last);self.scope=QComboBox()
        self.scope.addItems(['自动范围','非透明像素','动画全部帧']);self.scope.setToolTip('自动范围：有选区时处理选区，否则全图。动画全部帧需要逐帧确认。');box.addWidget(self.scope);self.scope.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.params=QWidget();params=QGridLayout(self.params);params.setContentsMargins(0,0,0,0);box.addWidget(self.params)
        self.controls={}
        for key,label,minimum,maximum,value in [('saturation','饱和度',-100,100,0),('contrast','对比度',-100,100,0),('brightness','亮度',-100,100,0),('opacity','不透明度%',0,100,100),('smooth','流畅度',0,100,100)]:
            widget=QWidget();r=QHBoxLayout(widget);r.setContentsMargins(0,0,0,0);r.addWidget(QLabel(label));spin=QSpinBox();spin.setRange(minimum,maximum);spin.setValue(value);r.addWidget(spin);params.addWidget(widget,len(self.controls)//2,len(self.controls)%2);self.controls[key]=(widget,spin)
            spin.valueChanged.connect(self.invalidate)
        from .color_controls import ColorControls
        self.color_options=ColorControls(self.invalidate);box.addWidget(self.color_options)
        self.color_options.kind.currentIndexChanged.connect(self.options)
        self.direction=QComboBox()
        for label,value in [('上→下','down'),('下→上','up'),('左→右','right'),('右→左','left'),('左上→右下','diagonal'),('右上→左下','reverse_diagonal')]:self.direction.addItem(label,value)
        params.addWidget(self.direction,2,1);self.direction.currentIndexChanged.connect(self.invalidate)
        row=QHBoxLayout();box.addLayout(row)
        self.prepare_button=QPushButton('分析各帧');row.addWidget(self.prepare_button)
        self.frame_choice=QComboBox();row.addWidget(self.frame_choice,1)
        row=QHBoxLayout();box.addLayout(row)
        self.include=QCheckBox('处理此帧');row.addWidget(self.include)
        self.review=QPushButton('确认此帧选区');row.addWidget(self.review)
        row=QHBoxLayout();box.addLayout(row)
        self.preview_button=QPushButton('预览调色');self.apply_button=QPushButton('应用');self.cancel_button=QPushButton('取消预览')
        for button in (self.preview_button,self.apply_button,self.cancel_button):row.addWidget(button)
        self.note=QLabel('默认有选区时处理选区，无选区时处理全图；预览不写文件，应用可撤销。');self.note.setWordWrap(True);self.note.hide()
        self.toggle.toggled.connect(self.show_body);self.body.hide()
        self.first.clicked.connect(lambda:self.choose('first'));self.last.clicked.connect(lambda:self.choose('last'))
        self.mode.currentIndexChanged.connect(self.options);self.scope.currentIndexChanged.connect(self.scope_changed)
        self.prepare_button.clicked.connect(lambda:window.run(self.prepare_frames));self.frame_choice.currentIndexChanged.connect(self.pick_frame)
        self.include.toggled.connect(self.include_frame);self.review.clicked.connect(lambda:window.run(self.review_frame))
        self.preview_button.clicked.connect(lambda:window.run(self.preview));self.apply_button.clicked.connect(lambda:window.run(self.apply))
        self.cancel_button.clicked.connect(self.invalidate)
        self.canvas.selectionChanged.connect(self.selection_changed);self.canvas.viewChanged.connect(self.view_changed)
        self.canvas.changed.connect(self.reset);self.canvas.strokeUpdated.connect(self.reset)
        self.canvas.adjustmentRequested.connect(lambda:window.run(self.preview))
        self.canvas.gradientRequested.connect(lambda start,end:window.run(lambda:self.drag_gradient(start,end)))
        from .recolor_settings import RecolorSettings
        self.shared_controls=RecolorSettings();box.insertWidget(0,self.shared_controls)
        self.shared_controls.changed.connect(self.options)
        self.update_color_buttons()
        window.docks['editor'].widget().layout().addWidget(self);self.options();self.scope_changed()

    def show_body(self,show):
        self.body.setVisible(show);self.toggle.setText('调色')
        if not show:self.invalidate()

    def choose(self,key):
        if getattr(self,'tool_kind',None)=='gradient':
            self.active_endpoint=key;self.endpoint_editor.set_color(QColor(getattr(self.settings,key)))
            self.update_color_buttons();return
        from .color_editor import choose_color
        color=choose_color(QColor(getattr(self.settings,key)),self)
        if color.isValid():
            setattr(self.settings,key,color.name());self.update_color_buttons();self.invalidate()

    def update_color_buttons(self):
        for key in ('first','last'):
            color=QColor(getattr(self.settings,key));button=getattr(self,key)
            swatch=QPixmap(20,20);swatch.fill(color)
            button.setIcon(QIcon(swatch));button.setIconSize(QSize(20,20));button.setText(color.name().upper())
            if getattr(self,'tool_kind',None)=='gradient':
                button.setToolTip(self.window.tr('起点颜色','Start color') if key=='first' else self.window.tr('终点颜色','End color'))
            else:button.setToolTip('')
            button.setCheckable(getattr(self,'tool_kind',None)=='gradient')
            button.setChecked(getattr(self,'tool_kind',None)=='gradient' and key==self.active_endpoint)

    def edit_endpoint(self,color):
        if getattr(self,'tool_kind',None)!='gradient':return
        setattr(self.settings,self.active_endpoint,color.name(QColor.NameFormat.HexArgb))
        self.update_color_buttons();self.invalidate()

    def drag_gradient(self,start,end):
        self.check_editable()
        if start==end:return
        self.select_tool('gradient')
        self.scope.setCurrentIndex(0)
        self.settings.start=tuple(start);self.settings.end=tuple(end)
        self.preview()
        if self.output is not None:self.apply()

    def options(self,*args):
        gradient=getattr(self,'tool_kind',None)=='gradient'
        mode=self.mode.currentData();self.first.setVisible(mode in ('range','spatial'));self.last.setVisible(gradient or mode in ('range','spatial'))
        for key,(widget,_) in self.controls.items():
            widget.setVisible((mode=='opacity' and key=='opacity') or (mode=='adjust' and key in ('saturation','contrast','brightness')) or ((gradient or mode=='spatial') and key=='smooth'))
        self.params.setVisible(mode=='opacity' and not gradient)
        self.direction.setVisible(mode=='spatial')
        self.color_options.setVisible(mode=='color' and not gradient)
        if hasattr(self,'shared_controls'):
            self.shared_controls.setVisible(not gradient)
            self.mode.hide();self.params.hide();self.color_options.hide()
            if not gradient:self.first.hide();self.last.hide()
        self.invalidate()
        dialog=getattr(self.window,'recolor_window',None)
        if dialog and dialog.isVisible():dialog.request_fit()

    def select_tool(self,kind):
        if not hasattr(self,'tool_modes'):
            self.tool_modes=[(self.mode.itemText(i),self.mode.itemData(i)) for i in range(self.mode.count())]
            self.last_modes={'gradient':'spatial','recolor':'range'}
        previous=getattr(self,'tool_kind',None)
        if previous:self.last_modes[previous]=self.mode.currentData()
        self.tool_kind=kind
        self.settings=self.tool_settings[kind];self.update_color_buttons()
        self.preview_button.setText('预览渐变' if kind=='gradient' else '预览调色')
        with QSignalBlocker(self.mode):
            self.mode.clear()
            for label,value in self.tool_modes:
                if value in (('spatial',) if kind=='gradient' else ('range','opacity','color')):
                    self.mode.addItem(label,value)
            self.mode.setCurrentIndex(max(0,self.mode.findData(self.last_modes[kind])))
        self.options()
        if kind=='gradient' and self.transition_controls is None:
            from .gradient_controls import TransitionControls
            self.transition_controls=TransitionControls(self);self.body_layout.addWidget(self.transition_controls)
        if kind=='gradient' and self.endpoint_editor is None:
            from .color_editor import ColorEditor
            self.endpoint_editor=ColorEditor(QColor(self.settings.first),self,embedded=True)
            self.body_layout.insertWidget(1,self.endpoint_editor)
            self.endpoint_editor.colorChanged.connect(self.edit_endpoint)
        if self.endpoint_editor is not None:
            self.endpoint_editor.setVisible(kind=='gradient' and self.gradient_page=='colors')
            if kind=='gradient':self.endpoint_editor.set_color(QColor(getattr(self.settings,self.active_endpoint)))
        self.mode.hide()
        if self.transition_controls is not None:self.transition_controls.setVisible(kind=='gradient' and self.gradient_page=='transition')
        if kind=='gradient':
            self.first.setVisible(self.gradient_page=='colors');self.last.setVisible(self.gradient_page=='colors')
        self.params.hide()
        self.scope.setVisible(kind!='gradient')
        for button in (self.preview_button,self.apply_button,self.cancel_button):button.setVisible(kind!='gradient')
        self.note.hide()
        if kind=='gradient':
            self.direction.hide();self.scope.setCurrentIndex(0)

    def configuration(self):
        if getattr(self,'tool_kind',None)!='gradient':return self.shared_controls.settings()
        mode=self.mode.currentData();values={key:spin.value() for key,(_,spin) in self.controls.items()}
        if getattr(self,'tool_kind',None)=='gradient':mode='spatial';values['smooth']=self.settings.smooth
        if mode!='adjust':values.update(saturation=0,contrast=0,brightness=0)
        values.update(self.color_options.values())
        return replace(self.settings,mode=mode,direction=self.direction.currentData(),**values)

    def identity(self):
        return self.canvas.image.cacheKey(),tuple(self.canvas.regions or ()),self.window.current_source,repr(self.window.current)

    def invalidate(self,*args):
        had_preview=self.output is not None
        self.output=None;self.output_key=None;self.canvas.color_preview=None;self.canvas.update();self.apply_button.setEnabled(False)
        if had_preview and self.window.current:self.window.live_texture()

    def reset(self,*args):
        if self.busy:return
        self.invalidate();self.frames=[];self.frame_index=-1
        self.frame_choice.blockSignals(True);self.frame_choice.clear();self.frame_choice.blockSignals(False)

    def view_changed(self):
        self.settings.start=None;self.settings.end=None
        if not self.busy:self.reset()

    def scope_changed(self,*args):
        self.reset();multi=self.scope.currentIndex()==2
        for widget in (self.prepare_button,self.frame_choice,self.include,self.review):widget.setVisible(multi)

    def check_editable(self):
        animation=getattr(self.window,'animation_editor',None)
        if animation:animation.stop()
        if not self.window.current or self.canvas.image.isNull():raise ValueError('请先打开要编辑的贴图。')
        if self.canvas.read_only:raise ValueError('当前素材只读，请加入项目副本后调色。')
        if self.canvas.drawing or self.canvas.move_origin is not None:raise ValueError('请先结束笔画或确认选区移动。')
        if getattr(self.window,'large_view_only',False):raise ValueError('当前大图只支持预览。')

    def selected(self):
        if self.scope.currentIndex()==1:return self.canvas.view_region()
        if self.canvas.selection_region.isEmpty():
            if self.scope.currentIndex()==2:raise ValueError('请先为参考帧建立选区，再分析全部帧。')
            return self.canvas.view_region()
        return QRegion(self.canvas.selection_region)


    def prepare_frames(self):
        self.check_editable();animation=self.window.animation_editor
        from .capabilities import frame_reason
        reason=frame_reason(self.window)
        if reason:raise ValueError(reason)
        if not animation.frames or animation.mode.currentIndex()!=0:raise ValueError('请打开动画并切换到单帧编辑。')
        rects=set(frame[1] for frame in animation.frames)
        if len(rects)>256 or sum(r[2]*r[3] for r in rects)>4*1024*1024:raise ValueError('此动画超过本次交互分析范围（256 帧／400 万像素），请先逐帧处理。')
        region=self.selected();image=QImage(self.canvas.image);view=QImage(self.canvas.view_image())
        current=tuple(self.canvas.regions[0]);weights=dict(self.canvas.selection_weights);entries=list(animation.frames)
        def analyze_frames(cancel,progress):
            reference=signature(view,region);frames=[];seen=set()
            for number,(index,rect,_) in enumerate(entries):
                if cancel.is_set():raise InterruptedError('已取消动画分析')
                progress(number,len(entries))
                if rect in seen:continue
                seen.add(rect)
                mask,confident=(QRegion(region),True) if tuple(rect)==current else match_region(image.copy(*rect),reference)
                frames.append({'index':index,'rect':rect,'mask':mask,'weights':weights if tuple(rect)==current else {},'reviewed':tuple(rect)==current,'include':True,'confident':confident})
            progress(len(entries),len(entries));return frames
        try:frames=run_progress(self.window,'正在分析动画各帧',analyze_frames)
        except InterruptedError:self.note.setText('已取消动画分析，原图未修改。');return
        self.reset();self.busy=True
        try:
            self.frames=frames
            for frame in frames:
                self.frame_choice.addItem(f"帧 {frame['index']} · "+('参考帧' if frame['reviewed'] else '待确认' if frame['confident'] else '识别不确定'))
            self.frame_index=-1;self.frame_choice.setCurrentIndex(next(i for i,f in enumerate(self.frames) if tuple(f['rect'])==current))
        finally:self.busy=False
        self.pick_frame(self.frame_choice.currentIndex());self.note.setText('各帧已独立分析。逐帧检查／修正并确认；不需要的帧取消“处理此帧”。')

    def pick_frame(self,index):
        if self.busy or not 0<=index<len(self.frames):return
        self.invalidate();self.frame_index=index;frame=self.frames[index];self.busy=True
        try:
            animation=self.window.animation_editor
            row=next((i for i,f in enumerate(animation.frames) if f[1]==frame['rect']),-1)
            if row>=0:animation.cards.setCurrentRow(row)
            self.canvas.set_atlas(self.canvas.image,[frame['rect']],(self.window.current_source,self.window.current[0]))
            self.canvas.selection_region=QRegion(frame['mask']);self.canvas.selection_weights=dict(frame['weights']);self.canvas.sync_selection()
            self.include.setChecked(frame['include']);self.window.set_tool('select')
        finally:self.busy=False
        self.note.setText(f"帧 {frame['index']}："+('已确认' if frame['reviewed'] else '请检查识别范围，Shift／Alt 修正后确认'))

    def selection_changed(self,*args):
        if self.busy:return
        self.invalidate()
        if 0<=self.frame_index<len(self.frames):
            frame=self.frames[self.frame_index];frame['mask']=QRegion(self.canvas.selection_region);frame['weights']=dict(self.canvas.selection_weights);frame['reviewed']=False

    def include_frame(self,value):
        if self.busy:return
        if 0<=self.frame_index<len(self.frames):self.frames[self.frame_index]['include']=value
        self.invalidate()

    def review_frame(self):
        if 0<=self.frame_index<len(self.frames):
            frame=self.frames[self.frame_index]
            if frame['mask'].isEmpty():raise ValueError('此帧选区为空，请修正或取消处理。')
            frame['reviewed']=True;self.frame_choice.setItemText(self.frame_index,f"帧 {frame['index']} · 已确认")
            self.note.setText('此帧范围已确认。');self.invalidate()

    def preview(self):
        self.check_editable();config=self.configuration()
        if getattr(self,'tool_kind',None)=='gradient' and config.start is None:return
        self.window.texture_timer.stop()
        if self.scope.currentIndex()==2:
            if not self.frames:raise ValueError('请先分析各帧并确认范围。')
            active=[frame for frame in self.frames if frame['include']]
            if not active:raise ValueError('没有勾选要处理的帧。')
            if any(not f['reviewed'] for f in active):raise ValueError('仍有未确认的帧，请逐帧确认或取消处理。')
            original=QImage(self.canvas.image)
            active=[dict(f,mask=QRegion(f['mask']),weights=dict(f['weights'])) for f in active]
            def work(cancel,progress):
                output=QImage(original)
                for i,frame in enumerate(active):
                    rect=frame['rect']
                    patch=render(original.copy(*rect),frame['mask'],config,frame['weights'],cancel,
                        lambda done,total:progress(i*1000+done*1000//max(1,total),len(active)*1000))
                    painter=QPainter(output);painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source);painter.drawImage(rect[0],rect[1],patch);painter.end()
                return output
            try:output=run_progress(self.window,'正在处理动画调色',work)
            except InterruptedError:self.invalidate();self.note.setText('已取消，原图未修改。');return
            self.output=output;self.canvas.color_preview=output.copy(*self.frames[self.frame_index]['rect'])
            self.note.setText(f'已预览 {len(active)} 帧；每帧分别计算色阶，应用仅记录一次撤销。')
        else:
            image=QImage(self.canvas.view_image());region=QRegion(self.selected());weights=dict(self.canvas.selection_weights) if self.scope.currentIndex()==0 else {}
            try:self.output=run_progress(self.window,'正在生成调色预览',lambda cancel,progress:render(image,region,config,weights,cancel,progress))
            except InterruptedError:self.invalidate();self.note.setText('已取消，原图未修改。');return
            self.canvas.color_preview=QImage(self.output);self.note.setText('画板正在显示预览。应用写入源图；取消不改文件。')
        self.output_key=self.identity();self.apply_button.setEnabled(True);self.canvas.update()
        self.render_preview()

    def render_preview(self):
        from .sky_view import sync_preview
        if sync_preview(self.window,self.canvas.color_preview):return
        preview=self.window.preview
        if self.window.animation_editor.frames or getattr(self.window,'edit_bindings',None) or not preview.faces:
            preview.flat_image=QImage(self.canvas.color_preview)
        else:
            if self.canvas.regions:
                image=QImage(self.canvas.image);painter=QPainter(image);painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source);top=0
                for x,y,width,height in self.canvas.regions:
                    painter.drawImage(x,y,self.canvas.color_preview.copy(0,top,width,height));top+=height
                painter.end()
            else:image=QImage(self.canvas.color_preview)
            preview.image=image
            if self.window.current[0] in preview.textures:preview.textures[self.window.current[0]]=image
        preview.update()

    def apply(self):
        self.check_editable()
        if self.output is None or self.output_key!=self.identity():self.invalidate();raise ValueError('预览已失效，请重新预览后应用。')
        output=QImage(self.output);whole=self.scope.currentIndex()==2
        before=self.canvas.image if whole else self.canvas.view_image()
        if output==before:self.invalidate();return
        self.canvas.checkpoint(label='渐变' if getattr(self,'tool_kind','recolor')=='gradient' else '调色');self.invalidate()
        if whole:self.canvas.image=output
        else:self.canvas.replace_view(output)
        self.canvas.changed.emit();self.canvas.update();self.note.setText('已应用，可撤销／重做。')
