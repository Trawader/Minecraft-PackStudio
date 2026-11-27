"""Session timeline with global barriers for resource-wide transactions."""
import copy
from PySide6.QtCore import QObject,QTimer,Qt,QSignalBlocker,QEvent
from PySide6.QtWidgets import QWidget,QDockWidget,QVBoxLayout,QHBoxLayout,QListWidget,QPushButton
from PySide6.QtGui import QImage,QColor
from shiboken6 import isValid


class History(QObject):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.done=[];self.future=[];self.pending={};self.busy=False;self.dialog=None
        self.editors=[];self.revision=0;self.preview_saved=None
        window.canvas.installEventFilter(self);window.preview.installEventFilter(self)
        self.attach(window)
        action=window.window_menu.addAction('历史记录');action.setCheckable(True)
        menu=window.window_menu;menu.removeAction(action)
        actions=menu.actions();index=actions.index(window.docks['render'].toggleViewAction())+1
        menu.insertAction(actions[index] if index<len(actions) else None,action)
        def order_menu():
            menu.removeAction(window.reset_workspace_action);menu.addAction(window.reset_workspace_action)
        menu.aboutToShow.connect(order_menu);order_menu()
        action.triggered.connect(lambda checked:self.show() if checked else self.dialog.hide() if self.dialog else None)
        self.action=action

    def attach(self,editor):
        if editor in self.editors:return
        self.editors.append(editor);editor.canvas.timeline=self;editor.canvas.timeline_editor=editor

    def key(self,editor):
        return (editor.current_source,editor.current[0]) if editor.current else None

    def checkpoint(self,canvas,state):
        if self.busy:return
        self.flush()
        editor=canvas.timeline_editor;key=self.key(editor)
        owner=self.window.source(key[0]) if key else None
        if owner is None:return
        if state['pixel_edit'] and '_label' not in state:
            state['_label']={'pencil':'画笔','eraser':'橡皮擦','magic_eraser':'魔术橡皮擦','bucket':'油漆桶','fill':'填充','burn':'加深','dodge':'减淡','lighten':'变明','darken':'变暗','mouse':'移动'}.get(canvas.tool,'图像编辑')
        self.pending[canvas]=(editor,key,state,owner.files.get(key[1]),copy.deepcopy(editor.current))
        QTimer.singleShot(0,self.flush)

    def flush(self):
        if self.busy or getattr(self,'preview_saved',None) is not None:return
        for canvas,(editor,key,before,raw,current) in list(self.pending.items()):
            if not isValid(canvas):self.pending.pop(canvas,None);continue
            if canvas.drawing or canvas.task_running or getattr(canvas,'timeline_committing',False):continue
            self.pending.pop(canvas,None)
            after=canvas.snapshot(before['pixel_edit'])
            if before['image']==after['image'] and before['selection']==after['selection'] and before['weights']==after['weights']:continue
            owner=self.window.source(key[0])
            if owner is None:continue
            large=before['pixel_edit'] and before['image'].width()*before['image'].height()>4*1024*1024
            label=('大图编辑 · ' if large else '')+(before.get('_label','图像编辑') if before['pixel_edit'] else '选区')+' · '+key[1].rsplit('/',1)[-1]
            self.append(dict(kind='canvas',barrier=large,label=label,key=key,before=before,after=after,raw_before=raw,raw_after=owner.files.get(key[1]),current=current,canvas=canvas))

    def append(self,entry):
        if self.busy:return
        self.done.append(entry);self.future.clear();self.revision+=1
        from .history_changes import LIMIT
        total=sum(e.get('cost',0) for e in self.done)
        for old in self.done:
            if total<=LIMIT:break
            if old['kind']=='group':
                total-=old['cost'];label=old['label'];old.clear()
                old.update(kind='blocked',label=label,reason='暂存预算已用尽，恢复内容已释放')
        for i,old in enumerate(self.done):
            pool=self.window.resource_history if old['kind']=='resource' else getattr(self.window,'batch_recolor_history',[]) if old['kind']=='batch' else None
            if pool is not None and not any(item is old['entry'] for item in pool):
                label=old['label'];old.clear();old.update(kind='blocked',label=label,reason='恢复记录已过期，无法回滚')
        # Images are implicitly shared with the existing canvas snapshots.
        while len(self.done)>60:self.done.pop(0)
        def cost(e):return sum(e[k]['image'].sizeInBytes() for k in ('before','after')) if e['kind']=='canvas' else 0
        while len(self.done)>1 and sum(map(cost,self.done))>128*1024*1024:self.done.pop(0)
        self.sync()

    def resource(self,entry):
        if self.busy:return
        self.flush()
        if any(e.get('entry') is entry for e in self.done):return
        from .resource_history import LibraryChange
        if isinstance(entry,LibraryChange):label='素材操作 · '+entry.after.name
        else:
            label='加入项目' if len(entry.after)>len(entry.before) else '删除项目项' if len(entry.after)<len(entry.before) else '项目操作'
        self.append(dict(kind='resource',label=label,entry=entry))

    def batch(self,entry):
        self.flush();self.append(dict(kind='batch',label=f'批量调色 · {len(entry[2])} PNG',entry=entry))

    def available(self,redo=False,barriers=False):
        self.flush();items=self.future if redo else self.done
        return bool(items) and not items[-1].get('invalid') and items[-1]['kind']!='blocked' and (barriers or items[-1]['kind']=='canvas' and not items[-1].get('barrier')) and not self.busy and not any(isValid(e.canvas) and (e.canvas.drawing or e.canvas.task_running) for e in self.editors if isValid(e))

    def canvas_apply(self,entry,redo):
        w=self.window;origin,path=entry['key'];owner=w.source(origin)
        source=entry['raw_before' if redo else 'raw_after'];target=entry['raw_after' if redo else 'raw_before']
        if owner is None or owner.files.get(path)!=source:raise ValueError('资源已发生其他修改，无法安全回滚：'+path)
        if w.is_builtin({'origin':origin}):raise ValueError('只读资源无法回滚')
        state=entry['after' if redo else 'before'];canvas=entry['canvas']
        active=isValid(canvas) and self.key(canvas.timeline_editor)==entry['key'] and canvas.image==entry['before' if redo else 'after']['image']
        if active:
            canvas.regions=list(state['view']) or None
            canvas.restore_snapshot(state);canvas.update()
        else:
            d={'origin':origin,'path':path,'kind':'png','name':path.rsplit('/',1)[-1]}
            w.edit_descriptor(d)
            if self.key(w)!=(origin,path):raise InterruptedError('已取消打开回滚目标，资源未修改')
            w.canvas.regions=list(state['view']) or None;w.canvas.restore_snapshot(state);w.canvas.update()
        # Preserve exact bytes, so older transactions' conflict checks remain valid.
        owner.files[path]=target
        if not origin.startswith('stage:'):w.library_store.queue(owner);w.library_save_timer.start(400)
        else:w.changed()
        w.resource_editors.sync()

    def step(self,redo=False,barriers=False):
        self.clear_preview()
        if not self.available(redo,barriers):return False
        items=self.future if redo else self.done;entry=items[-1];w=self.window
        self.busy=True
        try:
            if entry['kind']=='canvas':self.canvas_apply(entry,redo)
            elif entry['kind']=='group':
                from .history_changes import apply
                apply(w,entry,redo)
            elif entry['kind']=='batch':
                from .batch_recolor import apply_batch,undo_batch
                item=entry['entry'];origin,uid,before,after,metadata=item
                if redo:
                    apply_batch(w,origin,w.source(origin),before,metadata,after)
                    entry['entry']=w.batch_recolor_history[-1]
                else:
                    if not getattr(w,'batch_recolor_history',[]) or w.batch_recolor_history[-1] is not item:raise ValueError('该批量记录已过期，无法回滚')
                    undo_batch(w)
            else:
                from .resource_history import LibraryChange,restore
                item=entry['entry']
                if redo:
                    if isinstance(item,LibraryChange):
                        owner=w.source(item.origin)
                        if owner!=item.before:raise ValueError('素材已变化，无法重做')
                        restore(owner,item.after)
                        try:w.library_store.put(owner)
                        except Exception:restore(owner,item.before);raise
                    else:
                        if w.layers!=item.before:raise ValueError('项目已变化，无法重做')
                        w.layers=[w.clone_layer(l) for l in item.after]
                    w.resource_history.append(item);w.clear_editor();w.changed();w.refresh()
                else:
                    if not w.resource_history or w.resource_history[-1] is not item:raise ValueError('该资源记录已过期，无法回滚')
                    w.undo_resource()
            items.pop();(self.done if redo else self.future).append(entry);self.revision+=1
        except ValueError as error:
            entry['invalid']=True;entry['reason']=str(error);self.revision+=1
            raise
        finally:self.busy=False;self.sync()
        return True

    def entries(self):
        return self.done+list(reversed(self.future))

    def rollback(self):
        row=self.list.currentRow();self.clear_preview()
        if not self.can_rollback(row):return
        while len(self.done)>row+1:
            if not self.step(barriers=True):break
        while len(self.done)<row+1:
            if not self.step(redo=True,barriers=True):break

    def can_rollback(self,row):
        entries=self.entries()
        if not 0<=row<len(entries) or row==len(self.done)-1:return False
        crossed=entries[min(row+1,len(self.done)):max(row+1,len(self.done))]
        return all(e['kind']!='blocked' and not e.get('invalid') for e in crossed)

    def eventFilter(self,obj,event):
        if event.type() in (QEvent.Type.MouseButtonPress,QEvent.Type.KeyPress,QEvent.Type.Wheel):self.clear_preview()
        return False

    def clear_preview(self):
        saved=getattr(self,'preview_saved',None)
        if saved is None:return
        self.preview_saved=None;w=self.window;c=w.canvas
        with QSignalBlocker(c):
            c.regions=list(saved['state']['view']) or None;c.restore_snapshot(saved['state'])
        c.color_preview=saved['color_preview'];c.read_only=saved['read_only'];c.update()
        for key,value in saved['preview'].items():setattr(w.preview,key,value)
        if 'page' in saved:w.set_preview_page(saved['page'])
        if 'caption' in saved:w.caption.setText(saved['caption'])
        w.preview.update()

    def history_hidden(self,visible):
        if visible:return
        self.clear_preview()
        with QSignalBlocker(self.list):self.list.clearSelection();self.list.setCurrentRow(-1)
        self.rollback_button.setEnabled(False)

    def preview_row(self,row):
        self.clear_preview();self.flush();self.rollback_button.setEnabled(self.can_rollback(row))
        entries=self.entries()
        if not 0<=row<len(entries):return
        w=self.window;c=w.canvas
        if c.drawing or c.task_running or c.move_origin is not None:return
        if hasattr(w,'texture_timer'):w.texture_timer.stop()
        if hasattr(w,'animation_editor'):w.animation_editor.stop()
        entry=entries[row];state=None;files=None
        if entry['kind']=='canvas':state=entry['after']
        elif entry['kind']=='batch':files=entry['entry'][3]
        elif entry['kind']=='group':
            candidates=[pair[1] for group in entry['changes'].values() for pair in group.values() if pair[1] is not None]
            current=w.current[0] if w.current else None
            candidates.sort(key=lambda item:current not in item.files)
            if candidates:files=candidates[0].files
            else:files={}
        elif entry['kind']=='resource':
            after=entry['entry'].after
            if isinstance(after,list):after=after[0] if after else None
            files=after.files if after is not None else {}
        if state is None and files:
            from .core import decode
            paths=[p for p in files if p.lower().endswith('.png')]
            current=w.current[0] if w.current else None
            if current in paths:paths.remove(current);paths.insert(0,current)
            for path in paths:
                try:
                    state=c.snapshot();state.update(image=decode(files[path]),selection=type(c.selection_region)(),weights={},view=());break
                except ValueError:continue
        if state is None and files is not None:
            state=c.snapshot();state.update(image=QImage(),selection=type(c.selection_region)(),weights={},view=())
        if state is None:return
        self.preview_saved={'state':c.snapshot(),'color_preview':c.color_preview,'read_only':c.read_only,
            'preview':{key:copy.copy(getattr(w.preview,key)) for key in ('image','flat_image','faces','textures','sky_image','sky_cache') if hasattr(w.preview,key)}}
        if hasattr(w,'preview_stack'):
            self.preview_saved['page']=w.preview_stack.currentWidget();w.set_preview_page(w.preview_panel)
        if hasattr(w,'caption'):
            self.preview_saved['caption']=w.caption.text();w.caption.setText(self.label(entry))
        with QSignalBlocker(c):
            c.regions=list(state['view']) or None;c.restore_snapshot(state)
        c.color_preview=None;c.read_only=True;c.update()
        if entry['kind']=='canvas' and self.key(w)==entry['key']:w.live_texture()
        else:
            w.preview.sky_image=None;w.preview.sky_cache=None;w.preview.faces=[];w.preview.flat_image=c.view_image();w.preview.image=c.view_image();w.preview.update()

    def reset(self):
        self.clear_preview()
        self.pending.clear();self.done.clear();self.future.clear();self.revision+=1;self.sync()

    def external_undo(self,item):
        if self.busy:return
        if self.done and self.done[-1].get('entry') is item:
            self.future.append(self.done.pop());self.revision+=1;self.sync()

    def sync(self):
        self.editors=[editor for editor in self.editors if isValid(editor)]
        for editor in self.editors:
            if not isValid(editor):continue
            for button,items in zip(editor.history_buttons,(self.done,self.future)):
                button.setEnabled(bool(items) and not items[-1].get('invalid') and items[-1]['kind']=='canvas' and not items[-1].get('barrier') and not self.busy)
        if self.dialog and isValid(self.dialog):
            stamp=(self.revision,self.window.lang)
            if getattr(self,'_displayed',None)==stamp:return
            self._displayed=stamp
            selected=self.list.currentRow();blocker=QSignalBlocker(self.list);self.list.clear()
            for entry in self.done:
                self.list.addItem(self.window.tr('● ','● ')+self.label(entry))
                if entry.get('reason'):
                    from .localization import text
                    item=self.list.item(self.list.count()-1);item.setText(self.window.tr('不可回滚 · ','Cannot roll back · ')+self.label(entry));item.setToolTip(text(entry['reason'],self.window.lang));item.setForeground(QColor('#888888'))
            for entry in reversed(self.future):
                self.list.addItem(self.window.tr('○ 已撤销 · ','○ Undone · ')+self.label(entry))
                if entry.get('reason'):
                    from .localization import text
                    item=self.list.item(self.list.count()-1);item.setToolTip(text(entry['reason'],self.window.lang));item.setForeground(QColor('#888888'))
            self.list.setCurrentRow(min(selected,self.list.count()-1))
            self.rollback_button.setEnabled(self.can_rollback(self.list.currentRow()));self.redo_button.setEnabled(bool(self.done) and not self.done[-1].get('invalid') and self.done[-1]['kind']!='blocked')

    def label(self,entry):
        from .localization import text
        return text(entry['label'],self.window.lang)

    def show(self):
        self.flush()
        if self.dialog is None:
            self.dialog=QDockWidget('历史记录',self.window);self.dialog.setObjectName('studio-operation-history')
            from .dock_chrome import configure,fit_floating
            configure(self.dialog,close_button=True,floating_only=True);content=QWidget();self.dialog.setWidget(content)
            self.window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,self.dialog)
            self.dialog.setFloating(True);self.dialog.resize(520,420);fit_floating(self.dialog)
            self.dialog.visibilityChanged.connect(self.action.setChecked)
            box=QVBoxLayout(content);self.list=QListWidget();box.addWidget(self.list)
            row=QHBoxLayout();box.addLayout(row)
            self.rollback_button=QPushButton('回滚到选定操作');self.redo_button=QPushButton('回滚一步')
            self.rollback_button.setAutoDefault(False);self.redo_button.setAutoDefault(False)
            row.addWidget(self.redo_button);row.addWidget(self.rollback_button)
            self.list.currentRowChanged.connect(self.preview_row)
            self.dialog.visibilityChanged.connect(self.history_hidden)
            self.rollback_button.clicked.connect(lambda:self.window.run(self.rollback))
            self.redo_button.clicked.connect(lambda:self.window.run(lambda:self.step(barriers=True)))
        self.sync()
        count=self.list.count();metrics=self.list.fontMetrics()
        width=max(280,min(480,max((metrics.horizontalAdvance(self.list.item(i).text())+56 for i in range(count)),default=280)))
        self.dialog.resize(width,max(180,min(14,max(3,count))*(metrics.height()+12)+100))
        self.dialog.show();self.dialog.raise_()
        from .dock_chrome import fit_floating
        fit_floating(self.dialog)
