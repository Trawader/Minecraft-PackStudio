"""Model-backed material reuse, without inventing variant texture files."""
from functools import lru_cache
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QListWidget,QDialogButtonBox
from .versions import source_version
from .resource_graph import ResourceGraph
from .semantics import identities


@lru_cache(maxsize=4)
def vanilla_files(version):
    from .builtin_assets import paths,get
    return {p:get(version,p) if p.endswith(('.json','.properties','.mcmeta')) else b'' for p in paths(version)}


def supported(path):
    code=identities()[0].get(path,path.split('/textures/')[-1].removesuffix('.png'))
    return code.startswith('block/') and any(word in code for word in ('planks','cobblestone','stone','brick','deepslate','tuff'))


def show(window,descriptor):
    owner=window.source(descriptor['origin'])
    if owner is None:return
    path=descriptor['path'];version=owner.asset_versions.get(path,source_version(owner,window.working_version))
    combined=dict(vanilla_files(version));combined.update(owner.files)
    graph=ResourceGraph(combined).parse();related,_=graph.closure([path])
    variants=sorted(p for p in related if '/models/block/' in p and any(word in p.rsplit('/',1)[-1] for word in ('stairs','slab','fence','wall','button','pressure_plate')))
    dialog=QDialog(window);dialog.setWindowTitle('基础材质与结构变体');dialog.resize(760,510);layout=QVBoxLayout(dialog)
    label=QLabel('以下是实际模型引用链中的结构变体。共用基础贴图的楼梯、台阶、栅栏或墙会随这张材质变化，不需要生成重复 PNG；独立纹理不会按名称强行覆盖。\n来源版本：'+version+'\n基础贴图：'+path)
    label.setWordWrap(True);layout.addWidget(label);listing=QListWidget();layout.addWidget(listing,1)
    for model in variants:listing.addItem(model+(' · 当前材质包' if model in owner.files else ' · 原版回退模型'))
    if not variants:listing.addItem('当前版本与来源未发现已解析的结构变体引用；不会凭名称创建。')
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
    buttons.button(QDialogButtonBox.StandardButton.Ok).setText('将基础材质及来源内关联资源加入项目')
    buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
    if dialog.exec()!=QDialog.DialogCode.Accepted:return
    selected,_=graph.closure([path]+variants)
    window.add_to_composition({**descriptor,'object_paths':sorted(p for p in selected if p in owner.files)})


def add_action(window,menu,descriptor):
    if descriptor.get('kind')!='png' or window.source(descriptor['origin']) is None or not supported(descriptor['path']):return
    action=menu.addAction('查看材质共用变体（楼梯／台阶／栅栏／墙）…')
    stable=dict(descriptor);action.triggered.connect(lambda:window.run(lambda:show(window,stable)))
