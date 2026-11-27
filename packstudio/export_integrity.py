"""Preserve extension reference chains and review actual final output references."""
from functools import lru_cache
import struct
from .resource_graph import ResourceGraph
from .versions import VERSIONS,records


@lru_cache(maxsize=1)
def known_paths():
    return frozenset(path for version in VERSIONS for path in records(version))


def is_model_config(path):
    return path.startswith('assets/') and path.endswith('.json') and any(
        part in path.split('/')[2:-1] for part in ('models','blockstates','items'))


def model_dependencies(files):
    """Keep supplied model definitions and their reference chain together."""
    roots={path for path in files if is_model_config(path)}
    if not roots:return set()
    selected,_=ResourceGraph(files).parse().closure(roots,include_callers=True)
    return selected


def protected_paths(layers):
    # Use the winning configuration, so hidden lower configurations cannot invent links.
    files={}
    for layer in reversed(layers):
        if layer.enabled and layer.kind!='component':files.update(layer.files)
    known=known_paths();roots=set()
    for path in files:
        if not path.startswith('assets/'):continue
        if (is_model_config(path) or not path.startswith('assets/minecraft/')
            or any(part in path.split('/') for part in ('optifine','mcpatcher','overrides'))
            or path.endswith('.properties')
            or path.endswith('.json') and path not in known):roots.add(path)
    graph=ResourceGraph(files).parse()
    roots.update(row['path'] for row in graph.issues if row['path'].startswith('assets/'))
    selected,_=graph.closure(roots,include_callers=True)
    return selected


def reference_issues(files,target):
    graph=ResourceGraph(files).parse();issues=[]
    available=records(target) if target in VERSIONS else {}
    for row in graph.issues:
        issues.append({'path':row['path'],'action':'reference_unverified','detail':row['reason']})
    from .texture_animation import timeline
    for path,raw in files.items():
        if not path.lower().endswith('.png.mcmeta'):continue
        texture=files.get(path[:-7])
        if texture is None:
            issues.append({'path':path,'action':'animation_unverified','detail':'最终文件中没有配套 PNG；动画配置与原版回退纹理是否匹配尚未确认。'})
            continue
        try:
            if len(texture)<24 or not texture.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('配套文件不是可识别的 PNG')
            timeline(raw,*struct.unpack('>II',texture[16:24]))
        except (ValueError,UnicodeError) as error:
            issues.append({'path':path,'action':'animation_unverified','detail':'动画配置无法确认：'+str(error)+'；原文件保留。'})
    seen=set()
    for row in graph.evidence:
        dependency=row['target'];key=(row['source'],dependency)
        if key in seen or dependency in files or dependency in available:continue
        seen.add(key)
        detail='最终文件中未找到引用目标：'+dependency+'（'+row['reason']+'）'
        detail+='；目标版本原版目录中也未找到。' if target in VERSIONS else '；保持原样模式未确定单一版本，原版回退尚未核实。'
        issues.append({'path':row['source'],'action':'reference_unverified','detail':detail})
    from .sounds import reference_issues as sound_issues
    issues.extend(sound_issues(files))
    return issues


def review(window,files,target,report):
    issues=reference_issues(files,target)
    if not issues:return True
    from PySide6.QtWidgets import QMessageBox
    dialog=QMessageBox(window);dialog.setWindowTitle('导出引用需要确认')
    dialog.setIcon(QMessageBox.Icon.Warning)
    dialog.setText(f'最终合成结果有 {len(issues)} 项引用或配置尚未确认。')
    dialog.setInformativeText('可返回修改，或保留当前文件继续导出。此检查仅覆盖已支持的引用语法，不代表扩展资源在目标游戏中兼容。')
    dialog.setDetailedText('\n'.join(row['path']+' — '+row['detail'] for row in issues))
    proceed=dialog.addButton('保留当前文件并继续导出',QMessageBox.ButtonRole.AcceptRole)
    cancel=dialog.addButton('返回修改',QMessageBox.ButtonRole.RejectRole)
    dialog.setDefaultButton(cancel);dialog.setEscapeButton(cancel);dialog.exec()
    if dialog.clickedButton() is not proceed:return False
    report.extend(dict(row,accepted=True) for row in issues)
    return True
