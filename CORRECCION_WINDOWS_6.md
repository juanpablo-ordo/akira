# AKIRA Studio Rev5 · corrección Windows 6

La ejecución 27 (`39007735029`, commit `4d3511e66474e677a5a929a8c39971ec52947781`) aprobó la nueva comprobación de importaciones, pero falló al borrar `fixture.mp4` después de probar el fondo de video: `PermissionError: [WinError 32]`. Terminó con 1.215 pruebas aprobadas, una fallida y una omitida por falta de pantalla Tk. Las etapas posteriores no se ejecutaron.

## Corrección

El cierre del decodificador ahora tiene una barrera explícita: el hilo deja de leer, cierra la salida para que FFmpeg no quede bloqueado escribiendo, solicita el fin del proceso propio, confirma su terminación nativa y libera su handle. Si excede el plazo, detiene y espera exclusivamente ese proceso; un cierre no confirmado continúa siendo un error. La confirmación Windows usa el handle real y no depende únicamente del código de salida que Python pudiera haber guardado.

La ventana conserva la propiedad del decodificador durante el cierre. Un cambio de fondo o de tamaño espera mediante un temporizador a que termine el anterior, sin iniciar varios decodificadores a la vez. El cierre final de la aplicación espera también al hilo lector. Se libera el fotograma pendiente y se protege la recepción de la interfaz frente al vaciado de la cola durante el cierre.

La prueba original comprueba que el hilo y el proceso terminaron, la salida está cerrada y el archivo realmente se borró antes de eliminar su carpeta. En las pruebas, solo los errores Windows 32/33 de acceso compartido tienen un plazo máximo de dos segundos para observar la liberación efectiva: otros permisos y los bloqueos persistentes siguen fallando. Esto contempla lectores externos temporales, como un escáner; el registro original no identifica qué proceso retenía el archivo.

## Verificación

Las pruebas nuevas ejercitan el estado de salida guardado, el agotamiento del plazo, la cancelación durante el arranque y doce ciclos reales de reproducción/cierre/borrado. Mantienen abierto otro proceso y exigen que no se detenga. También verifican que no se sustituye un trabajador mientras siga vivo y que los bloqueos persistentes no se ocultan.

Las once pruebas dirigidas pasaron en Linux. También pasaron **1.226 pruebas y 118 subpruebas** con Tcl/Tk 8.6.14 en pantalla de 1024 × 768, y **1.223 pruebas unittest con la red bloqueada** con Tcl/Tk 9.0.4 y pantalla grande; sin fallos ni omisiones. Los doce ciclos tardaron 0,26 s en esa ejecución; esa medición corresponde a un video sintético pequeño, no al rendimiento del equipo del usuario. La rama de espera Win32 se prueba con un handle simulado; la revisión necesita CI Windows para validar esa plataforma. Las suites completas y sus cifras finales están en `VALIDACION_STUDIO_REV5.json` y `VERIFICACION_STUDIO_FIX6`.

Se conservan los arreglos de importación de FIX5 y su evidencia con Qwen3 real en Linux. El motor financiero, los parámetros de riesgo, el cliente de IA y la configuración no cambian.

## Publicar

1. Extrae todo el ZIP en una carpeta nueva.
2. Ejecuta `PUBLICAR_A_GITHUB_REV5.cmd`.
3. En https://github.com/juanpablo-ordo/akira/actions comprueba una ejecución nueva con **corrección Windows 6**.

Reejecutar la ejecución 27 conserva el código que falló. El instalador Windows con IA solo se publica después de superar todas las etapas, incluida la prueba de la IA realmente instalada.
