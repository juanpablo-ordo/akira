# Aceptación Studio Rev9 · 16.4.4

Esta revisión convierte los problemas observados en comprobaciones reproducibles. No se publica información de cuentas, órdenes, claves, sesiones ni archivos privados recibidos del usuario. Los nuevos escenarios son sintéticos, simétricos y escalables a Bitcoin y oro.

| Caso | Comportamiento comprobado |
| --- | --- |
| LIMIT esperando cerca de un impulso contrario | Dos M1 contiguas y cerradas; cuerpos de al menos 0,25 ATR, proporción cuerpo/rango 0,55, desplazamiento conjunto de al menos 1,15 ATR y medio riesgo inicial; último cierre próximo al extremo y a la entrada. No se usan velas futuras. |
| Retirada de pendiente propia | Misma comprobación que para entradas; confirmación sobre dos cotizaciones distintas y reglas de MT5 antes de retirar. Se conservan las órdenes externas y las posiciones. |
| Una vela, datos viejos, huecos o rechazo ya observado | No crean una invalidación nueva por impulso. Las invalidaciones estructurales existentes siguen vigentes. |
| Reentrada tras pérdidas consecutivas | Una M15 completa posterior al cierre, tendencia M15/H1 alineada y cuerpo de recuperación de al menos 0,20 ATR M15. |
| Historial anterior sin tesis o con otras versiones | Se conserva para contabilidad y controles tras pérdidas; se excluye de las métricas comparables y de los nuevos modelos aprendidos. |
| Modelo aprendido de otra familia, selector, build o cuenta | No modifica el ranking. Los modelos nuevos mantienen separación cronológica y costes, y deben superar los criterios previos de promoción. |
| Revisión individual detrás de un resumen | Se incluye el tiempo del motor ocupado y sus trabajos anteriores; cola local con límite de 900 s. El plazo de ejecución se cuenta aparte y el estado visible usa el mismo presupuesto acotado. |
| Indicadores cambiados durante la espera | Se usan los actuales y se cambia la huella; la aprobación anterior no se reutiliza. Una sesión cerrada o cotización caducada no inicia esa revisión. |
| Dos activos con claves de escenario iguales | Las comprobaciones de entrada se conservan por símbolo y clave. Una comprobación antigua de otro símbolo no se acepta. |
| Propuestas baratas bloqueadas por calidad | Cuentan en el mínimo observado y se explica su condición de espera. No se presenta la primera propuesta cara como único motivo de bloqueo. |
| Ninguna zona de oro cabe en el presupuesto | Se muestran el menor riesgo observado y el límite. No se sube el riesgo ni se estrecha la protección para fabricar actividad. |
| YouTube | Guía de archivo .txt Netscape, finalidad opcional, privacidad y límites; cancelar no abre archivos. Importación y transcripción completa mantienen sus validaciones previas. |

La regla de impulso es un filtro de ejecución; su efecto sobre ganancias, entradas omitidas y drawdown necesita evaluación prospectiva en demo. Estos umbrales son relativos al ATR y a la geometría, no a precios o tickets de la cuenta recibida. Una reproducción sintética no demuestra que el broker hubiera aceptado una cancelación concreta antes del fill.

La validación de entrega exige la suite completa sin omisiones en Windows, pruebas gráficas del código y del EXE, HTTPS verificado, ensayo de dos núcleos, IA real general e individual BTC/XAU con contexto de 2048 tokens, conversación y una instalación limpia con respuesta de su propio modelo. No se envían órdenes a una cuenta real durante esos ensayos.

La latencia de inferencia y el consumo en una laptop concreta deben medirse por separado del tiempo del actor financiero. No se certifica crecimiento de cuenta, una ganancia diaria fija ni ausencia de futuras pérdidas. Las referencias históricas y los archivos de validación Rev8 conservan su identidad y no certifican Rev9.
