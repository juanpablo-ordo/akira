# AKIRA Rev4 — corrección del publicador completo

El ZIP anterior sí incluía `akira_secrets.py`. El script de publicación verificaba erróneamente que este archivo *hubiera cambiado*. Git no marca como modificado un archivo que ya existe con contenido idéntico en el repositorio.

## Qué se corrigió

- El publicador ahora exige el módulo `akira_secrets.py` en la carpeta original y en el clon temporal.
- Confirma con `git ls-files --error-unmatch` que el módulo forma parte del índice del repositorio, aunque no haya sido modificado.
- Mantiene el bloqueo de `AKIRA_SECRETS.json`, `.env`, bases de datos y claves privadas.
- Conserva la comprobación del commit esperado antes de publicar, sin tocar `main`.
- Se agregó `tests/test_rev4_publisher_integrity.py` para reproducir exactamente el caso de un archivo intacto que Git no incluye en la lista de cambios.

## Instrucciones

1. Extraer este ZIP completo a **una carpeta nueva**. No combinar archivos con paquetes anteriores.
2. Ejecutar `PUBLICAR_A_GITHUB_REV4.cmd`. Requiere Git para Windows y la sesión de GitHub autorizada.
3. El publicador actualizará **solo** `akira-r8-studio-rev4-20261016`, si la rama conserva el commit esperado.
4. Revisar GitHub Actions para el instalador. No desinstalar la versión actual ni activar una cuenta real.

La corrección elimina el **falso error de ausencia del módulo**, pero no certifica que la suite Windows o el instalador terminen correctamente.
