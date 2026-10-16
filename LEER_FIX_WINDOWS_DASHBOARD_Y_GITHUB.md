# AKIRA 16.3.5 R8 Studio Rev4 — dashboard Windows

**Corregido:** tablero de BTC y oro prioriza espacio real del Canvas en resoluciones reducidas y DPI alto; el autocontrol deja de ubicar la ventana fuera de pantalla, y ahora registra dimensiones mientras la pestaña del tablero aún está abierta. Estas medidas anteriores eran engañosas al leerse tras navegar a Ajustes.

**Resultado local:** `1190 passed, 90 subtests passed` (Linux/Xvfb). Pruebas específicas a 1024x768 y escala Tk 1.5 aprobadas. **Pendiente:** GitHub Actions en Windows, autocontrol de AKIRA.exe, compilación del instalador e integración MT5 demo. No usar dinero real.

**GitHub:** el publicador `PUBLICAR_A_GITHUB_REV4.cmd` y `.ps1` están actualizados al commit de la rama `b040778873006bd6b50da61968eec015cb39fe85`. El publicador no toca `main`; requiere Git autenticado y Windows. Verifique la rama actual antes de publicarlo. Si la rama cambió, se detendrá.

**Límite de esta conversación:** la integración GitHub rechazó una escritura con HTTP 403 `Resource not accessible by integration`. Por ello el código de este ZIP NO fue subido a GitHub. Se necesita autorizar escritura en el conector o usar Work (navegador de nube autenticado en GitHub) o ejecutar el publicador desde Windows.

Este ZIP contiene el proyecto completo (código fuente), no un EXE o instalador certificado. Los valores reales de claves, archivos `.env`, `.gguf`, datos de cuenta MT5 y logs privados quedan excluidos.
