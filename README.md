# AKIRA 16.4.3 · Studio Rev8

Revisión de los avisos y del seguimiento de Bitcoin y oro mostrados en las capturas del 19 de octubre de 2026. El instalador se publica únicamente después de pasar las regresiones, el ejecutable y una instalación completa en Windows.

## Cambios de esta revisión

- Revisiones de IA independientes por activo. Un fallo de BTC deja a oro elegible y no borra su resultado válido. Cada activo conserva la fecha real de sus datos.
- Una sola inferencia auxiliar local a la vez, en una cola propia. Las revisiones exigidas o solicitadas por el usuario pueden aplazar el resumen auxiliar. Las pendientes de igual prioridad alternan entre activos.
- Pausa de las revisiones auxiliares contada desde su finalización: mínimo diez minutos en ahorro y tres en equilibrio. Así una consulta lenta no convierte la frecuencia programada en generación continua. El actor financiero mantiene su frecuencia.
- Entrada del modelo ajustada al contexto realmente cargado. En el resumen se conservan todos los marcos y se identifican las omisiones; el motor técnico mantiene todos sus indicadores. Oro no recibe derivados o libros BTC como si fueran datos XAU.
- Evidencia común al principio de la solicitud y precios/horas variables después. El servidor puede reutilizar únicamente el prefijo idéntico; los precios, edades y niveles vigentes siguen viajando en cada solicitud.
- Revisión individual con plazo coherente con la carga y la inferencia. Se mantienen el control de versión y los niveles exactos: una revisión vencida no aprueba la orden.
- Oro y Bitcoin muestran su última evaluación y su motivo concreto de espera en Trading y Análisis. No se presenta una cotización como una orden enviada.
- El lector público utilizado por subtítulos y páginas usa también los certificados incluidos. Distingue un fallo de conexión/certificado de un vídeo sin subtítulos; conserva los bloqueos de acceso y sesión del proveedor.
- Un boletín oficial vacío figura como sin novedades; una referencia educativa guardada no se confunde con una cotización vieja. CoinGlass opcional no se presenta como condición para calcular el análisis de oro.

## Validación y alcance

Consulta [ACEPTACION_REV8.md](ACEPTACION_REV8.md). Los resultados de Rev7 son históricos y no certifican este instalador. La rama de pruebas de Rev8 identifica el código que se construye y los diagnósticos de la ejecución.

Las pruebas financieras usan FakeMT5 y no operan una cuenta real. Las pruebas del modelo usan el motor CPU y el GGUF oficiales, con contexto de 2.048 tokens. La inferencia sigue necesitando tiempo y recursos en una laptop pequeña; no se confunde su latencia con la frecuencia del actor de ejecución.

Las claves y los permisos de CoinGlass y YouTube siguen perteneciendo al usuario y al proveedor. No se inventan transcripciones ni se certifica rentabilidad. Falta verificar esta revisión en la laptop, con su sesión de MT5 y sus fuentes reales.
