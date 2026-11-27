"""Resolve explicitly unmapped imports on export copies; library changes are opt-in."""
import copy
import re
from pathlib import PurePosixPath
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,
    QLineEdit,QCheckBox,QDialogButtonBox,QMessageBox,QHeaderView)
from .core import safe_path


def valid_target(path,original):
    if path!=safe_path(path) or not re.fullmatch(r'assets/[a-z0-9_.-]+/[a-z0-9_./-]+',path):
        raise ValueError('请输入合法资源路径：assets/命名空间/目录/文件名，仅使用小写英文、数字、下划线、点和短横线。')
    if len(path.split('/'))<4 or path.endswith('/') or any(p in ('.','..') for p in path.split('/')):
        raise ValueError('目标路径必须包含资源目录和文件名。')
    if original.lower().endswith('.png') and not path.endswith('.png'):
        raise ValueError('PNG 素材的目标文件名必须以 .png 结尾。')
    if original.lower().endswith('.ogg') and (not path.endswith('.ogg') or path.split('/')[2]!='sounds'):
        raise ValueError('OGG 音效目标必须为 assets/命名空间/sounds/… .ogg。')
    return path


class TargetDialog(QDialog):
    def __init__(self,window,layers,rows):
        super().__init__(window);self.layers=layers;self.rows=[];self.decisions={}
        self.setWindowTitle('导出异常：素材尚未指定目标位置');self.resize(1080,490)
        layout=QVBoxLayout(self)
        label=QLabel('为以下素材指定资源包内目录和文件名，或明确排除。默认仅用于本次导出；“应用到素材库”只保存目标映射，不改名、不移动原文件。')
        label.setWordWrap(True);layout.addWidget(label)
        table=QTableWidget(len(rows),6);table.setHorizontalHeaderLabels(['来源／素材','目标目录','文件名','本次排除','应用到素材库','接受跨项同路径'])
        table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        layout.addWidget(table)
        for index,(layer,path,proposal) in enumerate(rows):
            item=QTableWidgetItem(layer.name+'\n'+path);item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable);table.setItem(index,0,item)
            parent,name=proposal.rsplit('/',1) if proposal and '/' in proposal else ('assets/minecraft/sounds' if path.lower().endswith('.ogg') else 'assets/minecraft/textures',PurePosixPath(path).name)
            if not re.fullmatch(r'[a-z0-9_.-]+',name):name=''
            directory=QLineEdit(parent);filename=QLineEdit(name)
            exclude=QCheckBox();persist=QCheckBox();allow=QCheckBox()
            persist.setEnabled(bool(window.source(layer.library_uid or layer.selection.get('source_uid'))))
            for column,widget in enumerate((directory,filename,exclude,persist,allow),1):table.setCellWidget(index,column,widget)
            table.setRowHeight(index,50);self.rows.append((layer,path,directory,filename,exclude,persist,allow))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('应用本次设置并继续')
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def accept(self):
        try:
            decisions={}
            for layer,path,directory,filename,exclude,persist,allow in self.rows:
                name=filename.text().strip()
                if not exclude.isChecked() and (not name or '/' in name or '\\' in name):
                    raise ValueError('文件名一栏只填写文件名；子目录请填写在目标目录一栏。')
                target=None if exclude.isChecked() else valid_target(directory.text().strip().rstrip('/')+'/'+name,path)
                decisions[(layer.uid,path)]={'target':target,'persist':persist.isChecked() and target is not None,'allow':allow.isChecked()}
            validate_collisions(self.layers,decisions)
            persistent={}
            for layer,path,*_ in self.rows:
                decision=decisions[(layer.uid,path)]
                if decision['persist']:
                    key=(layer.library_uid or layer.selection.get('source_uid'),path)
                    if key in persistent and persistent[key]!=decision['target']:raise ValueError('同一素材被指定了不同的长期目标，请只保留一个“应用到素材库”设置。')
                    persistent[key]=decision['target']
            self.decisions=decisions
        except ValueError as error:
            QMessageBox.warning(self,'目标位置尚未解决',str(error));return
        super().accept()


def targets(layer,decisions):
    saved=layer.selection.get('export_targets',{})
    for path in layer.files:
        decision=decisions.get((layer.uid,path))
        if decision is not None:target=decision['target']
        elif path.lower().endswith('.png.mcmeta') and ((layer.uid,path[:-7]) in decisions or path[:-7] in saved):
            base=decisions.get((layer.uid,path[:-7]),{}).get('target',saved.get(path[:-7]))
            target=base+'.mcmeta' if base else None
        else:target=saved.get(path,path)
        yield path,target


