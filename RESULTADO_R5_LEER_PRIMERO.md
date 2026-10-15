# AKIRA R5 — Correcciones sobre la compilación Windows 16.3.2

**No es un instalador**. Este ZIP contiene solamente archivos fuente que reemplazan los correspondientes en `juanpablo-ordo/akira` para que GitHub Actions construya de nuevo el instalador Windows.

## Errores observados en los videos y medidas implementadas

| Defecto | Cambio de código | Comprobación pendiente |
| --- | --- | --- |
| IA mostraba ACTIVO sin conversar | `assistant_akira.py` exige una inferencia visible real; la consulta `/models` deja de bastar. `akira_local_ai.py` usa `enable_thinking=False` para respuestas rápidas de Qwen3. | Abrir la app **instalada** en Windows y conversar sin Ollama. |
| Registro repetía fallos antiguos de PowerShell | En instalaciones `llama.cpp` gestionadas se ignora el antiguo estado de preparación de Ollama al determinar si la IA está lista. | Confirmar que una configuración anterior migra correctamente. |
| No se podía desinstalar | `application_management.py` busca `unins000.exe` del instalador nativo. Akira cierra su propio `llama-server.exe` al cerrarse, y sale después de iniciar el desinstalador. | Desinstalar y reinstalar desde Configuración de Windows; conservar MT5 y datos elegidos. |
| Limitador era otra ventana fija deformada | `desktop.py` lo integra desplegable dentro de Ajustes; controles fluidos, sin tamaño fijo. Tiempo de modelo cargado se aplica al proceso. | Revisar DPI, monitores y arrastre en Windows. |
| Falta descarga individual de voces | Ahora hay consulta de catálogo, **DESCARGAR VOZ ELEGIDA**, **DESCARGAR TODAS** y **CANCELAR DESCARGA**, con eventos propios y progreso. | Probar catálogo y descargas de red con modelos Piper. |
| Paneles saltaban al arrastrarlos | `desktop_layout.py` evita restaurar divisiones mientras se arrastran y espera al terminar de redimensionar. | Probar tamaño pequeño, grande y maximizado en Windows. |
| Sprites se veían deformes al reducirse | `akira_live2d.py` utiliza filtro adecuado para miniaturas y redimensionamiento diferido; conserva diez expresiones existentes. | **No se ha redibujado aún un set artístico nuevo**. |
| Errores HTTPS 403/503 | Se han diagnosticado como restricciones o fallos de fuentes de terceros. | **No está resuelto**; requiere reproducir URL, estado y fallback de cada fuente. |
| Runner y pendientes supuestamente óptimas | No se ha relajado el riesgo ni afirmado calidad sin evidencias. | **No probado** con historial y MT5 demo: prohibido asumir rentabilidad o ejecución real. |

## Pruebas realizadas en Linux con pantalla virtual

- 58 pruebas seleccionadas aprobadas, 1 omitida.
- Otras 50 pruebas y 7 subpruebas aprobadas, tras actualizar una expectativa obsoleta del desinstalador antiguo.
- `native_ui_check.run_ui_check` con `FakeMT5` produjo `PASSED`, con **17 validaciones** de GUI y sin cuenta real.
- Compilación sintáctica (`python -m compileall`) correcta.
- **La batería total de 1.049 pruebas no terminó por límite de ejecución**; dos pruebas antiguas de auto-revisión factual que simulan Ollama siguen fallando cuando se usa el nuevo backend local. Por lo tanto, NO se certifica la suite completa ni una prueba real de instalación de Windows.

## Instalación del parche en GitHub

1. Descomprime este ZIP. Copia **los archivos y carpetas dentro de la raíz** de tu repositorio `akira` (GitHub Desktop > Repository > Show in Explorer), manteniendo las rutas.
2. Haz Commit con resumen `R5: arreglar IA, desinstalador, voces y UI` y Push origin.
3. GitHub > Actions > `AKIRA Windows - verificar y compilar` > Run workflow en `main`.
4. Descarga únicamente el artefacto `AKIRA-16.3.2-instalador-Windows` de **esa nueva compilación** si todas las etapas pasan.
5. Prueba sin permitir ejecución de trading real. Comprueba chat Qwen, voces, rendimiento, desinstalador y recupera el historial solamente tras verificar la actualización.

**Importante**: GitHub rechaza las escrituras desde la conexión del asistente con `403 Resource not accessible by integration`, así que este ZIP no ha sido publicado automáticamente en tu repositorio.
