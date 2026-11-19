# AKIRA 0.3 — revisión de la grabación del 18/11/2026

Fuente: grabación de escritorio facilitada por el usuario y comentarios que la
acompañan. Esta lista **no** certifica pruebas en sus dispositivos ni beneficios.

## Cambios codificados
- Visualización del estado: red neuronal de puntos y enlaces transparentes, con
  colores configurados, en vez del sprite negro. El avatar clásico se mantiene
  sólo para compatibilidad de recursos anteriores; no ocupa el área principal.
- Ondas del motor: widget Qt nativo con barras de color según estados; cadencia
  de 32 ms, sin imágenes externas. El medidor del micrófono usa la amplitud
  realmente informada por el dispositivo y cambia de color con el tema.
- Inicio: desaparece el recuadro duplicado de alertas; sigue el botón de
  campana y los filtros del registro; se reduce la altura en ausencia de eventos.
- Privacidad: PIN desbloquea todos los valores durante la sesión; se bloquea
  manualmente, al cerrar/reiniciar, o al cambiar la identidad de MT5. Se
  elimina el bloqueo por inactividad de 25 segundos. **Precaución: compartir
  pantalla con sesión desbloqueada mostrará datos**.
- Análisis: todos los indicadores numéricos realmente presentes por
  temporalidad, sin inventar valores; motivos con etiquetas comprensibles.
- Fuentes: CoinGlass eliminado de futuras consultas y de la interfaz.
  Derivados públicos sin CoinGlass continúan; YouTube queda opcional.
- Voz: botones compactos con nombres accesibles, velocidad y volumen de cambio
  inmediato para la siguiente frase; interpolación completa antes de reproducir.
- Referencia educativa aportada: https://www.youtube.com/live/e2v18afjSa8
  (identificador `e2v18afjSa8`). Sólo se acepta una transcripción completa
  verificada por el importador. Aun recibida, el contenido es una hipótesis,
  no una señal automática ni una promesa de rentabilidad.

## Criterios pendientes y límites
- Micrófonos, voz, WASAPI, altavoces, dos monitores, imágenes sin fondo negro,
  tiempo entre cuadros, FPS al desplazarse: **verificación física pendiente**.
- Red del usuario, historial y resultados verdaderos en Exness MT5 demo:
  **no han sido verificados aquí**.
- La caída reportada de 69 a 58 USD merece auditoría de tickets, lotes, motivos,
  SL y costes. No puede achacarse a un módulo sin examinar esas operaciones.
- **No es posible prometer acierto, beneficio, ausencia de pérdidas ni aprovechar
  cada caída o subida.** Requiere backtests sin sesgo de futuro, costes reales,
  walk-forward y prueba demo antes de cambios de ejecución en vivo.
