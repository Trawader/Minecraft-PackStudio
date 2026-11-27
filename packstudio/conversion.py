"""Whole-pack conversion within library/project copies."""
import copy,json
from dataclasses import replace
from .versions import VERSIONS,FORMATS,source_version

def pack_selection(owner,descriptor):
    if owner is None or owner.kind!='pack' or descriptor.get('kind') not in ('root','folder'):return None
    prefix=descriptor.get('path','').rstrip('/')+'/' if descriptor.get('path') else ''
    raw=owner.files.get(prefix+'pack.mcmeta')
    if raw is None or not any(p.startswith(prefix+'assets/minecraft/') for p in owner.files):return None
    try:
        meta=json.loads(raw)
        if not isinstance(meta,dict) or not isinstance(meta.get('pack'),dict):return None
    except (ValueError,UnicodeError):return None
    files={p[len(prefix):]:v for p,v in owner.files.items() if p.startswith(prefix)}
    layer=replace(owner,files=files,enabled=True,asset_versions={p[len(prefix):]:v for p,v in owner.asset_versions.items() if p.startswith(prefix)},
        layout_confirmations={p[len(prefix):]:copy.deepcopy(v) for p,v in owner.layout_confirmations.items() if p.startswith(prefix)})
    if prefix:layer.source_version='';layer.format_hint=None
    return prefix,layer

def convert_pack(layer,vanilla,target,fallback,report_out=None):
    from .export_dialog import defaults,prepare_files
    from .layouts import confirm_layout,layout_catalog
    if target not in VERSIONS:raise ValueError('Choose a supported target version')
    base=defaults([layer]);active=replace(layer,enabled=True)
    files=prepare_files([active],vanilla,fallback,base,target,base['title'],base['body'],base['cover'],report_out=report_out)
    result=replace(layer,files=files,source_version=target,format_hint=FORMATS[target],asset_versions={},layout_confirmations={})
    for path in files:
        if target in layout_catalog().get(path,{}):confirm_layout(result,path,target)
    return result


def conversion_issues(converted,report):
    from .export_integrity import reference_issues
    return [r for r in report if r.get('action') in ('omitted','unresolved')]+reference_issues(converted.files,converted.source_version)


def review_conversion(window,converted,report):
    issues=conversion_issues(converted,report)
    if not issues:return True
    from PySide6.QtWidgets import QMessageBox
    box=QMessageBox(window);box.setWindowTitle(window.tr('转换结果需要确认','Review conversion result'))
    box.setText(window.tr(f'有 {len(issues)} 项兼容性或引用问题，尚未写入转换结果。',f'{len(issues)} compatibility or reference issues were found. The conversion has not been saved.'))
    box.setInformativeText(window.tr('跳过的资源不会进入转换结果。请查看详情，选择继续或返回修改。','Omitted resources will not be included. Review the details before continuing or going back.'))
    box.setDetailedText('\n'.join(r['path']+' — '+r['detail'] for r in issues))
    proceed=box.addButton(window.tr('使用当前转换结果','Use this conversion'),QMessageBox.ButtonRole.AcceptRole)
    cancel=box.addButton(window.tr('返回修改','Go back'),QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel);box.setEscapeButton(cancel);box.exec()
    if box.clickedButton() is not proceed:return False
    for row in issues:
        if row in report:row['accepted']=True
        else:report.append(dict(row,accepted=True))
    return True

def apply_pack(owner,prefix,converted):
    if not prefix:return replace(converted,uid=owner.uid,name=owner.name,enabled=owner.enabled)
    files={p:v for p,v in owner.files.items() if not p.startswith(prefix)}
    files.update({prefix+p:v for p,v in converted.files.items()})
    versions={p:v for p,v in owner.asset_versions.items() if not p.startswith(prefix)}
    versions.update({prefix+p:converted.source_version for p in converted.files})
    confirmations={p:copy.deepcopy(v) for p,v in owner.layout_confirmations.items() if not p.startswith(prefix)}
    confirmations.update({prefix+p:copy.deepcopy(v) for p,v in converted.layout_confirmations.items()})
    return replace(owner,files=files,asset_versions=versions,layout_confirmations=confirmations)
