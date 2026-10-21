# Verificación Studio Rev8 · 16.4.3

Código de aplicación construido: `0aff824fd306dfb3feb1df2b771ddf34567ef868`.

Ejecución de Windows: [39223750986](https://github.com/juanpablo-ordo/akira/actions/runs/39223750986). Resultado: **1314 pruebas y 121 subpruebas**, cero fallos, cero errores y cero omisiones. El instalador exacto y su caducidad se identifican en `../VALIDACION_STUDIO_REV8.json`.

Los informes Windows comprueban las ocho pantallas, la actividad visible de BTC y oro, la conexión HTTPS de noticias y del lector público de subtítulos, dos núcleos, revisiones generales e individuales con Qwen3-4B y contexto de 2.048 tokens, conversación y una instalación limpia que responde con su propio modelo. Un error, una revisión vencida o un dato ausente nunca se convierte en permiso de ejecución.

Los informes Linux son selecciones de apoyo durante el desarrollo; se solapan y sus cantidades no se suman. `LINUX_TEST_SCOPES.json` detalla cada selección. La suite completa de Windows certifica el código final.

Todos los datos financieros de estos ensayos son sintéticos. No se usa una cuenta real ni se envían órdenes. La medición del cliente con dos núcleos no incluye generación de texto; la latencia del modelo se registra aparte. No se extrapolan estos tiempos a la laptop ni al broker, y no se certifica rentabilidad.

Una fuente sin publicaciones, un proveedor que requiere acceso y un vídeo sin subtítulos tienen estados distintos. No se inventan datos ni transcripciones. CoinGlass opcional no se convierte en requisito para calcular el análisis de oro.
