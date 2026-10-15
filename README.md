# AKIRA — estado de desarrollo (R5)

**AKIRA es todavía un prototipo en pruebas. No activar trading automático con dinero real.**

El flujo `AKIRA Windows - verificar y compilar` construye `AKIRA.exe`, descarga los binarios oficiales de `llama.cpp`, prueba una respuesta real de Qwen3 en Windows, y compila un instalador Inno Setup. Una compilación verde **no demuestra** que el chat, voz, red, trading o interfaz respondan correctamente en todas las computadoras.

## Correcciones R5 de fallos grabados

- La IA integrada no se declara disponible solo por `/v1/models`; exige texto visible generado en una prueba de fondo.
- El cliente local Qwen3 usa explícitamente modo sin razonamiento para respuestas rápidas (sin impedir que conversaciones avanzadas pidan razonamiento).
- Ajustes > Limitador aparece dentro de la ventana principal y el control de descarga de memoria configura de verdad el tiempo de inactividad del proceso `llama.cpp`.
- Voz: consulta catálogo, descarga una voz elegida y cancela esa descarga sin cerrar la aplicación. Se conserva la opción de descargar todas.
- Desinstalador: busca primero el nativo `unins000.exe` de Inno Setup junto a la aplicación; no obliga a tener el viejo `.ps1`.
- Las divisiones redimensionables dejan de corregirse mientras el usuario las arrastra; los PNG del avatar se redimensionan con filtro adaptativo.

## Pendiente de validación real

El rediseño completo del avatar, rendimiento continuo al mover/ajustar ventanas en todos los monitores, fuentes HTTPS de terceros, modo llamada, calidad de runners/pendientes y resultados del trading necesitan pruebas posteriores; **no están certificados**. No se ha comparado una rentabilidad atribuible a esta revisión.

## Cómo compilar

GitHub > Actions > `AKIRA Windows - verificar y compilar` > Run workflow en `main`. Descarga `AKIRA-16.3.2-instalador-Windows` si aparece. Las pruebas realizan acciones con datos sintéticos, no con la cuenta real.

## Seguridad

Nunca incluyas contraseñas, tokens, archivos `.env` ni datos de cuenta. Por ser un repositorio público, cualquiera puede leer el historial. Si deseas seguir trabajando en privado, cambia la visibilidad cuando corresponda.
