# Aceptación Studio Rev10 · 16.4.5

| Caso | Comportamiento esperado |
| --- | --- |
| HTTPS en Windows y EXE | Contexto explícito truststore 0.10.5 con CryptoAPI y certifi empaquetados. Conserva hostname/cadena y permite completar certificados intermedios. Prueba real con certificado confiable, hostname incorrecto y cadena no confiable. |
| Biblioteca | Conserva la URL del catálogo como clave tras redirecciones y registra la URL realmente consultada. El lote deja de mostrar ACTUALIZANDO a los 45 s. Fuentes fallidas: motivo legible y nueva consulta en una hora; referencias guardadas conservadas. No bloquea MT5. |
| CoinGlass requiere plan | Predeterminado y migración: derivados públicos BTC, OKX → Bybit → Binance, sin clave. CoinGlass solo al elegirlo expresamente. Si todos fallan se informa sin inventar disponibilidad. |
| Cobertura de derivados | Un mercado por paquete; no mezcla cantidades/historias de exchanges. Financiación, interés abierto, libro y ratios según cobertura real. No simula mapas ni liquidaciones agregadas; no atribuye derivados BTC al oro. |
| Datos defectuosos | Rechaza errores de proveedor, valores no finitos, OI no positivo, libros vacíos/cruzados y timestamps fuera de vigencia. Máximo 120 s para snapshots con fecha, 900 s para series de 5 min. El aumento de OI por sí solo no es voto alcista. |
| Exceso de consultas | Derivados públicos cada 60 s, al menos 120 s en ahorro. Máximo ocho trabajos de red en el pool. Un hilo bloqueado termina su estado visible al vencer el plazo y no se duplica mientras siga ocupado. |
| IA local lenta | Resumen explícitamente parcial de ocho indicadores por cada marco, sin eliminar un activo; salida general de hasta 140 tokens en contexto pequeño. Revisión individual con ids breves internos, conservando identidad y niveles exactos. Cálculos técnicos completos en el motor. |
| Fallos repetidos | Pausas crecientes por activo. Una clave de escenario nueva no reinicia continuamente la inferencia fallida. La solicitud manual permite reintentar. Un fallo no se transforma en aprobación. |
| Carga de IA en ahorro | Revisión general BTC/oro; individual si el usuario la exige o solicita. En equilibrado, propuestas automáticas deben ser enviables y caber en presupuesto. Las exigencias explícitas siguen bloqueando hasta tener aprobación vigente. |
| Huellas de revisión | IA general y videos educativos no invalidan circularmente su propia revisión individual. Evidencia financiera, velas, configuración o niveles cambiados siguen invalidándola. La ficha muestra el plazo real de espera/carga/inferencia. |
| YouTube | Transcripciones completas, con fuente/fecha, alimentan estudios; sus palabras alcista/bajista no votan como señal ejecutable. Contenido bloqueado o incompleto no se presenta como aprendido. |
| Confluencia AKIRA | Hipótesis H1 ≥ 0,35 en la dirección + volumen M15 ≥ 1 + RSI de recuperación, reuniendo conceptos de varias transcripciones completas. Requiere sus propias observaciones y validación, sin heredar aprobación de componentes. |
| Ventana/ciclo técnico | Resumen de investigación en memoria durante 30 s o hasta añadir una fuente; evita abrir SQLite/analizar 100 fuentes en cada tick. Ensayo del EXE con dos núcleos, 100 referencias sintéticas y 80 noticias; inferencia medida por separado. |
| Bloqueos visibles | Mercado cerrado, cotización en pausa y reconciliación conservan prioridad sobre propuestas antiguas. «Próxima consulta» aparece en minutos/horas en lugar de segundos ambiguos. |

Los límites monetarios, autorización, protección estructural y restricciones MT5 se conservan. Si el lote mínimo de una zona supera el límite, se espera otra compatible. Runners según configuración del usuario; la actualización no activa cuentas ni fuerza entradas sin señal.

La confluencia requiere comparación prospectiva con costes: 40 cierres de entrenamiento y 100 posteriores en al menos 20 días, con abstenciones y la cota de mejora existente. Una hipótesis no demuestra superioridad ni rentabilidad.

La aceptación final exige regresiones Windows sin omisiones, autocontroles gráficos del código y EXE, HTTPS y rechazo de certificados inválidos, lecturas públicas reales de biblioteca/derivados, IA real general e individual BTC/XAU con 2048 tokens, conversación e instalación limpia con respuesta del modelo incluido. No se usa una cuenta real. Disponibilidad externa refleja el equipo de prueba, no acceso perpetuo ni universal.

Capturas, archivos de cuenta, claves y sesiones privadas no se publican. La evidencia histórica conserva sus versiones. El resultado nuevo se registra en VALIDACION_STUDIO_REV10.json al finalizar. Crecimiento, rentabilidad, velocidad en la laptop del usuario y ausencia de pérdidas no se certifican mediante la suite técnica.
