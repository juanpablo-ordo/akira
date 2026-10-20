# AKIRA 16.4.4 · Studio Rev9

Revisión de ejecución de pendientes, aprendizaje comparable y espera de IA. El instalador solo se publica tras pasar la suite completa, el ejecutable y una instalación real en Windows. Consulta [ACEPTACION_REV9.md](ACEPTACION_REV9.md).

## Cambios

- Una LIMIT cercana a su entrada se vuelve a revisar frente a un impulso contrario fuerte de dos velas M1 cerradas. La misma regla se aplica al envío y a la gestión de pendientes propias. No basta una sola vela; no modifica posiciones manuales ni su protección.
- Después de pérdidas consecutivas del mismo lado se exige una vela M15 nueva de recuperación, además de alineación M15/H1. Una media rezagada no basta para repetir una entrada.
- El historial completo sigue contando para contabilidad y controles tras pérdidas. El ranking y los modelos aprendidos usan resultados atribuidos a la misma familia, selector, versión y compilación. Los modelos antiguos quedan conservados y no se reutilizan como evidencia de la política nueva.
- La espera de IA incluye el resumen que ya ocupa el motor local y la carga de los trabajos anteriores. Conserva un límite finito. Antes de revisar se actualizan indicadores y huella de evidencia; un resultado tardío o con niveles distintos nunca autoriza una orden.
- Bitcoin y oro explican si hay propuestas compatibles con el presupuesto que aún esperan confirmación, o si las zonas evaluadas exceden el límite. El menor riesgo mostrado también incluye las propuestas que sí caben, aunque hayan fallado la comprobación de calidad.
- Las métricas del historial se reutilizan mientras no cambian sus resultados. El actor de MT5 no espera las consultas de red ni la generación de texto.
- Guía de sesión YouTube más clara y cancelable. No pide contraseñas, no abre un selector de archivos al cancelar y no promete eliminar las restricciones del proveedor.

## Instalación y alcance

Esta rama prepara Rev9; la evidencia de Rev8 incluida en el repositorio corresponde a su propia compilación. El enlace al instalador Rev9 y sus resultados se incorporan únicamente después de terminar la validación de Windows.

Una actualización conserva la configuración y los límites explícitos del usuario. Las cuentas nuevas empiezan en Solo análisis; el programa nunca activa una cuenta por su cuenta. La opción de entradas únicamente mediante pendientes sigue gestionando sus posiciones activadas como runners.

Las reproducciones financieras usan datos sintéticos y FakeMT5. Comprueban reglas y ausencia de envíos indebidos; no prueban rentabilidad. Los ensayos del modelo usan el motor local real. YouTube y CoinGlass conservan sus requisitos de acceso y sus límites. Una cuenta pequeña puede no admitir el lote mínimo de ciertas zonas de oro sin exceder su límite; Akira espera otra zona y explica el motivo.
