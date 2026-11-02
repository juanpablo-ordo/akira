# AKIRA Rev19 — Integración de tres módulos

Base compilada: `2334c559`. Rama aislada de integración: `akira-rev19-full-technical-adaptive-liquidity-20261102`.

## Indicadores dentro del selector

`indicator_decision.indicator_evidence()` introduce un efecto real de clasificación en `PendingPlanner.fuse_pending_context()` limitado a **±2.4 puntos**. Computa un voto por familia independiente: tendencia (Supertrend, HMA, Ichimoku), momentum (DeMarker), volumen de ticks (CMF) y estructura (FVG). Requiere M15 y H1, rechaza valores no finitos y nunca sustituye una geometría adecuada, los límites monetarios o MT5.

Solo utiliza velas cerradas ya existentes. A falta de confirmación suficiente, el ajuste es cero. Se expone el ajuste y la causa en la tesis de cada pendiente; ninguna magnitud se presenta como probabilidad calibrada.

## Estrategias adaptativas en selección operativa

El mismo clasificador de ocho regímenes usado por el planner (módulo `regime.py`) determina qué familias ya implementadas tienen prioridad, vía `adaptive_route.route()`. Regímenes de tendencia, rango, ruptura, barrido y volatilidad reciben preferencias específicas de retroceso/ruptura/runner/reversión. Una clasificación poco fiable mantiene el comportamiento previo y una estrategia manual no se reordena.

En el modo `AKIRA_ADAPTATIVA` el selector de pendientes agrega un efecto de prioridad pequeño, nunca inventa órdenes. Un runner automático claramente desaconsejado deja paso a pendientes. Un shock de noticias de alta confianza no admite exposición nueva. Los filtros existentes de `strategy_adaptation.py` con entrenamiento, holdout, cuenta y build mantienen la última palabra cuando están validados.

## CoinGlass, niveles modelados y liquidaciones agregadas

Se añadió consulta de `/api/futures/liquidation/aggregated-heatmap/model1?symbol=BTC&range=24h`, con parser de índices de precio y tiempo y límites de tamaño. Este endpoint de CoinGlass **solo está disponible para planes Professional o Enterprise**. Si no hay clave/permiso, se muestra el mapa MT5 y la causa, sin fabricar datos ni abusar de reintentos.

Las bandas CoinGlass representan **exposición apalancada modelada**, no liquidaciones realmente ejecutadas. Las liquidaciones históricas agregadas del otro endpoint se muestran por separado cuando hay datos reconocibles, sin inventar precios individuales. Para oro (XAUUSDm), y para BTC sin acceso al endpoint, se conserva el mapa **estimado por volumen de ticks del bróker**. Ninguna versión del mapa aprueba órdenes.

La fuente está integrada en `ContextWorker.jobs_for`, `ContextWorker.read`, `Engine.view` y `desktop_qt`, con envejecimiento de fuentes y estados de suscripción visibles.

## Protección y continuidad

Todos los cambios se realizaron en una rama separada; `main`, el PR de la base y las cuentas MT5 permanecen sin modificar. Los umbrales de riesgo, comprobaciones de geometría, stops/freeze, revisión neuronal seleccionada y conciliación de MT5 siguen en vigor. Este desarrollo **no promete ganancias ni nivel de acierto** y su publicación como instalador depende de la compilación CI verde.

Pruebas específicas: `tests/test_rev19_three_integrations.py`; pruebas originales: `tests/test_rev19_pdf_integral.py` y batería Windows completa.
