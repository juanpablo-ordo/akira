# Studio Rev13 · cambiar cuentas de MT5

Akira se conecta a la cuenta seleccionada en MT5. No envía a MT5 el número ni el servidor de una cuenta anterior durante la inicialización. Comprueba el número, servidor y terminal antes de construir el motor de esa cuenta.

## Cambiar a otra cuenta

1. En MT5, inicia sesión en la cuenta que quieres probar y espera a que conecte con el bróker.
2. En Akira abre **Ajustes → Operación → Usar cuenta abierta en MT5**. También está disponible desde el aviso de desconexión.
3. Akira guarda automáticamente el número, servidor y programa comprobados, conservando los límites de riesgo. El cambio queda en **Solo análisis**.
4. Comprueba que aparece MT5 conectado. Para enviar operaciones, pulsa **Activar operativa** y confirma la cuenta y el servidor que muestra el aviso.

La contraseña del bróker se introduce y se guarda en MT5. Escribir un número en Akira no inicia sesión por sí mismo.

Si tienes varias instalaciones de MT5 abiertas, selecciona el archivo terminal64.exe de la que quieres usar y repite Usar cuenta abierta en MT5. Si no has fijado una ruta, una única instalación abierta tiene prioridad sobre el programa recordado de una cuenta anterior.

## Correcciones

- Un servidor anterior ya no puede devolver el terminal a la cuenta antigua.
- El mismo número en otro servidor se trata como otra cuenta.
- Cambiar cuenta o terminal revoca la autorización anterior; los diarios permanecen separados.
- Se puede adoptar otra cuenta sin cerrar Akira, incluso tras una conexión fallida.
- La confirmación para operar incluye número y servidor y se comprueba de nuevo al guardar.
- Cerrar Akira cancela la espera de una inspección pendiente, incluso si la llamada a MT5 ya comenzó.
- La inspección fallida conserva la identidad anterior y deja las operaciones en Solo análisis.
- La interfaz conserva otros cambios del formulario mientras actualiza los campos de la cuenta detectada.

## Comprobaciones

Las pruebas de cuentas usan datos sintéticos, el controlador, actor y motor de producción. Comprueban cambios de número y servidor, distintos terminales, cierre/reapertura, diarios separados, límites conservados y ausencia de órdenes. Se ejecutan también dentro del ejecutable Windows. La biblioteca MT5 nativa se importa en Windows; no se realiza un inicio de sesión con el bróker del usuario.

Consulta el resultado efectivo en VALIDACION_REV13.json. No se presenta una simulación como validación de una sesión real ni se certifican ganancias.
