# AKIRA 16.4.7 · Studio Rev12 · Reconexión MT5

Esta revisión corrige la conexión y recuperación de la cuenta al cerrar y reabrir Akira. Conserva la protección de runners, conversación, informes y límites de la Rev11.

## Fallos corregidos

- La inicialización de MT5 no recibía `expected_login`: MT5 elegía su última cuenta en lugar de solicitar la guardada en Akira.
- Los ajustes guardados mientras el motor estaba desconectado no llegaban a su copia de configuración.
- La espera de arranque era de 10 segundos y algunas excepciones terminaban el actor en lugar de reintentar.
- La interfaz ocultaba el motivo y podía mostrar «Operativa autorizada» mientras esperaba MT5.

Ahora se solicita la cuenta guardada, se recuerda el terminal y servidor previamente comprobados, se admite hasta 60 segundos de inicio y se reintenta con espera controlada. Los cambios hechos mientras se conecta se revisan antes de permitir el primer ciclo. El cierre libera el controlador; la reconexión conserva una pausa manual. Los pedidos de órdenes recibidos sin conexión se rechazan: no se acumulan para enviarse después.

La interfaz muestra el motivo, el siguiente paso y Reconectar MT5. Ajustes → Operación permite seleccionar el programa de MT5 sin escribir su ruta. No se muestran cuentas disponibles ni importes inventados cuando MT5 no responde.

## Comprobación con la cuenta demo del usuario

1. Abre MT5 e inicia sesión en tu demo. MT5 debe recordar los datos de esa cuenta; introducir solo su número en Akira no sustituye la contraseña y servidor guardados en MT5.
2. En Ajustes → Operación comprueba la cuenta guardada y pulsa Guardar ajustes. Si usas varios MT5, selecciona su `terminal64.exe`. Pulsa Reconectar MT5 y espera el resultado.
3. Debe aparecer «MT5 conectado · cuenta demo» en Ajustes y el balance recibido en Cuenta. Cierra y reabre Akira y comprueba que se recuperen sin volver a introducir la cuenta.
4. Para autorizar operaciones usa el modo y confirmación de cuenta ya existentes. Conectar no activa por sí solo la operativa. Los límites, margen, permisos del bróker y comprobaciones de identidad siguen vigentes.

## Validación y límites

`tests/test_studio_rev12_mt5_reconnect.py` cubre cuenta y ruta persistentes, arranque, excepciones, tiempo de espera, cambios de ajustes durante la conexión, recuperación, pausa, bloqueo de otra cuenta, aislamiento del hilo financiero y presentación Qt.

`qa_mt5_reconnect_rev12.py` usa el actor y motor de producción con un bróker sintético: abre, cierra, vuelve a conectar, recibe BTC y oro, simula desconexión y tiempo agotado y rechaza otra cuenta. La comprobación se ejecuta dentro del autocontrol de origen y del ejecutable. En Windows también importa la biblioteca MT5 nativa empaquetada. No inicia sesión en la cuenta del usuario ni coloca operaciones reales.

El resultado completo Windows, las cifras y el instalador se registran en `VALIDACION_REV12.json` cuando termine el workflow. Los registros históricos de Rev11 conservan su identidad original y no certifican esta compilación. Ninguna prueba sintética garantiza conexión con un bróker concreto ni rentabilidad.
