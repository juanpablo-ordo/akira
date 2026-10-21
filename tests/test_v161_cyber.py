"""One-click voice recovery, asynchronous setup and consistent app identity."""
import hashlib,io,json,os,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
import voice_session as voice
import windows_identity as identity
from cyber_ui import brand_status,public_status
from build_windows import build_command

def row(key='es_ES-one-medium',speaker=0):
 model=key+'.onnx';config=model+'.json';files=['es/'+model,'es/'+config]
 data={files[0]:b'model-'+key.encode(),files[1]:b'{"audio":{"sample_rate":22050}}'}
 return {'id':'piper:'+key+':'+str(speaker),'name':key+' speaker '+str(speaker),'engine':'piper',
  'model':model,'installed':False,'files':files,'speaker':speaker,
  'file_metadata':{name:{'size_bytes':len(raw),'md5_digest':hashlib.md5(raw).hexdigest()} for name,raw in data.items()}},data

class AllVoicesTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
 def opener(self,data):
  def open_(url,timeout,**kwargs):return io.BytesIO(data[url.removeprefix(voice.PIPER_ROOT)])
  return open_
 def test_one_click_installs_every_model_in_catalog(self):
  first,a=row();second,b=row('en_US-two-high');events=[]
  with patch.object(voice,'voice_inventory',return_value=[first,second]),patch('urllib.request.urlopen',side_effect=self.opener({**a,**b})):
   job=voice.VoiceDownloadBatch(self.root,events.append);self.assertTrue(job.start());self.assertFalse(job.start());job.thread.join(4)
  self.assertFalse(job.active);self.assertEqual(events[-1]['state'],'complete');self.assertTrue(events[-1]['finished'])
  self.assertEqual(events[-1]['downloaded'],2);self.assertTrue(voice.voice_pair_valid(self.root,first));self.assertTrue(voice.voice_pair_valid(self.root,second))
  self.assertTrue(any(e.get('file_bytes',0)>0 for e in events))
 def test_multiple_speakers_share_one_download(self):
  first,data=row();second,_=row(speaker=7);events=[]
  with patch('urllib.request.urlopen',side_effect=self.opener(data)) as request:
   result=voice.install_all_voices(self.root,[first,second],events.append)
  self.assertEqual(request.call_count,2);self.assertEqual(result['models_total'],1);self.assertEqual(result['voices_total'],2)
 def test_repeated_download_skips_verified_installed_pairs(self):
  item,data=row()
  with patch('urllib.request.urlopen',side_effect=self.opener(data)):voice.install_all_voices(self.root,[item])
  with patch('urllib.request.urlopen',side_effect=AssertionError('Downloaded a complete installed voice')):
   result=voice.install_all_voices(self.root,[item])
  self.assertEqual(result['skipped'],1);self.assertEqual(result['downloaded'],0);self.assertEqual(result['state'],'complete')
 def test_corrupted_same_size_model_is_repaired(self):
  item,data=row()
  with patch('urllib.request.urlopen',side_effect=self.opener(data)):voice.install_all_voices(self.root,[item])
  path=self.root/'state/voices'/Path(item['files'][0]).name;path.write_bytes(b'x'*path.stat().st_size)
  self.assertFalse(voice.voice_pair_valid(self.root,item))
  with patch('urllib.request.urlopen',side_effect=self.opener(data)):result=voice.install_all_voices(self.root,[item])
  self.assertEqual(result['downloaded'],1);self.assertTrue(voice.voice_pair_valid(self.root,item))
 def test_failure_continues_and_retry_only_downloads_missing_pair(self):
  first,a=row();second,b=row('en_US-two-high');data={**a,**b}
  def fail_one(url,timeout,**kwargs):
   if url.endswith(Path(first['files'][0]).name):raise OSError('Network interrupted')
   return self.opener(data)(url,timeout)
  with patch('urllib.request.urlopen',side_effect=fail_one):result=voice.install_all_voices(self.root,[first,second])
  self.assertEqual(result['state'],'partial');self.assertEqual(result['downloaded'],1);self.assertEqual(result['failed'],1)
  with patch('urllib.request.urlopen',side_effect=self.opener(data)) as request:retry=voice.install_all_voices(self.root,[first,second])
  self.assertEqual(retry['skipped'],1);self.assertEqual(retry['downloaded'],1);self.assertEqual(request.call_count,2)
 def test_cancel_before_download_never_opens_network(self):
  item,data=row();cancel=threading.Event();cancel.set()
  with patch('urllib.request.urlopen',side_effect=AssertionError('Cancelled download opened network')):
   result=voice.install_all_voices(self.root,[item],cancel=cancel)
  self.assertEqual(result['state'],'cancelled');self.assertEqual(result['models_done'],0)
 def test_cancel_mid_pair_preserves_previous_complete_installation(self):
  item,data=row();folder=self.root/'state/voices';folder.mkdir(parents=True)
  model=folder/Path(item['files'][0]).name;config=folder/Path(item['files'][1]).name
  model.write_bytes(b'previous');config.write_bytes(b'{}');cancel=threading.Event()
  def progress(filename,done,total):cancel.set()
  with patch('urllib.request.urlopen',side_effect=self.opener(data)):
   with self.assertRaisesRegex(RuntimeError,'cancelada'):voice.install_voice(self.root,item,cancel=cancel,byte_progress=progress)
  self.assertEqual(model.read_bytes(),b'previous');self.assertEqual(config.read_bytes(),b'{}');self.assertFalse(list(folder.glob('install_*')))
 def test_incomplete_or_checksum_invalid_pair_is_never_marked_available(self):
  item,data=row();bad={**data,item['files'][0]:b'x'*len(data[item['files'][0]])}
  with patch('urllib.request.urlopen',side_effect=self.opener(bad)):result=voice.install_all_voices(self.root,[item])
  self.assertEqual(result['failed'],1);self.assertFalse(voice.voice_pair_valid(self.root,item))
  self.assertFalse(list((self.root/'state/voices').glob('*.onnx')))
 def test_disk_full_stops_with_retryable_status(self):
  item,data=row()
  with patch.object(voice.shutil,'disk_usage',return_value=NS(free=1)),patch('urllib.request.urlopen',side_effect=AssertionError('Insufficient disk space')):
   result=voice.install_all_voices(self.root,[item])
  self.assertEqual(result['state'],'disk_full');self.assertEqual(result['models_done'],0)
 def test_offline_catalog_can_use_previously_saved_inventory(self):
  item,data=row();events=[]
  with patch.object(voice,'voice_inventory',side_effect=[OSError('Offline catalog'),[item]]),patch('urllib.request.urlopen',side_effect=self.opener(data)):
   job=voice.VoiceDownloadBatch(self.root,events.append);job.start();job.thread.join(4)
  self.assertEqual(events[-1]['state'],'complete')
 def test_no_catalog_has_clear_finished_error(self):
  events=[]
  with patch.object(voice,'voice_inventory',side_effect=[OSError('offline'),[]]):
   job=voice.VoiceDownloadBatch(self.root,events.append);job.start();job.thread.join(4)
  self.assertTrue(events[-1]['finished']);self.assertEqual(events[-1]['state'],'error');self.assertFalse(job.active)
 def test_application_stop_cancels_batch(self):
  item,data=row();events=[];stop=threading.Event();stop.set()
  with patch.object(voice,'voice_inventory',return_value=[item]),patch('urllib.request.urlopen',side_effect=AssertionError('Shutdown')):
   job=voice.VoiceDownloadBatch(self.root,events.append,stop);job.start();job.thread.join(4)
  self.assertEqual(events[-1]['state'],'cancelled')
 def test_incomplete_files_are_not_advertised_as_available(self):
  item,data=row();folder=self.root/'state/voices';folder.mkdir(parents=True)
  for filename,raw in data.items():(folder/Path(filename).name).write_bytes(raw)
  self.assertTrue(voice.voice_files_available(folder,item['files'],item['file_metadata']))
  (folder/Path(item['files'][0]).name).write_bytes(b'incomplete')
  self.assertFalse(voice.voice_files_available(folder,item['files'],item['file_metadata']))
 def test_invalid_configuration_is_not_advertised_as_available(self):
  item,data=row();folder=self.root/'state/voices';folder.mkdir(parents=True)
  for filename,raw in data.items():(folder/Path(filename).name).write_bytes(raw)
  (folder/Path(item['files'][1]).name).write_bytes(b'not json')
  self.assertFalse(voice.voice_files_available(folder,item['files'],{}))

