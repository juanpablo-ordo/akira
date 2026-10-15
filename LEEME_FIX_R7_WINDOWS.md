# AKIRA R7 — corrección de las regresiones de Windows

Parche para el código R7 del commit c67f322e9a540afd64dc9f377667d98d8e6a4bb3, cuya ejecución 12 falló en seis pruebas. Se conserva la versión 16.3.4 R7.

## Cómo aplicarlo

1. Extrae este ZIP y copia todo su contenido dentro de la carpeta local de tu repositorio `akira`, junto a `Akira.py`. Acepta reemplazar los archivos y combinar las carpetas `tests` y `VERIFICACION_R7_WINDOWS_FIX`.
2. En GitHub Desktop, haz Commit y Push de los cambios. También deben subirse los tres manifiestos SHA-256 y `VALIDACION_V12.json` incluidos en el parche.
3. Abre Actions → AKIRA Windows - verificar y compilar → Run workflow → main. Inicia una ejecución nueva después del Push: «Re-run jobs» en la ejecución 12 usa su commit anterior.
4. Cuando la nueva ejecución complete todas las comprobaciones, descarga el artefacto `AKIRA-16.3.4-R7-IA-fuentes-expresiones-instalador-Windows-IA-INCLUIDA` y ejecuta `AKIRA_16_3_4_R7_IA_INCLUIDA.exe`.

## Qué se corrige

- Windows puede nombrar una misma carpeta temporal como `RUNNER~1` o `runneradmin`. Las pruebas ahora preparan rutas canónicas y sus simulaciones de permisos comparan rutas resueltas. Permanecen las comprobaciones de restauración del acceso directo, conservación de datos, prioridad de la instalación activa y aplazamiento de carpetas bloqueadas.
- El avatar asigna su primera imagen al crear el lienzo. Así tiene una imagen válida aunque Windows todavía no haya enviado el evento de mostrar la ventana. Las expresiones posteriores de paneles ocultos esperan hasta que el panel se muestra, conservando el trabajo reducido en segundo plano.
- La prueba de las 108 expresiones procesa los eventos de ventana antes de comprobar su representación. Dos pruebas adicionales cubren el primer frame y los cambios mientras el panel está oculto.
- Se actualizan los recuentos de pruebas y los manifiestos de integridad del paquete.

## Verificación

En Linux: 1.096 pruebas pytest y 83 subpruebas aprobadas, sin fallos ni omisiones; 1.093 pruebas unittest aprobadas con las conexiones de red bloqueadas. Se reprodujeron los cinco fallos de rutas mediante dos nombres para una misma carpeta: cinco fallos antes del parche y ninguno después.

Los informes se incluyen en `VERIFICACION_R7_WINDOWS_FIX`. La nueva compilación y el instalador Windows quedan pendientes de GitHub Actions. Las comprobaciones de compilación, IA instalada e instalación completa siguen siendo obligatorias en el workflow.
