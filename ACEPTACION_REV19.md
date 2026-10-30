# AKIRA 16.5.4 · Rev19

Estado: verificación de Windows pendiente. No presentar un instalador anterior como esta revisión.

## Correcciones y evidencias

| Área | Comportamiento implementado | Comprobación |
|---|---|---|
| Oro / MT5 | Cotización, permisos y sesión separados; recuperación UTC de velas; H1 descuenta huecos de sesión | `tests/test_market_state_rev19.py` |
| Órdenes automáticas | Revisión neuronal obligatoria de entrada, SL, TP, lote, cuenta y evidencia; vencimiento y cambios invalidan el dictamen | `tests/test_core_rev19.py`, `qa_execution_review_rev19.py` |
| Runners | Una pendiente H1 necesita invalidación H1; conserva protección y registra origen, MFE/MAE y razón | `runner_policy.py`, `COMPARACION_REV19.json` |
| Riesgo | Aritmética compartida con pantalla; regla limitante visible; pausa tras pérdidas configurable; perfiles histórico/demo/real | `risk_limits.py`, pruebas de riesgo y ajustes |
| IA | Local / nube / automático, generación comprobable, streaming, cancelación y presupuestos separados | pruebas de proveedor, `qa_conversation_rev19.py` |
| Fuentes | DNS, autenticación, cuota y timeout diferenciados; espera acotada por dominio/endpoint; YouTube fuera de trabajos automáticos | pruebas de fuentes y recuperación |
| Región | IANA, detección del sistema, formato local; UTC para velas y operaciones | pruebas DST y empaquetado `tzdata` / `tzlocal` |
| Selección | Archivo de validación incluido, sin ajuste estadístico cuando falta evidencia fuera de muestra | `selector_validation.json`, `selection_evidence.py` |
| Interfaz | Ajustes con acuse de revisión; dictamen obligatorio visible; estado real del proveedor | pruebas de interfaz y flujo del usuario |
| Instalación | Fuente, ejecutable, instalación limpia y actualización desde Rev18 | flujo Windows; pendiente hasta CI completo |

## Comparación con Rev10

Fuentes preservadas: Rev10 `201e839aea9f6aecf85f500cad4e075c9e885750` y Rev18 `de98b491fdb67ca0e207b0bca379e77da5f1df51`. El cierre estructural anterior era idéntico en ambas: utilizaba M15 para pendientes H1. La comparación reproducible ejecuta los tres códigos en intérpretes separados con las mismas velas y tiempos.

`python qa_revision_compare.py --rev10 RUTA_REV10 --rev18 RUTA_REV18 --current . --report COMPARACION_REV19.json`

Este caso funcional no simula fills, spreads ni rentabilidad. Falta el historial completo de ticks bid/ask, comisiones y decisiones de la prueba histórica referida para reconstruir su curva y comparar beneficio neto, factor de beneficio, drawdown y activación. Esas métricas quedan `NOT_EVALUATED`, sin cifras inventadas.

## Uso y límites comprobables

En Ajustes → IA elige local, proveedor externo o automático y pulsa **Comprobar proveedor**. La nube necesita un endpoint compatible, su modelo y una clave válida. Los tests automatizados de transporte externo no equivalen a una prueba con las credenciales del usuario. El modelo local incluido se prueba con generación real.

En Riesgo, la cifra efectiva usa el menor límite aplicable. Un presupuesto sin órdenes reservadas muestra uso cero; no significa que el límite guardado sea cero. La pausa por pérdidas muestra sus cierres y vencimiento. El perfil histórico nunca envía órdenes; un perfil demo no autoriza una cuenta real.

La revisión IA evalúa coherencia con datos recibidos y puede rechazar o pedir datos. No convierte una predicción en certeza. Ausencia de aprobación, datos insuficientes o permisos inválidos siguen siendo razones visibles para no abrir una orden.

No se ha operado una cuenta del usuario durante estas pruebas. La prueba de recursos limita CPU y configura el perfil Dell; no acredita rendimiento en su equipo físico. No se certifica conciencia, rentabilidad ni órdenes perfectas.
