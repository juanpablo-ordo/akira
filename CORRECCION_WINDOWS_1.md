# AKIRA Studio Rev5 · corrección Windows 1

Corrección del registro recibido con 4 fallos y 1.193 pruebas aprobadas. La Rev5 original está publicada en la rama `akira-studio-rev5-20261016`, commit `7097b5bdf57b1b63e39a0d08ba6f25c206e4e6c6`; su ejecución 22 falló en las regresiones.

## Cambios

- Las pruebas de migración comparan el archivo real y su pertenencia al nuevo destino. Windows puede representar el mismo directorio como `RUNNER~1` o `runneradmin`; esa diferencia de texto no demuestra pérdida de datos.
- La comprobación de botones y etiquetas usa el tamaño natural solicitado por el control nativo de la plataforma. Se mantienen pruebas que rechazan el recorte horizontal, vertical y los controles fuera de ventana.
- La prueba de pendientes cierra Desktop completo, con sus temporizadores y recursos, antes de destruir el intérprete Tk.
- CI comprueba los scripts Tcl/Tk del Python seleccionado, los copia a una carpeta independiente, verifica todos sus hashes y prueba tres inicializaciones nativas, incluyendo Progressbar. Si falta un script o no carga, falla con un diagnóstico específico antes de las regresiones. No se ocultan errores ni se omiten pruebas. El origen intermitente del fallo original de Tk requiere confirmación en Windows.
- El publicador detecta y actualiza la rama existente sin forzar su historial. Permite correcciones pequeñas y conserva la comprobación de árbol completo.

## Pruebas realizadas

1.202 pruebas pytest y 102 subpruebas, sin fallos ni omisiones. 1.199 pruebas unittest con red bloqueada, sin fallos ni omisiones. Autocontroles nativos: 27 comprobaciones Tk y 12 Qt. Se añadieron cinco regresiones para biblioteca incompleta, copia independiente, integridad y geometría nativa.

Evidencia actual en `VERIFICACION_STUDIO_FIX1`. Estas ejecuciones corresponden a Linux y Tcl/Tk 9.0; la nueva ejecución de Windows comprobará su Tcl/Tk 8.6, las rutas 8.3 y la geometría Win32. El EXE y la instalación Windows siguen pendientes.

## Cómo subir la corrección

1. Extrae este ZIP actualizado en una carpeta nueva de tu computadora Windows.
2. Ejecuta `PUBLICAR_A_GITHUB_REV5.cmd` dentro de la carpeta extraída. Usa el inicio de sesión de Git de tu computadora.
3. Comprueba la nueva ejecución en https://github.com/juanpablo-ordo/akira/actions. Su título debe incluir **corrección Windows 1** y la rama `akira-studio-rev5-20261016`.
4. Si termina en verde, descarga el artefacto del instalador con IA incluida indicado en `README.md`.

La conexión de escritura desde aquí sigue respondiendo HTTP 403; esta corrección aún no se ha subido por ese acceso. Reejecutar la ejecución 22 usa el commit anterior: para comprobar el arreglo se necesita el commit nuevo que publica el script.
