# AKIRA Studio Rev5 · corrección Windows 4

La ejecución Windows 25 (`39004132398`, commit `9446986a1dafd45bbc1551753d4f3f471f739de1`) terminó con 1.205 pruebas aprobadas y 2 fallidas. El límite externo de FIX3 funcionó y conservó el diagnóstico: el primer `update()` no regresó al solicitar 1366 × 768, con escala 2 y monitor de 1024 × 768. Otra prueba falló al crear Tk con `invalid command name "tcl_findLibrary"`. No se construyó el instalador.

## Cambios

Se retiraron los ajustes de ancho duplicados en etiquetas de fuentes, ajustes, interruptores, avisos y optimización. Cada etiqueta conserva un único ajuste basado en el ancho que realmente recibe. El ajuste de texto y la sincronización de paneles se agrupan en el siguiente fotograma de 16 ms, evitando modificar otra vez la geometría dentro del mismo pase nativo. La rueda sincroniza sus límites antes del primer movimiento, tanto en paneles como en avisos.

La prueba de alto DPI usa el mismo cálculo de tamaño que la aplicación: limita sus perfiles al monitor disponible y exige que el tamaño real coincida con el calculado. En el servidor de 1024 × 768, los perfiles se comprueban a 992 × 688 y 992 × 640; en el monitor local grande conservan 1366 × 768 y 1024 × 640. Se mantienen 80 velas por símbolo, altura mínima de 70 píxeles, dibujo real, desplazamiento y convergencia. También se abren Fuentes y Ajustes y se verifica un temporizador de respuesta.

El nuevo `tk_runtime.py` crea primero el intérprete Tcl, carga `tcl_findLibrary` desde el `auto.tcl` de esa misma biblioteca y después inicia Tk. La aplicación heredada, sus autocontroles y las pruebas usan ese mismo arranque. La comprobación previa exige `auto.tcl` y `tclIndex` y realiza 12 inicializaciones nativas. La prueba del cargador ausente, la de archivo ausente y las inicializaciones repetidas usan intérpretes reales. No se sustituyen por aprobaciones simuladas ni se reintenta un error para ocultarlo.

## Verificación y alcance

Los informes actuales están en `VERIFICACION_STUDIO_FIX4`; el registro Windows recibido está conservado como evidencia del fallo de FIX3. Se ejecutan suites completas en Linux Tcl/Tk 8.6.14 con pantalla de 1024 × 768 y Tcl/Tk 9.0.4 con pantalla grande, además de los autocontroles Tk/Qt y las 12 inicializaciones. Los cambios no amplían riesgo ni modifican el motor financiero.

El bloqueo Win32 exacto no se reprodujo localmente. Esta revisión corrige factores comprobables de reflujo e inicialización y debe superar CI Windows; los resultados Linux no certifican Windows. EXE, IA instalada, audio físico y MT5 demo siguen pendientes.

## Publicar

Extrae el ZIP en una carpeta nueva y ejecuta `PUBLICAR_A_GITHUB_REV5.cmd`. El workflow nuevo debe mostrar **corrección Windows 4**. La ejecución 25 usa su propio commit y no incorpora este código al reejecutarse. El instalador con IA incluida solo se publica después de superar todos los controles.