class IdentityTests(unittest.TestCase):
 def test_backend_name_never_appears_in_ready_or_error_badge(self):
  for status in ({'ready':True,'selected_model':'qwen3:14b'},{'ready':False,'error':'qwen3:14b unavailable'},{'mode':'LOCAL_PRIMARY'}):
   text=brand_status(status);self.assertIn('AKIRA',text);self.assertNotIn('qwen',text.lower());self.assertNotIn('LOCAL_PRIMARY',text)
 def test_progress_and_source_names_hide_backend_identifiers(self):
  text=public_status('Síntesis qwen3:14b · visión gemma3:4b · Ollama')
  self.assertNotIn('qwen',text.lower());self.assertNotIn('gemma',text.lower());self.assertNotIn('ollama',text.lower())
 def test_bundled_icon_is_found_when_runtime_folder_has_no_assets(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'assets').mkdir();(root/'assets/akira.ico').write_bytes(b'icon')
   with patch.object(identity.sys,'_MEIPASS',str(root),create=True):
    self.assertEqual(identity.asset_path('akira.ico',root/'mutable'),root/'assets/akira.ico')
 def test_default_icon_is_set_for_future_dialogs(self):
  window=Mock()
  with patch.object(identity,'os',NS(name='nt')):
   self.assertTrue(identity.apply_window_icon(window))
  self.assertIn('default',window.iconbitmap.call_args.kwargs)
  self.assertTrue(window.iconbitmap.call_args.kwargs['default'].endswith('akira.ico'))
 def test_native_executable_carries_brand_and_version_resources(self):
  command=build_command(Path(__file__).resolve().parents[1],Path('/tmp/native'),Path('/tmp/work'))
  self.assertIn('--windowed',command);self.assertIn('--version-file',command)
  self.assertTrue(command[command.index('--version-file')+1].endswith('windows_version.txt'))
  self.assertTrue(command[command.index('--icon')+1].endswith('akira.ico'))
 def test_shortcut_sets_matching_identity_icon_and_native_target(self):
  link=Mock();properties=Mock();persist=Mock()
  link.QueryInterface.side_effect=lambda iid:properties if iid=='properties' else persist
  com=NS(CoInitialize=Mock(),CoUninitialize=Mock(),CoCreateInstance=Mock(return_value=link),CLSCTX_INPROC_SERVER=1,IID_IPersistFile='persist')
  shell=NS(CLSID_ShellLink='shell',IID_IShellLink='link')
  propsys=NS(IID_IPropertyStore='properties',PROPVARIANTType=lambda value:value)
  pscon=NS(PKEY_AppUserModel_ID='id',PKEY_AppUserModel_RelaunchDisplayNameResource='name',PKEY_AppUserModel_RelaunchIconResource='icon',PKEY_AppUserModel_RelaunchCommand='command')
  modules={'pythoncom':com,'win32com':NS(),'win32com.shell':NS(shell=shell),'win32com.propsys':NS(propsys=propsys,pscon=pscon)}
  with tempfile.TemporaryDirectory() as tmp,patch.dict('sys.modules',modules):
   root=Path(tmp);identity.create_shortcut(root/'AKIRA.lnk',root/'native/AKIRA/AKIRA.exe',root)
  properties.SetValue.assert_any_call('id',identity.APP_ID);properties.SetValue.assert_any_call('name','AKIRA')
  self.assertTrue(link.SetPath.call_args.args[0].endswith('AKIRA.exe'));self.assertTrue(link.SetIconLocation.call_args.args[0].endswith('akira.ico'));persist.Save.assert_called_once();com.CoUninitialize.assert_called_once()

if __name__=='__main__':unittest.main()
