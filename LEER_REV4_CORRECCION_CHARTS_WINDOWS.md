# AKIRA R8 Studio Rev4 — corrección comprobación nativa de gráficos

## Fallo de GitHub verificado

En el commit `622c8ffe0932034db6cd8b3aa06325426e679159` de la rama `akira-r8-studio-rev4-20261016`, `build_windows.py` construyó AKIRA.exe pero su autocontrol falló con `No se completó el dibujado de charts`. El diagnóstico `NATIVE_SELF_CHECK.json` publicado por GitHub confirmó únicamente ese control fallido. No se compiló el instalador.

## Reproducción y corrección

- En Linux bajo Xvfb y escalado Tk de 150 %, el lienzo gráfico de BTC y oro tenía **64 px de alto**, menos que el mínimo real de 70 px requerido por `chart_render.render`. Por eso tenía 80 velas cargadas, pero **0 elementos dibujados**. A 200 % también se reprodujo inicialmente.
- Se aumentó el mínimo del panel de gráficos de 115 a **220 px**, permitiendo la representación de velas a 100, 150 y 200 % en la ventana de prueba 1600x900.
- `native_ui_check.py` comprueba dimensiones, velas, presencia real en pantalla y número de objetos trazados; intenta repintar después de estabilizar el diseño durante un plazo finito. Si vuelve a fallar, el detalle `chart_geometry` incluye ancho, alto, velas y elementos dibujados por símbolo. No se elimina la protección que bloquea un ejecutable cuyo dibujo esté incompleto.
- `tests/test_r13_chart_dpi.py` añade tres casos: comprobación integral a 150 %, los gráficos reales de la pantalla principal a 200 % y rechazo de lienzos demasiado pequeños.
- `ci_windows_tests.py` ejecuta cada nueva prueba de Tk en un proceso aislado, sin omitir el resto.

## Pruebas realizadas

- **57 pruebas + 5 subpruebas** de gráficos, Inicio, Pendientes, temas, geometría, instalación y CI aprobaron en Linux/Xvfb.
- Se intentó toda la suite, pero se detuvo en una prueba antigua después de ~17 %. No se cuenta como aprobada.
- **Pendiente:** ejecutar el flujo GitHub Actions completo en Windows y confirmar que se genera el instalador con IA; después validar MT5 demo. No se garantiza rentabilidad futura.

## Publicación

1. Extraer el ZIP **completo** en carpeta nueva; no mezclar con versiones antiguas.
2. Ejecutar `PUBLICAR_A_GITHUB_REV4.cmd` con Git instalado y sesión autorizada.
3. El publicador solo reemplaza la rama `akira-r8-studio-rev4-20261016` si sigue en el commit `622c8ffe0932034db6cd8b3aa06325426e679159`. `main` queda intacta. No sube secretos privados.
4. Comprobar en `https://github.com/juanpablo-ordo/akira/actions` el resultado real de la compilación. No desinstalar Akira hasta obtener instalador validado.
