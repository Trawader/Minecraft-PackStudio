"""Review atlas layouts before either internal conversion or adapted export."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QTableWidget,QTableWidgetItem,
    QDialogButtonBox,QHeaderView,QAbstractItemView,QCheckBox)
from .core import decode
from .versions import VERSIONS
from .layouts import inspect_atlases,confirm_layout,layout_catalog

def review_export_layers(studio,layers,target,include_hidden=False):
    import copy
    from dataclasses import replace
    if target=='unchanged':return layers
    from .export_priority import visible_files
    copies=[replace(l,files=dict(l.files),asset_versions=dict(l.asset_versions),layout_confirmations=copy.deepcopy(l.layout_confirmations)) for l in layers]
    checked=copies if include_hidden else visible_files(copies)
    pending=any(not row['chosen'] for layer in checked if layer.enabled and layer.kind!='component' for row in inspect_atlases(layer,studio.working_version))
    if pending:
        dialog=ConversionDialog(studio,checked,target=target,review_only=True)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return None
    return copies

class ConversionDialog(QDialog):
    def __init__(self,studio,layers,target=None,project=False,review_only=False):
        super().__init__(studio);self.studio=studio;self.layers=layers;self.review_only=review_only
        self.setWindowTitle(studio.tr('图集布局复核' if review_only else '跨版本处理','Review atlas layouts' if review_only else 'Convert resource pack'))
        self.resize(850,640);box=QVBoxLayout(self)
        self.version=QComboBox();self.version.setPlaceholderText(studio.tr('选择目标版本','Choose target version'))
        for v in VERSIONS:self.version.addItem(v,v)
        self.version.setCurrentIndex(self.version.findData(target) if target else -1);self.version.setEnabled(not review_only);box.addWidget(self.version)
        note=QLabel(studio.tr('逐张识别图集，不沿用整包版本。无法唯一识别时，请对照下方原版图确认布局；取消不会更改素材。','Atlases are checked independently of the pack version. Compare the reference below to resolve uncertain layouts. Cancel leaves assets untouched.'));note.setWordWrap(True);box.addWidget(note)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels([studio.tr('素材','Asset'),studio.tr('识别依据 / 整包版本','Evidence / pack version'),studio.tr('采用的布局','Use layout')])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch);self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(2,210);box.addWidget(self.table,1);self.rows=[]
        for layer in layers:
            if not layer.enabled:continue
            for row in inspect_atlases(layer,studio.working_version):
                index=self.table.rowCount();self.table.insertRow(index)
                self.table.setItem(index,0,QTableWidgetItem(layer.name+'\n'+row['path'].split('/textures/')[-1]))
                self.table.item(index,0).setToolTip(row['path'])
                self.table.setItem(index,1,QTableWidgetItem(row['reason']+'\n'+row['pack_version']))
                combo=QComboBox();combo.setPlaceholderText(studio.tr('请选择此图布局','Choose this image layout'))
                choice=-1
                for group in row['candidates']:
                    versions=group['versions'];label=' / '.join(versions) if len(versions)<3 else versions[0]+' – '+versions[-1]
                    combo.addItem(label,group['version'])
                    if row['chosen'] in versions:choice=combo.count()-1
                combo.setCurrentIndex(choice);self.table.setCellWidget(index,2,combo);self.table.setRowHeight(index,56)
                self.rows.append((layer,row,combo));combo.currentIndexChanged.connect(self.update_ready)
        self.preview=QLabel();self.reference=QLabel()
        for label in (self.preview,self.reference):label.setFixedHeight(190);label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        images=QHBoxLayout();images.addWidget(self.preview);images.addWidget(self.reference);box.addLayout(images)
        labels=QHBoxLayout();labels.addWidget(QLabel(studio.tr('当前图片','Current image')));labels.addWidget(QLabel(studio.tr('所选布局的原版参照','Vanilla reference for selected layout')));box.addLayout(labels)
        self.keep_original=QCheckBox(studio.tr('保留原项，生成转换副本','Keep original and create a converted copy'))
        self.keep_original.setChecked(not project);self.keep_original.setVisible(not review_only);box.addWidget(self.keep_original)
        scope=QLabel(studio.tr('本次布局确认仅用于导出，不修改素材库和项目。','These layout choices apply only to this export; library and project assets stay unchanged.') if review_only else studio.tr('项目处理仅修改所选副本；素材库处理不会修改已有副本，也不会写回磁盘原 ZIP。','Project conversion affects only this copy. Library conversion leaves existing copies and the original ZIP unchanged.'));scope.setWordWrap(True);box.addWidget(scope)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(studio.tr('继续导出' if review_only else '开始处理','Continue export' if review_only else 'Convert'))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(studio.tr('取消','Cancel'))
        box.addWidget(self.buttons);self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject)
        self.version.currentIndexChanged.connect(self.update_ready);self.table.currentCellChanged.connect(self.show_preview)
        if self.rows:self.table.selectRow(0)
        else:self.preview.setText(studio.tr('没有需要复核的大图','No atlases need review'))
        self.update_ready()
    def update_ready(self,*args):
        if not hasattr(self,'buttons'):return
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.version.currentData() in VERSIONS and all(combo.currentData() for _,_,combo in self.rows))
        self.show_preview()
    def show_preview(self,*args):
        index=self.table.currentRow()
        if index<0 or index>=len(self.rows):return
        layer,row,combo=self.rows[index]
        for label,data in ((self.preview,layer.files[row['path']]),(self.reference,self.studio.vanilla.get(combo.currentData(),row['path']) if combo.currentData() else None)):
            label.clear()
            if data:label.setPixmap(QPixmap.fromImage(decode(data)).scaled(340,185,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation))
    def accept(self):
        if not self.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled():return
        for layer,row,combo in self.rows:confirm_layout(layer,row['path'],combo.currentData())
        super().accept()
