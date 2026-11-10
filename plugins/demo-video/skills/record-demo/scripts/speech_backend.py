"""Platform-specific Kokoro adapters. No MLX import on Linux."""
import hashlib
import os
import platform
import re
from pathlib import Path
from urllib.request import urlopen

ASSETS = {
 'kokoro-v1.0.onnx': 'beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a',
 'voices-v1.0.bin': 'bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d',
}
BASE = 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/'

def backend_name():
 name = os.environ.get('DEMO_TTS_BACKEND', 'mlx' if platform.system() == 'Darwin' and platform.machine() == 'arm64' else 'onnx')
 if name not in ('mlx', 'onnx'): raise ValueError('DEMO_TTS_BACKEND must be mlx or onnx')
 if name == 'mlx' and not (platform.system() == 'Darwin' and platform.machine() == 'arm64'):
  raise ValueError('MLX requires Apple Silicon; use DEMO_TTS_BACKEND=onnx on Linux')
 return name

def asset_paths():
 root = Path(os.environ.get('DEMO_KOKORO_DIR', str(Path(os.environ.get('XDG_CACHE_HOME', Path.home()/'.cache'))/'record-demo'/'kokoro-v1.0')))
 root.mkdir(parents=True, exist_ok=True)
 for name, expected in ASSETS.items():
  target = root/name
  if not target.exists():
   if os.environ.get('HF_HUB_OFFLINE') == '1': raise FileNotFoundError(f'Offline model missing: {target}')
   temporary = target.with_suffix(target.suffix+'.partial')
   try:
    with urlopen(BASE+name, timeout=120) as response, temporary.open('wb') as output:
     while chunk := response.read(1024*1024): output.write(chunk)
    if hashlib.sha256(temporary.read_bytes()).hexdigest() != expected: raise ValueError(f'Model hash mismatch: {name}')
    temporary.replace(target)
   finally:
    temporary.unlink(missing_ok=True)
  if hashlib.sha256(target.read_bytes()).hexdigest() != expected: raise ValueError(f'Model hash mismatch: {name}')
 return root

class SpeechBackend:
 def __init__(self, language='a'):
  self.language = 'en-gb' if language == 'b' else 'en-us'
  self.name = backend_name()
  if self.name == 'mlx':
   from mlx_audio.tts.utils import load_model
   self.model = load_model('mlx-community/Kokoro-82M-bf16')
   self.pipeline = self.model._get_pipeline(language)
   self.provenance = {'backend':'mlx', 'model':'mlx-community/Kokoro-82M-bf16'}
  else:
   from kokoro_onnx import Kokoro
   import onnxruntime as ort
   root = asset_paths()
   opts = ort.SessionOptions(); opts.intra_op_num_threads = int(os.environ.get('DEMO_TTS_THREADS', '4'))
   session = ort.InferenceSession(str(root/'kokoro-v1.0.onnx'), sess_options=opts, providers=['CPUExecutionProvider'])
   # kokoro-onnx 0.4.9 sends int32 speed for input_ids exports, while
   # the pinned v1.0 model declares float32. Respect the actual model type.
   class TypedSession:
    _model_path = str(root/'kokoro-v1.0.onnx')
    def get_inputs(self): return session.get_inputs()
    def run(self, outputs, inputs):
     import numpy as np
     inputs = dict(inputs)
     if next(i.type for i in session.get_inputs() if i.name == 'speed') == 'tensor(float)': inputs['speed'] = np.asarray(inputs['speed'], dtype=np.float32)
     return session.run(outputs, inputs)
   self.model = Kokoro.from_session(TypedSession(), str(root/'voices-v1.0.bin'))
   self.pipeline = None
   self.provenance = {'backend':'onnx', 'model':'Kokoro-82M v1.0', 'release':BASE, 'sha256':ASSETS, 'provider':'CPUExecutionProvider'}
 def audio(self, text, voice, speed):
  import numpy as np
  if self.name == 'mlx': return np.concatenate([np.array(r.audio) for r in self.model.generate(text=text,voice=voice,speed=speed,lang_code=voice[0])])
  phonemes = self.onnx_phonemes(text, 'en-gb' if voice.startswith('b') else 'en-us')
  audio,sr = self.model.create(phonemes,voice=voice,speed=float(speed),is_phonemes=True)
  if sr != 24000: raise ValueError(f'Unexpected speech sample rate: {sr}')
  return audio
 def phonemes(self, text):
  if self.name == 'mlx': return [(t.text,t.phonemes) for t in self.pipeline.g2p(text)[1] if t.phonemes]
  # Use exactly the tokenizer that the ONNX synthesizer uses, not another G2P model.
  return [(text,self.onnx_phonemes(text,self.language))]
 def onnx_phonemes(self, text, language):
  parts = re.split(r'\[([^\]]+)\]\(/([^)]*)/\)', text)
  return ' '.join(self.model.tokenizer.phonemize(value,lang=language) if i % 3 == 0 else value for i,value in enumerate(parts) if i % 3 != 1 and value.strip())
