"""Pack metadata defaults, square cover cropping and export options."""
import copy,json,re
from pathlib import Path
from PySide6.QtCore import Qt,QRect,QPoint,Signal
from PySide6.QtGui import QColor,QImage,QPixmap,QPainter,QPen
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPlainTextEdit,
    QComboBox,QPushButton,QDialogButtonBox,QFileDialog,QMessageBox,QMenu,QWidget,QSlider)
from .core import decode,png,compose,newer_pack_sources,VERSIONS,write_zip
from .versions import metadata_format,FORMATS
from .adaptation import export_composition

COLORS=['000000','0000aa','00aa00','00aaaa','aa0000','aa00aa','ffaa00','aaaaaa','555555','5555ff','55ff55','55ffff','ff5555','ff55ff','ffff55','ffffff']
COLOR_NAMES=['黑 / Black','深蓝 / Dark blue','深绿 / Dark green','湖蓝 / Dark aqua','深红 / Dark red','紫 / Purple','金 / Gold','灰 / Gray','深灰 / Dark gray','蓝 / Blue','绿 / Green','青 / Aqua','红 / Red','粉 / Pink','黄 / Yellow','白 / White']

def text_value(value):
    if isinstance(value,str):return value
    if isinstance(value,list):return ''.join(text_value(v) for v in value)
    if isinstance(value,dict):return str(value.get('text',value.get('translate','')))+text_value(value.get('extra',[]))
    return ''

def defaults(layers):
    result={'filename':'MyPack','metadata':None,'raw':None,'cover':None,'title':'','body':''}
    named=False;fallback=None
    for layer in reversed(layers):
        if not layer.enabled or layer.kind!='pack':continue
        if not named:
            result['filename']=Path(layer.source).stem if layer.source and ' + ' not in layer.source else layer.name.split(' (from ')[0]
            named=True
        if result['raw'] is None and 'pack.mcmeta' in layer.files:
            try:
                metadata=json.loads(layer.files['pack.mcmeta'].decode('utf-8-sig'))
                if not isinstance(metadata,dict) or not isinstance(metadata.get('pack'),dict):raise ValueError('Invalid metadata')
                description=text_value(metadata['pack'].get('description',''))
                if fallback is None:fallback=(metadata,layer.files['pack.mcmeta'])
                if description:
                    result['metadata']=metadata;result['raw']=layer.files['pack.mcmeta']
                    result['title'],_,result['body']=description.partition('\n')
            except (ValueError,UnicodeError):pass
        if result['cover'] is None and 'pack.png' in layer.files and 'pack.png' not in layer.selection.get('unmapped_paths',[]):
            try:decode(layer.files['pack.png']);result['cover']=layer.files['pack.png']
            except ValueError:pass
    if result['raw'] is None and fallback:result['metadata'],result['raw']=fallback
    return result

def zip_name(value):
    name=value[:-4] if value.lower().endswith('.zip') else value
    if not name or name!=name.strip() or name.endswith('.') or re.search(r'[<>:"/\\|?*\x00-\x1f]',name):
        raise ValueError('文件名为空或含无效字符 / Invalid filename')
    if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'{p}{n}' for p in ('COM','LPT') for n in range(1,10)]}:
        raise ValueError('Windows 保留文件名 / Reserved filename')
    return name+'.zip'

def prepare_files(layers,vanilla,working_version,base,version,title,body,cover,fill_policy=None,report_out=None):
    if version not in (*VERSIONS,'unchanged'):raise ValueError('请选择版本 / Choose a version')
    from .original_export import target_version,compose_original
    effective=target_version(layers) if version=='unchanged' else version
    if effective is None:files=compose_original(layers,vanilla,working_version)
    else:
        files,report=export_composition(layers,vanilla,effective,working_version,fill_policy)
        if report_out is not None:report_out.extend(report)
    if report_out is not None:
        from .export_history import composition_notes
        report_out.extend(composition_notes(layers))
    changed=(title,body)!=(base['title'],base['body'])
    if base['raw'] is not None:files['pack.mcmeta']=base['raw']
    format_changed=False
    if effective and base['metadata']:
        from .versions import detect
        format_changed=effective not in detect({'pack.mcmeta':base['raw']})
    if version!='unchanged' or changed or format_changed or effective and base['raw'] is None:
        metadata=copy.deepcopy(base['metadata']) or {'pack':{'pack_format':1}}
        if effective:
            metadata_format(metadata['pack'],effective)
        if changed or 'description' not in metadata['pack']:
            metadata['pack']['description']=title+('\n'+body if body else '')
        files['pack.mcmeta']=json.dumps(metadata,ensure_ascii=False,indent=2).encode('utf-8')
    if cover is not None:files['pack.png']=cover
    return files

