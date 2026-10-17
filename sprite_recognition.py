"""Offline semantic sprite suggestions with a pinned CPU CLIP component.

Scores are relative similarities, never calibrated emotion probabilities.
Ambiguous matches remain editable. This module cannot import the trading actor.
"""
from __future__ import annotations
import gc,json,sys,threading
from pathlib import Path

PROMPTS={
 'idle':['a neutral relaxed cartoon character looking forward','an idle character sprite with open eyes'],
 'blink':['a cartoon character blinking with closed eyelids','a face with eyes half closed for a blink'],
 'listening':['a cartoon character listening attentively','an attentive curious face listening'],
 'talking':['a cartoon character speaking with mouth open','an animated face talking'],
 'thinking':['a thoughtful cartoon character thinking','a puzzled character considering a question'],
 'analyzing':['a focused cartoon character concentrating','an observant serious character studying'],
 'happy':['a happy smiling cartoon character','a cheerful joyful character sprite'],
 'alert':['an alarmed worried cartoon character','a character surprised by danger'],
 'sleeping':['a cartoon animal sleeping curled up','a sleeping character lying down with eyes closed'],
 'loading':['a character waiting with a loading spinner','a cartoon character waiting patiently'],
 'connecting':['a character waiting for a network connection','a cartoon character looking for a signal'],
 'waking':['a sleepy cartoon character waking up and stretching','a character opening eyes after sleep'],
 'bullish':['an optimistic excited cartoon character','a confident cheering character'],
 'bearish':['a concerned sad cartoon character','a cautious character with a worried expression'],
 'caring':['an affectionate gentle cartoon character','a warm caring character smiling softly'],
 'surprised':['a surprised cartoon character with wide eyes','an astonished character with open mouth'],
}


def component_root():
    roots=[Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'assets/sprite_vision',Path(sys.executable).resolve().parent/'sprite_vision']
    return next((root for root in roots if (root/'vision_model_quantized.onnx').is_file()),roots[0])


class SpriteRecognizer:
    def __init__(self,root=None):
        self.root=Path(root) if root else component_root();self.session=None;self.vectors=None;self.lock=threading.Lock()
    def available(self):return all((self.root/name).is_file() for name in ('vision_model_quantized.onnx','text_model_quantized.onnx','tokenizer.json'))
    def load(self):
        import numpy as np,onnxruntime as ort
        from tokenizers import Tokenizer
        options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
        options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
        tokenizer=Tokenizer.from_file(str(self.root/'tokenizer.json'));tokenizer.enable_truncation(max_length=77);tokenizer.enable_padding(length=77,pad_id=49407,pad_token='<|endoftext|>')
        text=ort.InferenceSession(str(self.root/'text_model_quantized.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
        self.labels=[];prompts=[]
        for state,values in PROMPTS.items():
            for value in values:prompts.append(value);self.labels.append(state)
        encoded=tokenizer.encode_batch(prompts);ids=np.asarray([row.ids for row in encoded],dtype=np.int64);mask=np.asarray([row.attention_mask for row in encoded],dtype=np.int64)
        inputs={row.name:(mask if 'mask' in row.name else ids) for row in text.get_inputs()}
        outputs=text.run(None,inputs);index=next((i for i,row in enumerate(text.get_outputs()) if 'text_embeds' in row.name),0)
        vectors=outputs[index];self.vectors=vectors/np.maximum(1e-12,np.linalg.norm(vectors,axis=1,keepdims=True));del text;gc.collect()
        self.session=ort.InferenceSession(str(self.root/'vision_model_quantized.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
    def classify(self,path):
        if not self.available():return None
        import numpy as np
        from PIL import Image
        with self.lock:
            if self.session is None:self.load()
            with Image.open(path) as source:
                source=source.convert('RGBA');bounds=source.getchannel('A').getbbox()
                if not bounds:return None
                source=source.crop(bounds);side=max(source.size);square=Image.new('RGBA',(side,side),(127,127,127,255));square.alpha_composite(source,((side-source.width)//2,(side-source.height)//2))
                array=np.asarray(square.convert('RGB').resize((224,224),Image.Resampling.BICUBIC),dtype=np.float32)/255
            array=(array-np.array([.48145466,.4578275,.40821073],np.float32))/np.array([.26862954,.26130258,.27577711],np.float32)
            tensor=np.transpose(array,(2,0,1))[None,...].astype(np.float32)
            outputs=self.session.run(None,{self.session.get_inputs()[0].name:tensor});index=next((i for i,row in enumerate(self.session.get_outputs()) if 'image_embeds' in row.name),0)
            vector=outputs[index];vector=vector/np.maximum(1e-12,np.linalg.norm(vector,axis=1,keepdims=True));scores=(vector@self.vectors.T)[0]
            ranked=sorted(((state,float(max(scores[i] for i,name in enumerate(self.labels) if name==state))) for state in PROMPTS),key=lambda row:row[1],reverse=True)
            margin=ranked[0][1]-ranked[1][1]
            return {'state':ranked[0][0],'score':round(ranked[0][1],4),'margin':round(margin,4),'requires_review':margin<.025,'alternatives':[{'state':name,'score':round(score,4)} for name,score in ranked[:3]],'method':'CLIP CPU zero-shot; similarity is not a probability'}


def annotate(entries,existing_ids=(),recognizer=None):
    result=[dict(row) for row in entries];recognizer=recognizer or SpriteRecognizer();known=set(existing_ids)
    for row in result:
        if row['id'] in known or float(row.get('confidence',0))>=.8:continue
        if not recognizer.available():
            row['recognition_note']='Modelo visual no disponible; sugerencia por nombre o movimiento. Se instala con el componente visual.';continue
        try:
            prediction=recognizer.classify(row['path'])
            if not prediction:continue
            row['visual_recognition']=prediction
            if not prediction['requires_review']:
                row.update(state=prediction['state'],detected_by=prediction['method'],confidence=prediction['score'])
            else:row['recognition_note']='Expresión ambigua; se conserva la propuesta anterior y las alternativas para revisión.'
        except (OSError,ValueError,RuntimeError,ImportError) as error:row['recognition_note']='No terminó el reconocimiento visual: '+type(error).__name__
    return result

def check_visual_component():
    """Real local ONNX inference gate; a fixture test is not semantic accuracy."""
    import math
    from avatar_animation import StateSprites
    from tempfile import TemporaryDirectory
    recognizer=SpriteRecognizer()
    if not recognizer.available():raise FileNotFoundError('Falta el componente visual local incluido en el instalador Studio completo')
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent));sprites=StateSprites(root)
    with TemporaryDirectory(prefix='akira-visual-check-') as tmp:
        path=Path(tmp)/'fixture.png';sprites.image(5,240,240).save(path)
        result=recognizer.classify(path);again=recognizer.classify(path)
    if not result or result!=again or not math.isfinite(result['score']) or result['state'] not in PROMPTS:raise RuntimeError('El componente visual no produjo una salida local finita y reproducible')
    return {'status':'PASSED','provider':'CPUExecutionProvider','fixture':'bundled sleeping sprite','prediction':result,'network_used':False,'universal_recognition_verified':False}
