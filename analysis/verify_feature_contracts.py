import os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen';sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QColor,QRegion
from packstudio.core import Layer,png,decode
from packstudio.studio import StudioWindow
from packstudio.capabilities import replacement,smart_reason,frame_reason,TOOLS
app=QApplication([])
with tempfile.TemporaryDirectory() as temp:
 os.environ['PACKSTUDIO_SETTINGS_FILE']=str(Path(temp)/'s.ini');w=StudioWindow(Path(temp)/'lib',drafts=False)
 try:
  a='assets/minecraft/textures/items/a.png';b=a.replace('a.png','b.png');audio='assets/minecraft/sounds/test.ogg'
  im=QImage(16,16,QImage.Format.Format_ARGB32);im.fill(QColor('cyan'));other=QImage(im);other.fill(QColor('red'))
  source=Layer('source',{a:png(im),b:png(other),audio:b'OggSbefore'});w.sources=[source];w.refresh()
  d={'origin':source.uid,'kind':'png','path':a,'name':'a'};sd=dict(d,path=b,name='b')
  assert not replacement(w,d)[0];w.select_asset(sd);assert replacement(w,d)[0]
  original=dict(source.files);w.replace_with_selected(d);assert decode(source.files[a])==other
  w.undo_resource();assert source.files==original
  w.replace_with_selected(d);source.files[a]=png(im)
  try:w.undo_resource();raise AssertionError('conflict overwritten')
  except ValueError:pass
  source.files[a]=png(other);w.undo_resource();assert source.files==original
  history=list(w.resource_history)
  with patch.object(w.library_store,'put',side_effect=OSError('disk failure')):
   try:w.replace_with_selected(d);raise AssertionError('failed save accepted')
   except OSError:pass
  assert source.files==original and w.resource_history==history
  from packstudio.audio_preview import AudioPreview
  w.audio_preview=AudioPreview(w);w.audio_preview.descriptor={'origin':source.uid,'kind':'file','path':audio,'name':'sound'}
  with patch.object(w.audio_preview,'open'):
   w.audio_preview.replace_bytes(b'OggSafter')
  assert source.files[audio]==b'OggSafter';w.undo_resource();assert source.files[audio]==b'OggSbefore'
  w.select_asset({'origin':source.uid,'kind':'file','path':audio,'name':'sound'})
  assert not replacement(w,d)[0] and replacement(w,w.audio_preview.descriptor)[0]
  w.select_asset(sd);assert not replacement(w,w.audio_preview.descriptor)[0]
  frame=dict(d,kind='component',regions=[(0,0,1,.5)])
  assert not replacement(w,frame,frame=True)[0]
  small=im.copy(0,0,16,8);w.selected_asset={'kind':'png','files':{'frame.png':png(small)}}
  assert replacement(w,frame,frame=True)[0]
  component=dict(d,kind='component',regions=[(0,0,1,.5)])
  before_component=dict(source.files);w.replace_with_selected(component);w.undo_resource();assert source.files==before_component
  bindings=dict(d,bindings=[{'path':a,'region':(0,0,1,1)},{'path':b,'region':(0,0,1,1)}])
  w.selected_asset={'kind':'pack','files':{'unrelated1.png':png(im),'unrelated2.png':png(im)}}
  assert not replacement(w,bindings)[0]
  w.selected_asset={'kind':'pack','files':{a:png(im),b:png(im)}};assert replacement(w,bindings)[0]
  w.add_to_composition(d);layer=w.layers[0];after=dict(layer.files)
  layer.files[a]=png(other);w.changed()
  try:w.undo_resource();raise AssertionError('later project edit overwritten')
  except ValueError:pass
  layer.files=after;w.undo_resource();assert not w.layers
  w.edit_descriptor(d);w.resource_editors.open_editor(d);dock,e=w.resource_editors.editors[(source.uid,a)]
  assert set(w.tool_buttons)==set(e.tool_buttons)
  for key,_ in TOOLS:assert key in e.tool_buttons
  assert type(e.recolor_panel) is type(w.recolor_panel) and type(e.animation_editor) is type(w.animation_editor)
  for tool in ('magic_eraser','dodge','darken','wand','select','mouse'):
   e.set_tool(tool);assert e.canvas.tool==tool
  e.recolor_panel.mode.setCurrentIndex(e.recolor_panel.mode.findData('adjust'));e.recolor_panel.controls['brightness'][1].setValue(-20)
  e.recolor_panel.preview();e.recolor_panel.apply();assert decode(source.files[a])!=im and w.canvas.image==e.canvas.image
  e.canvas.undo();assert decode(source.files[a])==im and w.canvas.image==im
  # A stale independent surface cannot overwrite bytes changed externally.
  source.files[a]=png(other)
  with patch.object(w,'run',side_effect=lambda fn:fn()):
   try:e.commit();raise AssertionError('stale editor wrote')
   except ValueError:pass
  assert source.files[a]==png(other) and e.canvas.image==other
  large=QImage(513,512,QImage.Format.Format_ARGB32);large.fill(QColor('blue'));e.canvas.set_image(large);e.sync_controls()
  assert smart_reason(e.canvas) and not e.tool_buttons['smart'].isEnabled()
  assert not e.recolor_panel.prepare_button.isEnabled() and e.recolor_panel.prepare_button.toolTip()
  assert not e.recolor_panel.scope.model().item(2).isEnabled()
  dock.close()
  print('PASS library PNG/audio replacement undo, save rollback, history conflict protection, type/frame capability parity, project conflict, shared detached controls, synchronized commits, stale-editor protection, preflight limits')
 finally:w.dirty=False;w.close();app.processEvents()
