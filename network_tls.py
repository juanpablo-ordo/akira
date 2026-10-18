"""Verified HTTPS for source and frozen builds, using system and bundled roots.

Never weakens hostname/chain checks. The cached context is immutable after setup;
loading the Windows certificate stores for every RSS request is expensive.
"""
from functools import lru_cache
import ssl
from urllib import request


@lru_cache(maxsize=1)
def https_context():
    context = ssl.create_default_context()
    import certifi
    context.load_verify_locations(cafile=certifi.where())
    return context


def urlopen(url, data=None, timeout=10, **kwargs):
    # An explicit context is also needed after an HTTP -> HTTPS redirect.
    return request.urlopen(url, data=data, timeout=timeout,
                           context=https_context(), **kwargs)


def connection_message(error):
    """Public message only; the original exception stays in diagnostics."""
    text = str(error).lower()
    if any(s in text for s in ('certificate_verify_failed','certificate verify failed','local issuer certificate')):
        return ('CONEXIÓN SEGURA PENDIENTE',
                'No se pudo verificar el certificado de esta fuente. Comprueba la fecha de Windows y sus certificados. Akira reintentará automáticamente; las demás fuentes siguen activas.')
    if any(s in text for s in ('no tiene un asistente','modelo no disponible','motor local','llama.cpp')):
        return ('IA PENDIENTE',
                'La revisión de IA aún no está disponible. Akira intentará iniciar el modelo instalado. Si falta un componente, usa Reparar IA en Ajustes → IA y voz. No se considera aprobada ninguna revisión pendiente.')
    if any(s in text for s in ('timeouterror','timed out','timeout','tiempo de espera')):
        return ('REINTENTO PROGRAMADO', 'La fuente tardó demasiado. Akira conserva los datos vigentes y reintentará en segundo plano.')
    if any(s in text for s in ('urlerror','connectionerror','connection refused','getaddrinfo','name resolution')):
        return ('SIN CONEXIÓN CON LA FUENTE', 'Esta fuente no respondió. Las demás fuentes siguen activas y se reintentará automáticamente.')
    return ('NO DISPONIBLE', 'Esta consulta no pudo completarse. Se reintentará en segundo plano. Puedes consultar el diagnóstico en Terminal.')
