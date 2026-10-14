# AKIRA — proyecto privado

Repositorio preparado para generar un ejecutable de Windows y localizar errores de compilación antes de producir un instalador final.

**Estado:** prototipo en desarrollo. NO apto todavía para trading real ni para distribución comercial. Las compilaciones automáticas son artefactos de prueba, **no** instaladores.

## Compilación de Windows

1. GitHub > Actions > **AKIRA Windows - verificar y compilar** > **Run workflow**.
2. Si todas las pruebas pasan, descargar `AKIRA-Windows-build-no-es-instalador` desde **Artifacts**.
3. Si falla, descargar `AKIRA-Windows-diagnosticos` y revisar la etapa exacta. El fallo no debe ocultarse.

El flujo instala dependencias, ejecuta pruebas seleccionadas, empaqueta `AKIRA.exe` mediante PyInstaller, realiza la autocomprobación que ya existe en `build_windows.py` y solo publica un ZIP binario si termina correctamente.

## Seguridad

No incluir claves API, contraseñas, cuentas reales de Exness/MT5, archivos `.env`, bases de datos ni diagnósticos personales. Se han sustituido números de cuenta presentes en pruebas antiguas por datos sintéticos; revisa el repositorio antes de compartirlo. La configuración de ejemplo inicia en **observe**.

Los modelos GGUF y `llama-server.exe` todavía no van integrados en la compilación de este flujo. Integrar un instalador nativo con descarga, cancelación y auditoría requiere una fase adicional con pruebas de Windows reales. No habilitar trading real.
