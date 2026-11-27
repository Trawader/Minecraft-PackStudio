"""Offscreen regression for whole-pack commands and mixed-version atlas recognition."""
import os,sys,json,uuid,copy
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication,QDialogButtonBox
from PySide6.QtGui import QColor
from packstudio.core import ROOT,Layer,Vanilla,decode,png,save_project,load_project
from packstudio.layouts import inspect_atlases,checked_layouts,confirm_layout,LayoutReviewRequired,layout_catalog
from packstudio.conversion import pack_selection,convert_pack,apply_pack
from packstudio.conversion_dialog import ConversionDialog
from packstudio.export_dialog import ExportDialog,prepare_files,defaults
from packstudio.studio import StudioWindow

app=QApplication([]);root=ROOT/'.tmp'/('pack-conversion-'+uuid.uuid4().hex);root.mkdir()
os.environ['PACKSTUDIO_SETTINGS_FILE']=str(root/'settings.ini')
w=StudioWindow(root/'library',drafts=False);v=w.vanilla
icons='assets/minecraft/textures/gui/icons.png'
metadata={'pack':{'pack_format':3,'description':{'text':'Colour','color':'gold','extra':[{'text':'\nSecond line'}]}}}
im=decode(v.get('1.8.9',icons))
# Recolour a visible XP pixel; exact bytes differ, but layout alpha is unchanged.
xy=next((x,y) for y in range(64,69) for x in range(182) if im.pixelColor(x,y).alpha())
colour=QColor('#ef1234');colour.setAlpha(im.pixelColor(*xy).alpha());im.setPixelColor(*xy,colour)
source=Layer('Mixed 1.12 pack',{'pack.mcmeta':json.dumps(metadata).encode(),icons:png(im)},source_version='1.12.2')
w.add_import(source);root_d={'origin':source.uid,'path':'','kind':'root','name':source.name}
checks=inspect_atlases(source);assert checks[0]['chosen'] in ('1.7.10','1.8.9') and source.layout_confirmations[icons]['stable'],checks
assert pack_selection(source,root_d)
folder={**root_d,'kind':'folder','path':'assets/minecraft/textures/gui'}
assert pack_selection(source,folder) is None
png_d={**root_d,'kind':'png','path':icons}
for d,expected in ((root_d,True),(folder,False),(png_d,False)):
    menu=w.resource_menu(d);assert any(a.objectName()=='convertWholePack' for a in menu.actions())==expected;menu.deleteLater()
working=pack_selection(source,root_d)[1]
dialog=ConversionDialog(w,[working]);dialog.version.setCurrentIndex(dialog.version.findData('1.16.5'))
assert dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
before=copy.deepcopy(source.files);dialog.reject();assert source.files==before
converted=convert_pack(working,v,'1.16.5','1.8.9')
output=decode(converted.files[icons]);target=decode(v.get('1.16.5',icons))
assert output.pixelColor(*xy)==colour
# Newly required attack indicator must come from the target, not an empty 1.8 rectangle.
assert output.copy(0,94,84,18)==target.copy(0,94,84,18)
assert json.loads(converted.files['pack.mcmeta'])['pack']['description']==metadata['pack']['description']
assert source.files==before
w.add_to_composition(root_d);shadow=w.layers[0];stage={'origin':'stage:'+shadow.uid,'path':'','kind':'root','name':shadow.name}
assert any(a.objectName()=='convertWholePack' for a in w.resource_menu(stage).actions())
w.commit_pack_conversion(stage,converted,keep_original=False)
assert shadow.source_version=='1.16.5' and source.files==before and w.library_store.load()[0].files==before
w.undo_resource();shadow=w.layers[0];assert shadow.files==before
w.commit_pack_conversion(root_d,converted,keep_original=True)
assert len(w.sources)==2 and w.sources[0].files==before and w.layers[0].files==before
created=w.sources[-1];assert created.source_version=='1.16.5'
# Replacement in the library must leave existing project shadows untouched.
w.commit_pack_conversion(root_d,converted,keep_original=False)
assert source.source_version=='1.16.5' and w.layers[0].files==before
assert any(l.uid==source.uid and l.source_version=='1.16.5' for l in w.library_store.load())
# Unknown custom shapes require explicit review, independent of the enclosing version.
unknown_image=decode(v.get('1.8.9',icons));unknown_image.fill(QColor('magenta'))
unknown=Layer('Unknown',{'pack.mcmeta':json.dumps(metadata).encode(),icons:png(unknown_image)},source_version='1.12.2')
assert inspect_atlases(unknown)[0]['chosen'] is None
try:checked_layouts(unknown,'1.8.9');raise AssertionError('No review requested')
except LayoutReviewRequired:pass
dialog=ConversionDialog(w,[unknown],target='1.16.5',review_only=True)
assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
dialog.rows[0][2].setCurrentIndex(0);dialog.accept();assert checked_layouts(unknown,'1.8.9')[0][icons] in ('1.7.10','1.8.9')
unknown_image.setPixelColor(0,0,QColor('black'));unknown.files[icons]=png(unknown_image)
assert inspect_atlases(unknown)[0]['chosen'] in ('1.7.10','1.8.9'),'Painting must retain the explicitly labelled layout version'
# A nested folder qualifies only when it is itself a whole pack; siblings survive conversion.
nested=Layer('Container',{'outside.txt':b'keep',**{'inner/'+p:data for p,data in before.items()}})
nd={'origin':nested.uid,'path':'inner','kind':'folder','name':'inner'}
prefix,part=pack_selection(nested,nd);assert prefix=='inner/'
result=apply_pack(nested,prefix,convert_pack(part,v,'1.16.5','1.8.9'))
assert result.files['outside.txt']==b'keep' and 'inner/pack.mcmeta' in result.files
# UI follows target changes, including JSON description preservation and newer metadata.
w.layers=[created];export=ExportDialog(w)
export.version.setCurrentIndex(export.version.findData('26.3'))
assert '26.3' in export.note.text() and '97.1' in export.note.text() and '1.7 / 1.8' not in export.note.text()
assert '26.3' in export.windowTitle() and '非包名' in export.field_labels[1].text()
export.show();app.processEvents();export.grab().save(str(ROOT/'.tmp/export-26.3.png'));export.hide()
export.version.setCurrentIndex(export.version.findData('unchanged'));assert '跟随底包版本：' in export.note.text() and '上层素材按此版本适配' in export.note.text()
save_project(root/'test.packstudio',[created],'1.8.9');loaded,_=load_project(root/'test.packstudio')
assert loaded[0].layout_confirmations==created.layout_confirmations
w.dirty=False;w.close()
print('PASS: whole-pack-only menus, mixed 1.8 icons inside 1.12 pack, missing target slots, ambiguity/cancel, shadow isolation, nested pack, persistence and version-aware export text')
