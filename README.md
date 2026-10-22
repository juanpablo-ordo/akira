# AKIRA 16.4.7 · Studio Rev12

Corrección de la reconexión MT5 y la cuenta demo al cerrar y reabrir Akira. Incluye los cambios de runners, conversación, informes y rendimiento de Studio Rev11.

En MT5, inicia sesión en tu demo y guarda allí sus datos. En **Ajustes → Operación** de Akira guarda el número de cuenta y, si usas varios MT5, selecciona su `terminal64.exe`. **Reconectar MT5** usa esos ajustes y comprueba la cuenta antes de continuar. La cuenta conectada y el motivo de cualquier fallo aparecen en la pantalla.

No es necesario volver a escribir los ajustes al reabrir. La conexión conserva la cuenta y terminal comprobados, el modo elegido y los límites de riesgo. Una cuenta distinta queda bloqueada. Conectar no autoriza operaciones por sí solo.

La compilación Windows verifica las regresiones, el ejecutable gráfico, cierre/reapertura del motor, importación de MT5, fuentes HTTPS, IA real incluida, recursos y la instalación completa. Consulta el estado efectivo en [VALIDACION_REV12.json](VALIDACION_REV12.json). No se certifica rentabilidad ni una sesión real del equipo del usuario.

[Instrucciones y comprobaciones](ACEPTACION_REV12.md) · [Cambios previos de runners, chat y consumo](ACEPTACION_REV11.md)
