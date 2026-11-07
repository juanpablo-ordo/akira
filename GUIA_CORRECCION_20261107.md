# AKIRA · Corrección 07-11-2026 · llamada y recursos

Esta corrección parte del commit `ef6473f799fca318477c65b56d1e7904e73dd200`,
que produjo el instalador anterior verificado. Conserva el motor Rev19, los
datos locales, los límites guardados y el identificador de las cohortes de aprendizaje.

## Llamada

En Chat → Voz y llamada, elige una voz instalada y pulsa **Probar voz** para
escucharla antes de iniciar. Puedes descargar otra voz y probarla después.
La demostración no abre el micrófono.

**Iniciar llamada** abre un canal de conversación hablado. Reconoce cada frase
y comienza a reproducir la respuesta por oraciones mientras se termina la generación.
No escribe tus palabras ni las respuestas de la llamada en el historial del chat.
**Interrumpir** corta la respuesta; **Silenciar**, **Reanudar** y **Finalizar llamada**
controlan el micrófono. No se aceptan acciones de trading desde este canal.

La llamada conserva contexto temporal, consulta la misma biblioteca y los
recuerdos guardados. «Recuerda que …» guarda un recuerdo explícito; puedes
consultarlo y eliminarlo desde Memoria. Al finalizar se descarta el historial
temporal de la llamada. El reconocimiento usa texto internamente, sin publicarlo.

## Rendimiento

Antes de abrir la interfaz se detectan RAM, CPU y adaptadores gráficos de Windows.
En Ajustes → Apariencia → Rendimiento se muestran los componentes y la
configuración efectiva. **Automático según componentes** activa el ajuste en
equipos de hasta 8 GB con gráficos integrados, aunque tengan más de dos núcleos.

**Ultraligero** fuerza CPU, contexto de 2048 tokens, menos efectos, fondos de
vídeo/GIF pausados y menor frecuencia de IA auxiliar. Conserva tus preferencias
visuales para poder recuperarlas. El sintetizador reutiliza la voz entre frases
y el modelo de lenguaje permanece preparado brevemente entre turnos. El perfil
no limita el ciclo de MT5 ni la supervisión de posiciones. La latencia de la IA
sigue dependiendo del procesador; no se garantiza una respuesta instantánea.

## Revisión IA y aprendizaje

El saldo flotante y el coste estimado que cambia con cada tick ya no descartan
una revisión en curso. Cambiar niveles, lote, cuenta, velas estructurales,
configuración o evidencia sí exige otra revisión. Antes de enviar, el Gateway
recalcula el riesgo, margen y restricciones del bróker con los datos actuales.
Los fallos de revisión obligatoria se reintentan entre 5 y 30 segundos; no
heredan la espera de cinco minutos de los resúmenes auxiliares.

**Estado del sistema** muestra la cola, revisión, proveedor, duración y motivo.
Una respuesta REJECT o INSUFFICIENT_DATA nunca se convierte en aprobación.
No se desactiva la revisión obligatoria ni se alteran los límites personales.

**Aprendizaje y filtros** muestra cierres, campañas con variables, entrenamiento,
prueba y modelos validados. Se guardan cierres propios confirmados por MT5,
incluidos runners completos y costes. Los modelos quedan separados por cuenta,
familia, vía, selector y versión, y se conservan al cambiar de cuenta.
Se requieren al menos 80 campañas por familia y cinco días antes de entrenar;
la validación cronológica decide si un candidato puede ajustar la selección de
pendientes. Sin evidencia suficiente se muestra **recopilando**, sin afirmar
que existe un modelo entrenado. No se reentrenan los pesos del modelo de lenguaje.

## Oro cerrado y cuenta de MT5

BTC sigue evaluándose cuando tiene sesión y cotización válidas. El oro cerrado
sigue recibiendo análisis del historial H1/H4/D1/W1 y escenarios de reapertura,
incluida la última vela del viernes que algunos terminales conservan en índice
cero. Se recupera por rango de fechas y solo se admiten intervalos ya cerrados.
Al reabrir se comprueban tick, gap, spread, estructura, riesgo y revisión IA;
un plan del fin de semana no autoriza directamente una orden.

**Adaptarse a la cuenta abierta en MT5** conecta automáticamente el historial y
capital de la cuenta seleccionada. Al cambiar de cuenta pasa a **Solo análisis**;
pulsa **Activar operativa** para autorizar esa cuenta. Conserva tus límites
personalizados y separa diarios, aprendizaje y revisiones de la cuenta anterior.
Desactivar ese ajuste mantiene la selección estricta de número y servidor.

Una segunda apertura muestra un aviso antes de iniciar interfaz, modelos o MT5.
No cierra la primera instancia ni crea otro motor de operaciones.

## Identificación del instalador

La ventana indica **Corrección 07-11-2026 · llamada y recursos**.
El archivo se denomina
`AKIRA_16_5_4_STUDIO_REV19_CORRECCION_20261107_IA_INCLUIDA.exe`.

La verificación automatizada combina regresiones del motor y la interfaz con
Whisper, Piper, una respuesta del GGUF real y el trabajador de voz del EXE de
Windows. La salida de audio de esa prueba es sintética; no demuestra el estado
del micrófono, controladores ni permisos del equipo del usuario, ni rentabilidad.