class CropView(QWidget):
    changed=Signal()
    def __init__(self,image):
        super().__init__();self.image=image;self.side=min(image.width(),image.height())
        self.x=(image.width()-self.side)//2;self.y=(image.height()-self.side)//2
        self.setMinimumSize(360,280);self.setMouseTracking(True)
    def geometry_values(self):
        scale=min(self.width()/self.image.width(),self.height()/self.image.height())
        return scale,(self.width()-self.image.width()*scale)/2,(self.height()-self.image.height()*scale)/2
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#181818'));s,x,y=self.geometry_values()
        p.drawImage(QRect(round(x),round(y),round(self.image.width()*s),round(self.image.height()*s)),self.image)
        p.setPen(QPen(QColor('#00bfff'),2));p.drawRect(QRect(round(x+self.x*s),round(y+self.y*s),round(self.side*s),round(self.side*s)))
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.move_crop(event.position())
    def mouseMoveEvent(self,event):
        if event.buttons()&Qt.MouseButton.LeftButton:self.move_crop(event.position())
    def move_crop(self,pos):
        s,x,y=self.geometry_values();self.x=max(0,min(self.image.width()-self.side,round((pos.x()-x)/s-self.side/2)))
        self.y=max(0,min(self.image.height()-self.side,round((pos.y()-y)/s-self.side/2)));self.update();self.changed.emit()
    def set_side(self,side):
        self.x=max(0,min(self.image.width()-side,self.x+(self.side-side)//2));self.y=max(0,min(self.image.height()-side,self.y+(self.side-side)//2));self.side=side;self.update()
    def cropped(self):
        result=self.image.copy(self.x,self.y,self.side,self.side)
        if self.side<8:result=result.scaled(8,8,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation)
        return result

class CropDialog(QDialog):
    def __init__(self,image,parent):
        super().__init__(parent);self.setWindowTitle('裁剪正方形封面 / Crop square cover');self.resize(520,440)
        box=QVBoxLayout(self);box.addWidget(QLabel('拖动选择裁剪位置，滑块调整正方形大小；小于 8×8 自动放大。\nDrag to position; adjust square size below. Minimum output: 8×8.'))
        self.view=CropView(image);box.addWidget(self.view,1)
        slider=QSlider(Qt.Orientation.Horizontal);slider.setRange(1,min(image.width(),image.height()));slider.setValue(self.view.side);slider.valueChanged.connect(self.view.set_side);box.addWidget(slider)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);box.addWidget(buttons);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject)

