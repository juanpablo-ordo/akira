# AKIRA Studio Rev5 · corrección Windows 2

El video corresponde a la ejecución 23 de GitHub, commit `b5e8cf5550bb5cd3d361701b8a29eba525e48e0a`. Windows aprobó las 1.202 pruebas y 102 subpruebas de FIX1, la biblioteca Tcl/Tk y la inferencia visual CPU de origen. El ejecutable se construyó, pero su autocontrol falló con «No se completó el dibujado de charts». El instalador no llegó a generarse.

## Corrección

Se reprodujo un fallo de distribución con texto grande: los gráficos conservaban 80 velas pero su altura se reducía a 21 píxeles, por debajo de los 70 que necesita el dibujado. El diagnóstico original de Windows no conservó esas dimensiones; esta reproducción local explica una causa comprobada del mismo fallo, pendiente de confirmar en el ejecutable Windows.

El área de mercado ahora conserva la altura natural de los gráficos y permite desplazar su contenido. También se retiró un segundo ajuste de ancho que competía con el ajuste propio de la etiqueta y provocaba ciclos continuos de redimensionado. En las pruebas corregidas ambos gráficos miden 107 píxeles y dibujan las 80 velas, incluso con escala de texto 2.667.

El autocontrol sigue exigiendo que los gráficos se dibujen. Si falla, el JSON y el error de compilación incluyen ancho, alto, datos recibidos, elementos dibujados y escala. CI prueba además la interfaz de origen antes de compilar el ejecutable. Los módulos de análisis, ejecución, riesgo y configuración financiera no se modificaron.

## Verificación

- 1.204 pruebas pytest y 102 subpruebas aprobadas, sin fallos ni omisiones.
- 1.201 pruebas unittest con la red bloqueada, sin fallos ni omisiones.
- Autocontrol Tk de 27 comprobaciones con escala normal y texto grande; autocontrol Qt predeterminado de 12 comprobaciones.
- Regresión nueva con ventanas de 1366 × 768 y 1024 × 640, divisor reducido, datos de velas sintéticos de FakeMT5, desplazamiento y convergencia del ajuste de texto.

Evidencia local actual: `VERIFICACION_STUDIO_FIX2`. Los archivos `WINDOWS_RUN23_*` conservan los resultados de la ejecución Windows anterior y su fallo; no certifican FIX2. Las mediciones anteriores R8/Rev4/FIX1 son históricas. El modelo GGUF, el ejecutable FIX2, la instalación Windows y MT5 demo siguen pendientes.

## Qué ejecutar

1. Extrae el ZIP actualizado en una carpeta nueva de Windows.
2. Ejecuta `PUBLICAR_A_GITHUB_REV5.cmd`. Actualiza la misma rama `akira-studio-rev5-20261016` usando Git autenticado de tu computadora.
3. Abre https://github.com/juanpablo-ordo/akira/actions y comprueba una ejecución nueva cuyo título incluya **corrección Windows 2**.
4. Tras superar todas las fases, descarga el artefacto con IA incluida y ejecuta `AKIRA_16_4_0_STUDIO_REV5_IA_INCLUIDA.exe`.

La escritura conectada desde aquí sigue respondiendo HTTP 403. Esta corrección necesita un commit nuevo; reejecutar la ejecución 23 conserva el código que falló. Este ZIP contiene el código completo y los recursos; el instalador final se genera en CI.
