"""Application-local export reports; never inserted into resource packs."""
from datetime import datetime
import json
import uuid
from PySide6.QtWidgets import QDialog,QVBoxLayout,QComboBox,QPlainTextEdit,QDialogButtonBox
from .core import ROOT

HISTORY=ROOT/'.tmp'/'export-history'


def record(window,path,version,layers,files,notes):
    entry={'created':datetime.now().astimezone().isoformat(timespec='seconds'),
           'output':str(path),'version':version,'file_count':len(files),
           'sources':[{'name':layer.name,'uid':layer.uid,'source':layer.source,
                       'selection':layer.selection} for layer in layers if layer.enabled],
           'events':notes}
    window.last_export_report=entry
    HISTORY.mkdir(parents=True,exist_ok=True)
    target=HISTORY/(datetime.now().strftime('%Y%m%d-%H%M%S-')+uuid.uuid4().hex+'.json')
    temporary=target.with_suffix('.writing')
    temporary.write_text(json.dumps(entry,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(target)
    return entry


def show(window):
    entries=[]
    latest=getattr(window,'last_export_report',None)
    if latest:entries.append(latest)
    if HISTORY.exists():
        for path in sorted(HISTORY.glob('*.json'),reverse=True)[:50]:
            try:entry=json.loads(path.read_text('utf-8'))
            except (OSError,ValueError):continue
            if isinstance(entry,dict) and entry!=latest:entries.append(entry)
    dialog=QDialog(window);dialog.setWindowTitle('导出报告与记录');dialog.resize(850,600)
    layout=QVBoxLayout(dialog);choices=QComboBox();content=QPlainTextEdit();content.setReadOnly(True)
    layout.addWidget(choices);layout.addWidget(content)
    for entry in entries:choices.addItem(entry.get('created','')+' · '+entry.get('output',''))
    def select(index):
        if 0<=index<len(entries):content.setPlainText(json.dumps(entries[index],ensure_ascii=False,indent=2))
    choices.currentIndexChanged.connect(select)
    if entries:select(0)
    else:content.setPlainText('还没有导出记录。')
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
    dialog.exec()


def composition_notes(layers):
    notes=[];winners={}
    for layer in layers:
        if not layer.enabled:
            notes.append({'path':'','action':'disabled','source':layer.name,'detail':'项目项未启用，本次不参与导出'})
            continue
        if layer.kind=='component':
            notes.append({'path':layer.target,'action':'component','source':layer.name,
                          'detail':'按合成台顺序参与区域覆盖','regions':layer.regions,'bindings':layer.bindings})
            continue
        for path in layer.files:
            if path in ('pack.mcmeta','pack.png'):
                notes.append({'path':path,'action':'metadata_candidate','source':layer.name,
                              'detail':'封面和描述候选；使用导出窗口的最终设置'})
                continue
            if path in winners:
                notes.append({'path':path,'action':'input_overlap','source':layer.name,
                              'detail':'输入同路径的上方项目项：'+winners[path]+'；最终结果同时受版本转换和组件覆盖影响'})
            else:winners[path]=layer.name
        for path in layer.selection.get('missing',[]):
            notes.append({'path':path,'action':'unresolved','source':layer.name,'detail':'选择资源组时未找到此引用；需要检查资源完整性'})
    return notes
