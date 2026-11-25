# Canal oficial de actualizaciones de AKIRA

## Experiencia del usuario

Una primera instalación preparada para el canal es suficiente. AKIRA busca al iniciar y cada seis horas; si falla la conexión reintenta a los quince minutos. Una versión nueva genera un aviso dentro de la aplicación y aparece en Ajustes → Actualizaciones. La descarga se puede pausar y reanudar. Al terminar se ofrece **Actualizar y reiniciar**. El ayudante espera el cierre de AKIRA, respalda sus binarios y datos, ejecuta el instalador en silencio, comprueba la nueva versión y vuelve a abrir AKIRA con el mismo perfil. Si la comprobación falla, restaura la versión anterior y sus datos.

La actualización pausa las nuevas entradas y concilia solicitudes con MT5 antes del cierre. Durante el cierre solo continúan las protecciones del bróker; la gestión de AKIRA está detenida. No se actualiza sin confirmación del usuario.

Se usa el instalador completo como paquete de actualización; todavía no hay descargas diferenciales ni un paquete que excluya el modelo. El usuario no recorre el asistente de instalación base en cada actualización.

El cliente conserva las comprobaciones originales: manifiesto Ed25519, tamaño, SHA-256, Authenticode y editor fijado. Una actualización criptográficamente válida no equivale a haber probado un instalador real: las pruebas con simulaciones se reportan por separado.

## Provisión del propietario

Antes de publicar una versión, el propietario debe crear un entorno protegido de GitHub llamado `release` y configurar, sin subirlos al repositorio:

- `AKIRA_ED25519_PRIVATE_KEY_PEM`: clave privada Ed25519 en PEM. La clave pública correspondiente se publica en `AKIRA_RELEASE_TRUST_JSON`.
- `AKIRA_AUTHENTICODE_PFX_BASE64`: certificado de firma de código `.pfx` codificado en Base64.
- `AKIRA_AUTHENTICODE_PFX_PASSWORD`: contraseña del PFX.
- Variable **del repositorio** `AKIRA_RELEASE_TRUST_JSON`: JSON público con `manifest_url`, `public_key`, `publisher`, `certificate_sha256` y `origins`. Debe estar disponible también al compilar, antes de acceder al entorno de publicación.

La huella `certificate_sha256` debe ser la del certificado que firma el instalador, y `publisher` debe coincidir exactamente con su sujeto. La compilación incorpora esa identidad pública al ejecutable; descargar otro JSON después de instalar no cambia la confianza de una versión antigua. No se debe generar un certificado autofirmado para producción ni sustituir la clave Ed25519 por otra.

El endpoint estable debe ser `https://github.com/juanpablo-ordo/akira/releases/latest/download/release.json`. Las rutas HTTPS permitidas deben contemplar `/juanpablo-ordo/akira/releases/` en `github.com` y las redirecciones reales de los activos de GitHub. Las redirecciones también se validan. La clave pública es Ed25519 de 32 bytes codificada en Base64; no se ofrece una identidad de producción ficticia en el repositorio.

El workflow actual admite un PFX del propietario. Un servicio externo gratuito como SignPath requiere aceptación del proyecto y una integración diferente para obtener el instalador firmado; esa provisión no está resuelta por este workflow. No se ha añadido una licencia MIT ni se ha solicitado una cuenta en nombre del propietario.

## Publicación

1. Para cada entrega, aumentar la versión en `akira_version.py` y en el valor automático de la rama en `build-windows.yml`; la siguiente entrega preparada es `0.4.0`. Guardar los cambios y actualizar las entradas afectadas de `PACKAGE_SHA256.json`. Cambiar el código sin aumentar la versión no genera una oferta de actualización.
2. Con la variable pública disponible, ejecutar `build-windows.yml` para el commit exacto y esperar todas las pruebas. La instalación de prueba comprueba que la identidad se incorporó al paquete.
3. Abrir `publish-release.yml` en la rama `akira-0.3-web-voz-recuperacion`, indicar `version` (por ejemplo `0.4.0`, sin prefijo `v`) y `build_run_id`. Seleccionar el mismo commit que pasó la compilación. El workflow debe estar disponible en la rama predeterminada para poder iniciarlo desde la interfaz de Actions; si no lo está, incorporar primero esa definición mediante revisión normal.
4. La publicación valida repositorio, rama, workflow, estado exitoso, commit, versión, ID de ejecución y SHA-256 del artefacto. Instala sus herramientas bloqueadas, firma el EXE y **vuelve a probar ese archivo firmado** con IA real y el canal incorporado. Regenera `VERIFICATION_REV19.json` antes de crear el manifiesto; el reporte `INSTALLED_LOCAL_AI.json` por sí solo no contiene la identidad completa de la entrega.
5. Firma el manifiesto Ed25519 y comprueba su firma y compatibilidad con el cliente. Crea `v<version>` apuntando al commit probado, adjunta instalador y manifiesto a un borrador y solo después publica como latest. Nunca sobrescribe silenciosamente una entrega anterior. Una ejecución fallida no publica una actualización.

El manifiesto vence a los treinta días. Antes de ese plazo debe publicarse una entrega nueva o implementarse un proceso de renovación firmado y revisado; no se debe ignorar la caducidad. También queda pendiente la política operativa de renovación de certificados fijados.

La compilación y el workflow de publicación son fases distintas. Sin la provisión y una primera instalación con identidad real incorporada, el canal permanece inactivo. Las instalaciones 0.3.0 compiladas sin canal necesitan una instalación manual de transición una sola vez. Después las actualizaciones se gestionan dentro de AKIRA.