def validate_collisions(layers,decisions):
    occupied={}
    for layer in layers:
        if not layer.enabled:continue
        if layer.kind=='component':
            for path in ([b['path'] for b in layer.bindings] if layer.bindings else [layer.target]):
                occupied.setdefault(path,[]).append((layer.uid,path))
            continue
        own=set()
        for path,target in targets(layer,decisions):
            if target is None:continue
            if target in own:raise ValueError('同一个项目项内存在重复目标：'+target+'。请修改目标或排除其中一项。')
            own.add(target);occupied.setdefault(target,[]).append((layer.uid,path))
    for key,decision in decisions.items():
        if decision['target'] is not None and any(len(occupied.get(target,[]))>1 for target in (decision['target'],decision['target']+'.mcmeta')) and not decision['allow']:
            raise ValueError('目标与其他项目项重合：'+decision['target']+'。如需按合成台优先级覆盖，请勾选“接受跨项同路径”。')


def resolve(window,original,version=None):
    layers=[window.clone_layer(layer) for layer in original];rows=[];decisions={};notes=[];pending=[]
    for layer in layers:
        if not layer.enabled or layer.kind=='component':continue
        owner=window.source(layer.library_uid or layer.selection.get('source_uid'))
        saved=dict(layer.selection.get('export_targets',{}))
        if owner:
            for path,target in owner.selection.get('export_targets',{}).items():
                if path in layer.files:saved.setdefault(path,target)
        layer.selection['export_targets']=saved
        for path in layer.selection.get('unmapped_paths',[]):
            if path not in layer.files:continue
            proposal=saved.get(path,'')
            try:
                if not proposal:raise ValueError('missing')
                valid_target(proposal,path)
            except ValueError:rows.append((layer,path,proposal));continue
            # Persisted mappings still need acknowledgement if this export collides.
            decisions[(layer.uid,path)]={'target':proposal,'persist':False,'allow':False}
    for layer in layers:
        for path,target in layer.selection.get('export_targets',{}).items():
            if layer.enabled and path in layer.files and not any(l.uid==layer.uid and p==path for l,p,_ in rows):
                valid_target(target,path)
                decisions.setdefault((layer.uid,path),{'target':target,'persist':False,'allow':False})
    try:validate_collisions(layers,decisions)
    except ValueError:
        for layer in layers:
            for path,target in layer.selection.get('export_targets',{}).items():
                if (layer.uid,path) in decisions and not any(l.uid==layer.uid and p==path for l,p,_ in rows):rows.append((layer,path,target))
    if rows:
        dialog=TargetDialog(window,layers,rows)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return None
        decisions.update(dialog.decisions)
    validate_collisions(layers,decisions)
    for layer in layers:
        if not layer.enabled or layer.kind=='component':continue
        mapped={};renamed={}
        for path,target in targets(layer,decisions):
            decision=decisions.get((layer.uid,path),{})
            if target is None:
                notes.append({'path':path,'action':'excluded','source':layer.name,'detail':'用户明确排除本次导出'});continue
            mapped[target]=layer.files[path];renamed[path]=target
            if target!=path:notes.append({'path':path,'action':'target_assigned','source':layer.name,'detail':target})
            if decision.get('persist'):pending.append((layer.library_uid or layer.selection.get('source_uid'),path,target))
        layer.files=mapped
        layer.asset_versions={renamed[p]:v for p,v in layer.asset_versions.items() if p in renamed}
        layer.layout_confirmations={renamed[p]:v for p,v in layer.layout_confirmations.items() if p in renamed}
        from .versions import VERSIONS
        if version in VERSIONS:
            for original_path,target in renamed.items():
                if target!=original_path:layer.asset_versions[target]=version
        if not mapped:layer.enabled=False
    if not any(layer.enabled for layer in layers):raise ValueError('本次导出没有剩余的启用素材。')
    return layers,notes,pending


def persist(window,pending):
    changes={};errors=[]
    for uid,path,target in pending:changes.setdefault(uid,{})[path]=target
    for uid,mappings in changes.items():
        owner=window.source(uid)
        if owner is None:errors.append('素材来源已移除，目标映射未保存');continue
        candidate=window.clone_layer(owner)
        valid={p:t for p,t in mappings.items() if p in owner.files}
        if len(valid)!=len(mappings):errors.append(owner.name+'：部分原素材已不存在，对应目标映射未保存')
        if not valid:continue
        candidate.selection.setdefault('export_targets',{}).update(valid)
        try:window.library_store.put(candidate)
        except (OSError,ValueError) as error:errors.append(owner.name+'：'+str(error));continue
        owner.selection=copy.deepcopy(candidate.selection)
    return errors
