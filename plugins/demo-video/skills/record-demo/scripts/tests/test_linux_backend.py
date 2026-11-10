import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('speech_backend',Path(__file__).resolve().parents[1]/'speech_backend.py')
speech=importlib.util.module_from_spec(spec);spec.loader.exec_module(speech)
class PlatformTests(unittest.TestCase):
 def test_linux_selects_onnx_without_loading_mlx(self):
  with patch.dict('os.environ',{},clear=True),patch.object(speech.platform,'system',return_value='Linux'):
   self.assertEqual(speech.backend_name(),'onnx')
 def test_apple_silicon_keeps_mlx(self):
  with patch.dict('os.environ',{},clear=True),patch.object(speech.platform,'system',return_value='Darwin'),patch.object(speech.platform,'machine',return_value='arm64'):
   self.assertEqual(speech.backend_name(),'mlx')
 def test_reject_mlx_on_linux(self):
  with patch.dict('os.environ',{'DEMO_TTS_BACKEND':'mlx'},clear=True),patch.object(speech.platform,'system',return_value='Linux'):
   with self.assertRaises(ValueError):speech.backend_name()
 def test_corrupt_cached_asset_rejected(self):
  with tempfile.TemporaryDirectory() as d,patch.dict('os.environ',{'DEMO_KOKORO_DIR':d}):
   (Path(d)/'kokoro-v1.0.onnx').write_bytes(b'bad')
   with self.assertRaises(ValueError):speech.asset_paths()
 def test_offline_missing_asset_rejected(self):
  with tempfile.TemporaryDirectory() as d,patch.dict('os.environ',{'DEMO_KOKORO_DIR':d,'HF_HUB_OFFLINE':'1'}):
   with self.assertRaises(FileNotFoundError):speech.asset_paths()
 def test_explicit_phonemes_bypass_g2p(self):
  class Tokenizer:
   def phonemize(self,text,lang):return text.strip().upper()
  m=speech.SpeechBackend.__new__(speech.SpeechBackend)
  m.model=type('Model',(),{'tokenizer':Tokenizer()})()
  self.assertEqual(m.onnx_phonemes('Use [name](/neɪm/) here.','en-us'),'USE neɪm HERE.')
if __name__=='__main__':unittest.main()
