# AKIRA 16.4.6 · Studio Rev11

Esta revisión protege el capital de las runners directas, da prioridad a pendientes y solicita protección de avance en posiciones propias cuando alcanzan el umbral R, aunque falte un pivote M15. Conserva SL/TP y controles del bróker. El chat distingue preguntas personales de investigación, mantiene el hilo y responde preguntas directas sin cargar el modelo. PDF, Excel y JSON separan solicitud, colocación y apertura de cada orden.

La validación del instalador de esta revisión se publica en [Actions de la rama Rev11](https://github.com/juanpablo-ordo/akira/actions/workflows/build-windows.yml?query=branch%3Aakira-studio-rev11-20261020). Usa el artefacto **instalador-Windows-IA-INCLUIDA** de una ejecución correcta. El artefacto «build-no-es-instalador» no incluye todos los componentes para instalar.

Para equipos modestos: Ajustes → Rendimiento → Ahorro de energía. La IA incluida sigue necesitando memoria al conversar; no se promete ejecución instantánea ni rentabilidad. Consulta [criterios y límites de Rev11](ACEPTACION_REV11.md).

## Historial de Rev10

[Descargar el instalador Windows con la IA incluida](https://github.com/juanpablo-ordo/akira/actions/runs/39397248037/artifacts/12253483233) · `AKIRA_16_4_5_STUDIO_REV10_IA_INCLUIDA.exe`.

Cierra Akira, extrae el ZIP y ejecuta el instalador. Al abrir debe aparecer **16.4.5 · Studio Rev10**. El artefacto se conserva hasta el 27 de octubre de 2026.

Verificado en Windows: **1371 pruebas y 134 subpruebas**, sin fallos ni omisiones; incluye 31 casos nuevos. También pasaron el EXE, HTTPS, lecturas públicas reales, modelo real BTC/XAU e instalación limpia con respuesta de su propia IA. [Resultados y hashes](VALIDACION_STUDIO_REV10.json) · [Flujo completado](https://github.com/juanpablo-ordo/akira/actions/runs/39397248037).

## Cambios

- HTTPS con el verificador nativo de Windows y certificados empaquetados. Biblioteca con caché correcta tras redirecciones, plazo finito y motivos legibles. Las referencias guardadas conservan su fecha.
- Derivados públicos BTC de OKX, Bybit o Binance como opción predeterminada; CoinGlass opcional. La prueba del EXE obtuvo financiación, interés abierto, libro y proporción de cuentas compradoras/vendedoras desde OKX, sin clave. Se indica la cobertura: no se simulan liquidaciones agregadas ni sus mapas, ni derivados del oro.
- Resumen y respuesta de IA más pequeños. En ahorro se mantienen análisis técnico y revisión general; las individuales se reservan para solicitudes o exigencias del usuario. Fallos repetidos generan pausas crecientes por activo y un estado finito.
- Opiniones de YouTube como material educativo para estudios. Nueva hipótesis de confluencia H1, volumen M15 y RSI con evaluación independiente; no se activa como combinación no validada.
- Menos lecturas de disco en el ciclo técnico. Próxima consulta en minutos/horas. Mercado cerrado, cotización en pausa y reconciliación conservan prioridad sobre propuestas antiguas.

## Mediciones y alcance

Con el modelo real, CPU de dos hilos y contexto de 2048 tokens, el resumen de BTC/oro tardó **53,812 s** y las revisiones individuales **32,016/29,625 s**. No son tiempos de colocación de órdenes: la generación de texto se ejecuta fuera del actor financiero.

En el ensayo financiero sintético del EXE, con dos núcleos, 100 referencias y 80 noticias, ahorro registró **4,88 % de CPU**, **24,1 ms de ciclo p95** y 40 ciclos con cotización actual. No se generaba texto durante ese ensayo. El resultado depende del equipo; no se presenta como medición de la laptop del usuario ni como consumo máximo durante inferencia.

Una actualización conserva límites y decisiones de ejecución. Las cuentas nuevas empiezan en Solo análisis. Runners según configuración del usuario. Si el lote mínimo de una zona de oro supera su límite con la protección estructural, se espera otra zona compatible; no se aumenta el riesgo para fabricar actividad.

Las pruebas financieras utilizan datos sintéticos y FakeMT5, sin órdenes a una cuenta real. No certifican crecimiento, rentabilidad, ausencia de pérdidas ni disponibilidad perpetua de proveedores. Una hipótesis de estrategia debe superar sus propias observaciones prospectivas con costes antes de intervenir en la selección de operaciones.

[Criterios de aceptación](ACEPTACION_REV10.md). Código compilado: `513adb97af05071fe2050f9327c0e5fd7ac0a2d9`. Esta rama verificada añade solo documentación y evidencia al programa probado. Las capturas y los archivos privados del usuario no se publican. La evidencia histórica Rev9 conserva su identidad.
