# AKIRA 16.4.3 · Studio Rev8

[Descargar el instalador Windows con la IA incluida](https://github.com/juanpablo-ordo/akira/actions/runs/39223750986/artifacts/12174625823) · `AKIRA_16_4_3_STUDIO_REV8_IA_INCLUIDA.exe`.

Extrae el ZIP y ejecuta el instalador. La versión que debe aparecer al abrir es **16.4.3 · Studio Rev8**. El artefacto se conserva hasta el 26 de octubre de 2026.

Comprobado en Windows: **1314 pruebas y 121 subpruebas**, cero fallos y cero omisiones; ejecutable, HTTPS, IA real de ambos activos e instalación completa. Código construido: `0aff824fd306dfb3feb1df2b771ddf34567ef868`. [Evidencia](VALIDACION_STUDIO_REV8.json).


Revisión de los avisos y del seguimiento de Bitcoin y oro mostrados en las capturas del 19 de octubre de 2026. El instalador se publica únicamente después de pasar las regresiones, el ejecutable y una instalación completa en Windows.

## Cambios de esta revisión

- Revisiones de IA independientes por activo. Un fallo de BTC deja a oro elegible y no borra su resultado válido. Cada activo conserva la fecha real de sus datos.
- Una sola inferencia auxiliar local a la vez, en una cola propia. Las revisiones exigidas o solicitadas por el usuario pueden aplazar el resumen auxiliar. Las pendientes de igual prioridad alternan entre activos.
- Pausa de los resúmenes generales contada desde su finalización: mínimo diez minutos en ahorro y tres en equilibrio. Así una consulta lenta no convierte la frecuencia programada en generación continua. Las revisiones automáticas de ideas también se espacian diez minutos en ahorro y tres en equilibrio. El actor financiero mantiene su frecuencia.
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
