# AKIRA Rev19 — Cobertura técnica de la especificación PDF (1 noviembre 2026)

Base: rama verificada `akira-rev19-safe-repair-20261101` (commit `bcf0538`). Cambios de esta revisión en `akira-rev19-integral-pdf-20261101`. No se incluyeron informes privados, contraseñas, cuentas o tickets reales.

## Contrato de entrega

La aplicación conserva restricciones monetarias, propiedad de tickets, anti-duplicados y comprobación MT5; este código no envía órdenes reales fuera del modo autorizado. Un test sintético no acredita rentabilidad, aceptación futura del bróker ni que una pérdida pasada fuera evitable. Mantener el PR separado de la rama estable.

### P0: prioridad de protección, confirmación y decisiones

- `engine.py`: ejecutar supervisión de posiciones ANTES de actualización de investigación o revisión de noticias.
- `position_manager.py`: auditoría por ticket de bid/ask ejecutable, spread, R actual, MFE observado, SL/TP actuales, estado de protección y fallos de comprobación; diario persistente.
- `default_config.json`: perfiles **nuevos** con BE de ensayo 0.95R, trailing 1.4R y espera mínima conservada en 60 segundos (ajustable). Todos son hipótesis, no óptimos demostrados.
- `studio_settings_qt.py`: controles explícitos de umbral, ATR, espera, frecuencia de modificación, horizonte y política de TP; previsualización de umbrales de protección absurda. Preferencias antiguas no se reemplazan.
- `execution.py`: comprobaciones existentes de identidad del ticket, cotización reciente, stops/freeze, `order_check`, `order_send` y conciliación antes de declarar protegido. No se anulan.
- `incident_replay.py`: auditoría read-only de exportaciones; no inventa ticks ni confirma hipótesis contrafácticas.

### P0: revisión IA y seguridad

- `execution.review_policy`: `required` de manera predeterminada = aprobación neuronal exacta o nueva entrada bloqueada; `technical` como elección explícita de usuario = evaluación determinista sin llamarla IA. El Gateway siempre valida precios/riesgo/MT5; la protección existente no depende del modelo.
- Los controles de riesgo y de exposición combinada continúan activos en ambos modos.

### P1: indicador, adaptación y mapa

- `technical_indicator_extensions.py`: SMA, WMA, HMA, Ichimoku, SAR, Supertrend, ZigZag confirmado, Donchian, Keltner, Chandelier, Chaikin Money Flow y AD, DeMarker, pivotes tradicionales/Fibonacci, FVG y POC de ticks **estimado**. Se alimentan exclusivamente de velas MT5 cerradas.
- Los nuevos indicadores se muestran explícitamente como **contexto**: no añaden votos correlacionados ni aprueban operaciones por sí solos. El motor existente incluye EMA, ADX, RSI, MACD, MFI, VWAP, ROC, ATR, bandas, swings, barridos, BOS y otros. No se afirma equivalencia con fuentes externas o TA-Lib sin prueba de referencia.
- `market_regime.py`: tendencia, rango, posible reversión confirmada, expansión, datos insuficientes, cierre; etiqueta hipótesis sin afirmar retorno rentable. La validación prospectiva y holdout de `strategy_adaptation.py` conserva sus umbrales propios.
- `liquidation_heatmap.py`: bandas comparables de intensidad actual/histórica de precio y volumen de ticks del bróker, nunca liquidaciones de derivados inventadas. No participa en autorización de entradas. Panel visible en Análisis.

### P1/P2: datos, UI, avisos, modelo, persistencia y paquete

- Se conserva la corrección previa de recuperación H1/mercado cerrado, escritor único de `pending_research.json` con lock y reintentos y canales de investigación con timeout. Revisar DNS y proveedores desde diagnóstico por fuente, no desde una bandera general.
- `activity_event_schema.py` + `execution.Reporter`: cada evento incluye identidad, hora UTC, categoría, severidad, símbolo, ticket opcional, acción, detalles, correlación y confirmación MT5. Eventos sin operación (datos/protección/errores) también se muestran.
- `studio_controller.py`: aviso persistente deduplicado por configuración incompatible o fallo reciente de mejora de SL. No silencia pérdidas ni rechazos.
- Se conservan el procesamiento en workers, llama.cpp+GGUF y las pruebas de conversación, hardware limitado, instalación/upgrade desde Rev18 y SHA del empaquetado en la CI Windows.

## Matriz de aceptación (distinguir código, CI y ensayo humano)

| Caso | Incorporación funcional | Verificación humana todavía necesaria |
|---|---|---|
| T01 Oro histórico | Análisis forense reproducible de archivo exportado, MFE real observado, vacíos de evidencia explícitos | Tick-by-tick + cotizaciones y retcodes reales para contrafáctico; no afirmar pérdida evitable |
| T02 BE/SLTP | Umbrales configurables, progreso sin pivote; Gateway rechaza ampliar SL, confirma por snapshot | Exness demo, stops/freeze, spread extremo, costes, reapertura y gap |
| T03 Reinicio | Diario persistente, reconciliación de intents y datos de posición (infraestructura ya existente) | Reinicio brusco y restauración en la Dell/MT5 real |
| T04 Cierre/gap | Barras cerradas, conservación de SL servidor, diagnóstico de sesión | Apertura con spread, rollover, cierre/festivos |
| T05 IA | Fail closed requerida, modo técnico explícito, sin falsa aprobación neuronal | Proveedor real intermitente, timeout y cambios de geometría |
| T06 Rendimiento de señales | Selección adaptativa con entrenamiento/holdout prospectivo y candidatos por régimen descriptivo | Walk-forward con datos históricos/ticks de calidad y comisiones |
| T07 Internet/DNS | Recuperación y fallbacks ya existentes, señales separadas de MT5 | Desconectar/reconectar Internet y MT5 de forma independiente |
| T08 Escritura | Temporales únicos, lock interproceso e intraproceso; test de 1000 escrituras | Cortes durante replace y reinicio real |
| T09 Actividad | Categorías idénticas, esquema auditable, avisos de SL | Confirmar visualmente cada pestaña y ticket |
| T10 Modelo | GGUF/llama.cpp incluido en el flujo Windows base | 20 turnos y recursos en laptop real |
| T11 Indicadores | Valores de referencia simples y contrato contexto-only | Más series de referencia, sensibilidad por régimen y contribución medida |
| T12 Instalación | Pipeline Windows de build, empaquetado, inferencia, upgrade, hash y artefacto | Instalar y probar en PC del usuario |

**Regla de publicación:** publicar instalador solo si todas las comprobaciones automáticas CI terminan en verde. No fusionar ni declarar rentabilidad comprobada por ello. El usuario hará los ensayos de demo y experiencia tras instalar.
