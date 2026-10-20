# AKIRA 16.4.4 · Studio Rev9

[Descargar el instalador Windows con la IA incluida](https://github.com/juanpablo-ordo/akira/actions/runs/39366924498/artifacts/12240821934) · `AKIRA_16_4_4_STUDIO_REV9_IA_INCLUIDA.exe`.

Cierra Akira, extrae el ZIP y ejecuta el instalador. La versión que debe aparecer al abrir es **16.4.4 · Studio Rev9**. El artefacto se conserva hasta el 27 de octubre de 2026.

Comprobado en Windows: **1340 pruebas y 128 subpruebas**, cero fallos y cero omisiones; ejecutable, HTTPS, IA real de ambos activos e instalación completa. Código construido: `20df6cb7374345b20826ea2507a403153fb60599`. [Evidencia](VALIDACION_STUDIO_REV9.json).

## Cambios

- Una LIMIT cercana a su entrada se vuelve a revisar frente a un impulso contrario fuerte de dos velas M1 cerradas. La misma regla se aplica al envío y a la gestión de pendientes propias. No basta una sola vela; no modifica posiciones manuales ni su protección.
- Después de pérdidas consecutivas del mismo lado se exige una vela M15 nueva de recuperación, además de alineación M15/H1. Una media rezagada no basta para repetir una entrada.
- El historial completo sigue contando para contabilidad y controles tras pérdidas. El ranking y los modelos aprendidos usan resultados atribuidos a la misma familia, selector, versión y compilación. Los modelos antiguos quedan conservados y no se reutilizan como evidencia de la política nueva.
- La espera de IA incluye el resumen que ya ocupa el motor local y la carga de los trabajos anteriores. Conserva un límite finito. Antes de revisar se actualizan indicadores y huella de evidencia; un resultado tardío o con niveles distintos nunca autoriza una orden.
- Bitcoin y oro explican si hay propuestas compatibles con el presupuesto que aún esperan confirmación, o si las zonas evaluadas exceden el límite. El menor riesgo mostrado también incluye las propuestas que sí caben, aunque hayan fallado la comprobación de calidad.
- Las métricas del historial se reutilizan mientras no cambian sus resultados. El actor de MT5 no espera las consultas de red ni la generación de texto.
- Guía de sesión YouTube más clara y cancelable. No pide contraseñas, no abre un selector de archivos al cancelar y no promete eliminar las restricciones del proveedor.

## Instalación y alcance

La rama verificada añade los diagnósticos y esta documentación al código compilado. No cambia sus módulos, pruebas, recursos ni flujo de construcción. Los resultados de Rev8 se conservan como evidencia histórica de su propia compilación.

Una actualización conserva la configuración y los límites explícitos del usuario. Las cuentas nuevas empiezan en Solo análisis; el programa nunca activa una cuenta por su cuenta. La opción de entradas únicamente mediante pendientes sigue gestionando sus posiciones activadas como runners.

Las reproducciones financieras usan datos sintéticos y FakeMT5. Comprueban reglas y ausencia de envíos indebidos; no prueban rentabilidad. Los ensayos del modelo usan el motor local real. YouTube y CoinGlass conservan sus requisitos de acceso y sus límites. Una cuenta pequeña puede no admitir el lote mínimo de ciertas zonas de oro sin exceder su límite; Akira espera otra zona y explica el motivo.
