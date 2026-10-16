# AKIRA 16.3.5 R8 Studio Rev4 — publicación y Windows CI

**Este archivo es código fuente, no un instalador completo.** El script publica la fuente saneada en una rama nueva del repositorio autorizado `juanpablo-ordo/akira`. **No toca la rama `main` ni los datos de tu instalación**, ni puede activar operaciones reales.

El acceso de GitHub de ChatGPT devolvió `403 Resource not accessible by integration` al intentar crear la rama. Por eso la publicación no está hecha todavía. Si el repositorio permite escribir con tu sesión de GitHub Desktop/Git, descomprime el ZIP en Windows y abre `PUBLICAR_A_GITHUB_REV4.cmd` para subir la rama. La compilación se inicia automáticamente en GitHub Actions mediante el evento push. Si pide iniciar sesión o falla por permisos, no se habrá publicado; comprueba el mensaje.

**Privacidad:** se excluyeron bases SQLite de `state/` y cualquier `.env`, archivos de credenciales, registros, modelos y ejecutables; nunca subas el ZIP anterior a un repositorio público tal cual.

**Equipo de referencia recuperado:** RTX 5060 Ti 8 GB, RAM DDR5 32 GB 6000 MHz, Intel i7 12.ª generación serie K (modelo exacto no proporcionado), ROG STRIX Z790-H. Perfil inicial del modelo local: Qwen3-4B-GGUF Q4_K_M, contexto 4096, 12 capas de GPU, 1 petición concurrente. No son límites físicos garantizados.

**Antes de llamar 'listo' al ejecutable:** ejecutar build Windows con modelo incorporado, instalar en una máquina Windows real, comprobar lectura/escritura de ajustes, GPU y Wallpapers, MT5 demo con pendientes y runners y protección real, errores/reconexión, al menos seis horas de sesión y métricas de ejecución. Ninguna suite simulada garantiza rentabilidad ni cubre los 232 requisitos.
