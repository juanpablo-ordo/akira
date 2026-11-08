# AKIRA 16.5.4 · corrección 22

Instalador: `AKIRA_16_5_4_STUDIO_REV22_20261108_IA_INCLUIDA.exe`.
La identificación histórica del motor sigue siendo REV19 para conservar la
compatibilidad de diarios y aprendizaje. La ventana muestra «Revisión 22».

## Qué comprobar al abrir

1. Cerrar la ventana anterior e instalar la actualización. El instalador conserva
   la configuración. Una segunda apertura accidental muestra el aviso antes de
   cargar Qt, la IA o MT5.
2. En Ajustes → Operación, usar la cuenta abierta de MT5. Al cambiar de cuenta,
   verificar su identidad y activar la operativa para esa cuenta.
3. En el inicio, «Cobertura de mercado» muestra el plan de oro incluso durante el
   cierre: si está preparado, el rango observado y la próxima sesión; si faltan
   velas, lo dice. Al abrir se recalculan las candidatas con cotización vigente.
4. «Estado del motor» informa el contexto, hilos CPU y capas solicitadas en GPU
   del proceso que realmente está ejecutándose, y cualquier recuperación en CPU.
   Una tarjeta de 16 GB admite descarga completa del modelo pequeño a GPU; las
   tarjetas de 8 GB conservan margen con descarga parcial. La disponibilidad real
   de Vulkan sigue dependiendo del controlador; el respaldo CPU queda visible.
5. Probar la voz antes de iniciar la llamada. Seleccionar micrófono y salida
   correctos; la barra indica entrada de audio. La conversación es hablada y no
   se copia al chat. Un error permanece visible aunque vuelva a escuchar.
6. Para memoria persistente, decir «Recuerda que…». El contexto de la llamada se
   conserva durante esa llamada. El panel de aprendizaje distingue recopilación
   de cierres y modelos validados; no afirma entrenar el modelo de lenguaje.

## Parámetros para experimentar con una cuenta demo

Estos valores permiten comprobar el motor con límites de capital amplios. Pueden
consumir la cuenta demo. No son una configuración que demuestre rentabilidad.
Seleccionar primero **Perfil de cuenta → DEMO · Experimentación controlada**:
este perfil rechaza nuevas órdenes si MT5 identifica una cuenta real.

| Ajuste | Valor para la prueba solicitada |
|---|---|
| Proteger el capital de esta cuenta | Desactivado |
| Pausar nuevas entradas tras pérdidas consecutivas | Desactivado |
| Evitar entradas alrededor de anuncios FOMC | Desactivado |
| Tope por orden en dinero | 100.000.000 |
| Tope por orden sobre el patrimonio | 100% |
| Parte del capital disponible para riesgo | 100% |
| Tope adicional del presupuesto en dinero | 0 |
| Pérdida máxima del día en dinero | 0 |
| Pérdida máxima del día en porcentaje | 0 |
| Nivel mínimo de margen configurado por AKIRA | 0 |
| Riesgo runner: % del límite por operación | 100% |

Guardar y aplicar riesgo. El límite efectivo aparece calculado sobre la cuenta
actual: con 50 de patrimonio, 6% solo permite arriesgar 3 por orden, aunque el
tope monetario sea enorme. Con 100% permite hasta 50 antes de descontar reservas.
**Cero en el tope por orden bloquea entradas**; cero en el tope adicional de
presupuesto o pérdida diaria desactiva solo ese tope, como indica cada control.

Estas opciones no desactivan las reglas técnicas ni las pausas específicas de
runners: tienen sus propios controles y un mínimo de pausa de 60 segundos tras
una pérdida. El margen del bróker, lote mínimo, cotizaciones, mercado abierto,
geometría SL/TP, posiciones existentes y confirmación de envío siguen siendo
necesarios. No hay parámetros que garanticen operar bajo toda circunstancia.

Para comprobar el dictamen neuronal, dejar «Revisión previa a nuevas órdenes» en
**IA obligatoria**. Si se elige explícitamente «Motor técnico», la aprobación
neuronal deja de exigirse, pero la interfaz lo identifica como decisión técnica.
No se presenta una decisión técnica como aprobación de la IA. La corrección
repara el arranque del modelo; no cambia esa elección automáticamente.

## Evidencia de ejecución y recuperación

Una candidata no equivale a una orden. Pendientes muestra la decisión y el motivo;
solo un ticket confirmado por MT5 se cuenta como envío. Ante una desconexión, el
motor vuelve a consultar el estado del bróker antes de repetir una solicitud.
Las fuentes públicas pueden fallar sin significar que MT5 esté desconectado.
El diagnóstico incluye el servidor propio, generación real confirmada y estado
de las revisiones; el informe conserva las decisiones y resultados de la cuenta.
