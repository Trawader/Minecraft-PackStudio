"""User-editable display/search copies. Identity never comes from configuration."""
import hashlib,json,os
from pathlib import Path
from functools import lru_cache

def number(code):return 'PE-'+hashlib.sha256(('packstudio:'+code).encode()).hexdigest()[:20]

def config_path():
    from .core import ROOT
    return Path(os.environ.get('PACKSTUDIO_NAMING_FILE',ROOT/'config'/'names-and-search.json'))

@lru_cache(maxsize=1)
def defaults():
    path=Path(__file__).parent/'data/naming_defaults.json'
    return json.loads(path.read_text('utf8')) if path.exists() else {'schema':1,'entries':{}}

def reset_copy():
    path=config_path();path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.writing');temp.write_text(json.dumps(defaults(),ensure_ascii=False,indent=2),'utf8');temp.replace(path)
    reload_copy();return path

def ensure_copy():
    if not config_path().exists():reset_copy()
    return config_path()

@lru_cache(maxsize=1)
def overrides():
    if os.environ.get('PACKSTUDIO_BUILD_NAMES')=='1':return {},0
    try:
        data=json.loads(config_path().read_text('utf-8-sig'))
        if not isinstance(data,dict) or data.get('schema')!=1 or not isinstance(data.get('entries'),dict):return {},1
    except (OSError,ValueError):return {},1
    result={};invalid=0;known=defaults()['entries']
    for code,row in data['entries'].items():
        if code not in known or not isinstance(row,dict) or row.get('number')!=number(code):invalid+=1;continue
        name=row.get('name');tags=row.get('tags',[]);inherit=row.get('include_default_search',True)
        if not isinstance(name,str) or not name.strip() or len(name)>512 or not isinstance(tags,list) or any(not isinstance(t,str) or len(t)>256 for t in tags) or len(tags)>256 or not isinstance(inherit,bool):invalid+=1;continue
        result[code]={'name':name.strip(),'tags':tags,'include_default_search':inherit}
    return result,invalid

def presentation(code,name,search=''):
    row=overrides()[0].get(code)
    if row is None:return name,search
    terms=search if row['include_default_search'] else ''
    return row['name'],(' '.join([row['name'],terms,*row['tags']])).lower()

def reload_copy():
    overrides.cache_clear()
    from . import semantics
    semantics.describe.cache_clear();semantics.parts.cache_clear()
    return overrides()[1]

def install_settings(w):
    from PySide6.QtWidgets import QLabel,QPushButton,QMessageBox
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    from .core import ROOT
    ensure_copy();box=w.settings_dialog.layout()
    label=QLabel(w.tr('玩家命名与搜索配置副本（不改变资源编号）','Player naming/search copy (resource identities are immutable)'));label.setWordWrap(True);box.addWidget(label)
    def button(zh,en,callback):
        b=QPushButton(w.tr(zh,en));b.clicked.connect(lambda:w.run(callback));box.addWidget(b);return b
    def reload():
        invalid=reload_copy();w.refresh();w.statusBar().showMessage(w.tr('已重新加载命名；无效条目回退默认：','Names reloaded; invalid entries using defaults: ')+str(invalid))
    def reset():
        if QMessageBox.question(w,w.tr('重置命名副本','Reset naming copy'),w.tr('将覆盖玩家修改的名称和搜索标签。继续？','Replace custom names and search tags with defaults?'),QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Yes:return
        reset_copy();reload()
    button('打开命名配置副本','Open naming configuration',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(ensure_copy()))))
    button('重新加载命名与搜索规则','Reload naming/search rules',reload)
    w.reset_names_button=button('重置命名配置副本','Reset naming configuration',reset)
    import sys
    document_root=Path(sys._MEIPASS) if getattr(sys,'frozen',False) else ROOT
    button('打开版本／编号／名称对照文档','Open version/identity/name reference',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(document_root/'docs'/'resource-identities.tsv'))))
