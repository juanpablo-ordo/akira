"""Voz local con micrófono explícito, sin PowerShell ni escucha en segundo plano.

Windows controla los permisos de las aplicaciones de escritorio en Configuración >
Privacidad y seguridad > Micrófono. Tk no genera el diálogo de permisos
propio de Chrome, por lo que pedimos consentimiento en la ventana de Akira.
"""
from __future__ import annotations
import os, re, threading

_MODEL = None
_MODEL_LOCK = threading.Lock()


def microphone_devices():
    """Lista micrófonos; no graba ni solicita permisos."""
    import sounddevice as sd
    return [(int(i), str(d['name'])) for i,d in enumerate(sd.query_devices())
            if int(d.get('max_input_channels', 0)) > 0]


def listen_once(timeout_seconds=9, device=None):
    if os.name != 'nt':
        raise RuntimeError('La captura de micrófono está disponible en la aplicación para Windows.')
    try:
        import sounddevice as sd
        import numpy as np
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError('Falta el módulo de voz. Instala las dependencias de Akira: sounddevice y faster-whisper.') from exc
    devices = microphone_devices()
    if not devices:
        raise RuntimeError('Windows no detectó ningún micrófono. Revisa Configuración > Privacidad y seguridad > Micrófono y permite aplicaciones de escritorio.')
    if device is not None and int(device) not in [i for i,_ in devices]:
        raise RuntimeError('El micrófono seleccionado ya no está conectado.')
    sample_rate = 16000
    try:
        recorded = sd.rec(int(sample_rate*max(3,min(12,float(timeout_seconds)))),
                          samplerate=sample_rate,channels=1,dtype='float32',device=device)
        sd.wait()
    except Exception as exc:
        raise RuntimeError('No se pudo utilizar el micrófono. Autoriza las aplicaciones de escritorio en la privacidad de Windows y verifica que el dispositivo funcione.') from exc
    audio=np.asarray(recorded,dtype='float32').reshape(-1)
    if audio.size==0 or float(np.max(np.abs(audio)))<0.005:
        raise RuntimeError('No detecté voz. Comprueba el micrófono o habla un poco más cerca.')
    global _MODEL
    with _MODEL_LOCK:
        if _MODEL is None:
            # Modelo pequeño: se descarga una vez; no mantiene el micrófono activo.
            _MODEL=WhisperModel('tiny',device='cpu',compute_type='int8',cpu_threads=2,num_workers=1)
    segments,_=_MODEL.transcribe(audio,language='es',beam_size=2,
                                  vad_filter=True,condition_on_previous_text=False)
    return ' '.join(str(s.text).strip() for s in segments).strip()[:1500]


def speak_async(text):
    """Usa la voz del sistema solo si el usuario activó lectura de respuestas."""
    if os.name!='nt':return
    clean=re.sub(r'\[([^\]]+)\]\(https?://[^)]+\)',r'\1',str(text or ''))
    clean=re.sub(r'https?://\S+','fuente consultada',clean).strip()[:3000]
    if not clean:return
    def work():
        try:
            import pyttsx3
            engine=pyttsx3.init()
            engine.say(clean);engine.runAndWait();engine.stop()
        except Exception:
            pass
    threading.Thread(target=work,name='AkiraTTS',daemon=True).start()