class ExportDialog(QDialog):
    def __init__(self,studio):
        super().__init__(studio);self.studio=studio;self.base=defaults(studio.layers);self.cover=self.base['cover']
        self.setWindowTitle(studio.tr('导出材质包','Export resource pack'));self.resize(600,570)
        box=QVBoxLayout(self);self.version=QComboBox();self.version.setPlaceholderText(studio.tr('请选择版本','Choose version'))
        for v in VERSIONS:self.version.addItem(v,v)
        self.version.addItem(studio.tr('保留原始格式（跟随底包）','Preserve original format (follow base pack)'),'unchanged');self.version.setCurrentIndex(-1);box.addWidget(self.version)
        self.filename=QLineEdit(self.base['filename']);self.title=QLineEdit(self.base['title']);self.body=QPlainTextEdit(self.base['body']);self.body.setMaximumHeight(100)
        self.field_labels=[]
        for label,editor in [(studio.tr('文件名 / 游戏显示名称（.zip 固定）','Filename / game pack name (.zip fixed)'),self.filename),(studio.tr('说明标题（首行）','Description title (first line)'),self.title),(studio.tr('正文（后续行）','Description body (following lines)'),self.body)]:
            field_label=QLabel(label);self.field_labels.append(field_label);box.addWidget(field_label);row=QHBoxLayout();row.addWidget(editor,1);button=QPushButton('§');button.setFixedWidth(32);button.setToolTip(studio.tr('插入传统颜色／样式代码','Insert legacy colour / style codes'));button.clicked.connect(lambda checked=False,e=editor,b=button:self.code_menu(e,b));row.addWidget(button);box.addLayout(row)
        self.note=QLabel();self.note.setWordWrap(True);box.addWidget(self.note)
        row=QHBoxLayout();self.cover_label=QLabel();self.cover_label.setFixedSize(80,80);row.addWidget(self.cover_label)
        upload=QPushButton(studio.tr('上传／裁剪封面','Upload / crop cover'));upload.clicked.connect(self.upload_cover);row.addWidget(upload)
        reset=QPushButton(studio.tr('恢复默认封面','Reset cover'));reset.clicked.connect(self.reset_cover);row.addWidget(reset);box.addLayout(row);self.update_cover()
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);box.addWidget(self.buttons)
        self.report_button=self.buttons.addButton(studio.tr('报告与记录','Reports and history'),QDialogButtonBox.ButtonRole.ActionRole)
        from .export_history import show as show_export_history
        self.report_button.clicked.connect(lambda:studio.run(lambda:show_export_history(studio)))
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(studio.tr('导出','Export'))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(studio.tr('取消','Cancel'))
        self.version.currentIndexChanged.connect(self.update_version_text);self.update_version_text()
        self.buttons.accepted.connect(self.save);self.buttons.rejected.connect(self.reject)
    def update_version_text(self,*args):
        version=self.version.currentData();tr=self.studio.tr
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(version in (*VERSIONS,'unchanged'))
        prefix=('Java '+version+' · ') if version in VERSIONS else ''
        self.setWindowTitle(tr('导出材质包','Export resource pack')+(' — Java '+version if version in VERSIONS else ''))
        for label,text in zip(self.field_labels,[tr('包名 / ZIP 文件名（.zip 固定）','Pack name / ZIP filename (.zip fixed)'),tr('描述首行（非包名）','Description first line (not the pack name)'),tr('描述后续行','Remaining description lines')]):label.setText(text)
        if version=='unchanged':
            from .original_export import target_version
            target=target_version(self.studio.layers)
            lead=tr('跟随底包版本：','Base pack version: ')+target+tr('；上层素材按此版本适配。','; adapt upper assets to this version.') if target else tr('底包版本不明：保留素材各自的原格式；独立小素材用其来源版本原版图集补全。','Unknown base version: preserve each source format; complete standalone parts with vanilla atlases from their source version.')
        elif version in VERSIONS:
            fmt=str(FORMATS[version])+('.1' if version=='26.3' else '.0' if FORMATS[version]>=75 else '')
            lead=prefix+tr('资源包格式 ','resource pack format ')+fmt+tr('；转换前逐张复核图集布局。','; each atlas layout is checked before conversion.')
        else:lead=tr('请选择目标版本，或选择不作适配。','Choose a target version or no adaptation.')
        common=tr('游戏包名来自 ZIP 文件名。两处描述合并写入 pack.mcmeta；没有独立的标题字段。§ 按钮插入传统格式代码，& 不自动变色。未编辑描述时保留原文本组件；编辑后使用本窗口的文本（含 § 代码）。封面与描述从启用的底层整包向上查找。','The game pack name comes from the ZIP filename. Both description fields form pack.mcmeta description; there is no separate title field. § inserts legacy formatting; & is literal. Existing text components remain intact unless the description is edited, when this window writes its text (including § codes). Defaults search enabled packs bottom to top.')
        self.note.setText(lead+'\n'+common)
        self.note.setToolTip(tr('较新版本使用 min_format / max_format；其他已支持版本使用 pack_format。游戏可能按可用宽度换行或截断描述。','Recent versions use min_format / max_format; earlier supported versions use pack_format. The game may wrap or clip the description to fit.'))
    def code_menu(self,editor,button):
        menu=QMenu(self)
        for code,color,name in zip('0123456789abcdef',COLORS,COLOR_NAMES):
            pix=QPixmap(12,12);pix.fill(QColor('#'+color))
            from PySide6.QtGui import QIcon
            action=menu.addAction(QIcon(pix),'§'+code+' '+name);action.triggered.connect(lambda checked=False,c=code:self.insert_code(editor,c))
        menu.addSeparator()
        for code,name in [('k','随机 / Obfuscated'),('l','粗体 / Bold'),('m','删除线 / Strike'),('n','下划线 / Underline'),('o','斜体 / Italic'),('r','重置 / Reset')]:
            action=menu.addAction('§'+code+' '+name);action.triggered.connect(lambda checked=False,c=code:self.insert_code(editor,c))
        menu.exec(button.mapToGlobal(QPoint(0,button.height())))
    def insert_code(self,editor,code):
        if isinstance(editor,QLineEdit):editor.insert('§'+code)
        else:editor.insertPlainText('§'+code)
        editor.setFocus()
    def update_cover(self):
        if self.cover:self.cover_label.setPixmap(QPixmap.fromImage(decode(self.cover)).scaled(80,80,Qt.AspectRatioMode.KeepAspectRatio))
        else:self.cover_label.clear();self.cover_label.setText('无封面 / No cover')
    def reset_cover(self):self.cover=self.base['cover'];self.update_cover()
    def upload_cover(self):
        path,_=QFileDialog.getOpenFileName(self,'封面 / Cover','','Images (*.png *.jpg *.jpeg *.bmp *.webp)')
        if not path:return
        try:
            image=decode(Path(path).read_bytes());crop=CropDialog(image,self)
            if crop.exec()==QDialog.DialogCode.Accepted:self.cover=png(crop.view.cropped());self.update_cover()
        except (ValueError,OSError) as error:QMessageBox.warning(self,'封面 / Cover',str(error))
    def save(self):
        try:
            name=zip_name(self.filename.text());version=self.version.currentData()
            if version not in (*VERSIONS,'unchanged'):raise ValueError('请选择版本 / Choose version')
            from .conversion_dialog import review_export_layers
            from .original_export import target_version
            effective=(target_version(self.studio.layers) or 'unchanged') if version=='unchanged' else version
            from .export_targets import resolve,persist
            self.studio.library_store.flush()
            resolved=resolve(self.studio,self.studio.layers,effective)
            if resolved is None:return
            layers,target_notes,pending_targets=resolved
            layers=review_export_layers(self.studio,layers,effective)
            if layers is None:return
            from .export_priority import choose_policy
            fill_policy=choose_policy(self,layers,self.studio.vanilla,effective,self.studio.working_version)
            if fill_policy is None:return
            if fill_policy=='lower':
                layers=review_export_layers(self.studio,layers,effective,include_hidden=True)
                if layers is None:return
            folder=QFileDialog.getExistingDirectory(self,'导出到文件夹 / Export to folder')
            if not folder:return
            path=Path(folder)/name;self.studio.protect_source(path)
            if path.exists() and QMessageBox.question(self,'覆盖 / Overwrite',str(path),QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Yes:return
            report=list(target_notes)
            from .task_progress import run_progress
            title=self.title.text();body=self.body.toPlainText();cover=self.cover
            try:files=run_progress(self,"正在合成导出资源",lambda cancel,progress:prepare_files(layers,self.studio.vanilla,self.studio.working_version,self.base,version,title,body,cover,fill_policy,report_out=report))
            except InterruptedError:return
            from .export_integrity import review
            reference_target=target_version(layers) if version=='unchanged' else version
            if not review(self,files,reference_target,report):return
            run_progress(self,"正在写入资源包",lambda cancel,progress:write_zip(path,files,progress),cancellable=False)
            mapping_errors=persist(self.studio,pending_targets)
            for error in mapping_errors:
                report.append({'path':'','action':'mapping_save_failed','detail':error})
            if pending_targets and not mapping_errors:
                report.append({'path':'','action':'mapping_saved','detail':'用户选择的目标映射已应用到素材库；原文件路径和显示名称保持不变'})
            from .export_history import record
            history_error=None
            try:record(self.studio,path,version,layers,files,report)
            except OSError as error:history_error=str(error)
            omitted=[r for r in report if r['action'] in ('omitted','unresolved')]
            if omitted:
                message=QMessageBox(self);message.setWindowTitle('转换报告 / Conversion report')
                message.setText(f'已导出；{len(omitted)} 项存在兼容性或引用提示，可在导出窗口的“报告与记录”查看。报告未添加到资源包中。')
                message.setDetailedText('\n'.join(r['path']+' — '+r['detail'] for r in omitted));message.exec()
            status='已导出 / Exported: '+str(path)
            if history_error:status+='；历史记录保存失败，本次报告仍可在窗口中查看：'+history_error
            if mapping_errors:status+='；部分素材库目标映射未能保存，详见导出报告。'
            self.studio.statusBar().showMessage(status);self.accept()
        except (ValueError,OSError) as error:QMessageBox.warning(self,'导出未完成 / Export failed',str(error))
