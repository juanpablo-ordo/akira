# Canal oficial de actualizaciones de AKIRA

El cliente solo acepta un manifiesto Ed25519 válido y un instalador `.exe` con Authenticode válido. Si falta cualquiera de las dos identidades, el cliente falla cerrado y no descarga ni instala.

## Provisión del propietario

Antes de publicar una versión, el propietario debe crear un entorno protegido de GitHub llamado `release` y configurar, sin subirlos al repositorio:

- `AKIRA_ED25519_PRIVATE_KEY_PEM`: clave privada Ed25519 en PEM. La clave pública correspondiente se publica en `AKIRA_RELEASE_TRUST_JSON`.
- `AKIRA_AUTHENTICODE_PFX_BASE64`: certificado de firma de código `.pfx` codificado en Base64.
- `AKIRA_AUTHENTICODE_PFX_PASSWORD`: contraseña del PFX.
- Variable `AKIRA_RELEASE_TRUST_JSON`: JSON con `manifest_url`, `public_key`, `publisher`, `certificate_sha256` y `origins`.

La huella `certificate_sha256` debe ser la del certificado que firma el instalador, y `publisher` debe coincidir exactamente con su sujeto. No se debe generar un certificado autofirmado para producción ni sustituir la clave Ed25519 por otra.

## Publicación

1. Ejecutar `build-windows.yml` para el commit exacto y esperar todas las pruebas.
2. Abrir `publish-release.yml`, indicar la etiqueta (por ejemplo `v0.4.0`) y el ID de la ejecución aprobada.
3. El workflow vuelve a firmar el instalador con el certificado del propietario, genera el manifiesto firmado y publica ambos en GitHub Releases.

La compilación y el workflow de publicación son fases distintas. Hasta que se provisionen esos secretos y se publique `release_trust.json` con la identidad real, el canal permanece deliberadamente inactivo.
