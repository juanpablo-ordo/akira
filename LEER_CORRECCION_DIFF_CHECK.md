# AKIRA - Corrección del publicador de Git para Windows

Este paquete corrige el error **Git falló (2): ... diff --cached --check**.

Se quitaron los espacios al final en `desktop.py`, una línea en blanco de más al final del archivo de prueba `tests/test_v134_runners.py` y se normalizó el CSV `REQUISITOS_232_ESTADO.csv` a saltos de línea LF, sin cambiar su contenido. El publicador ya no intenta subir `*.patch` (artefactos de difusión) y usa `core.whitespace=cr-at-eol` al revisar los archivos para aceptar CRLF legítimos de Windows sin permitir espacios sobrantes. Si encuentra un problema auténtico, muestra el archivo y la línea.

## Aplicación rápida (no necesitas reextraer todo)

1. Descomprime este ZIP pequeño.
2. Copia `PUBLICAR_A_GITHUB_REV4.ps1`, `desktop.py`, `REQUISITOS_232_ESTADO.csv` y la carpeta `tests` a tu carpeta de Akira previamente extraída, reemplazando los archivos del mismo nombre. **Mantén la estructura de carpetas.**
3. Ejecuta el `PUBLICAR_A_GITHUB_REV4.cmd` que ya tienes. El script solo trabaja en un clon temporal de la rama `akira-r8-studio-rev4-20261016`; no modifica `main` ni tus claves privadas.

Alternativa: extrae el ZIP de 25 MB `AKIRA_R8_STUDIO_REV4_DASHBOARD_PUBLICACION_CORREGIDA.zip` a una carpeta nueva y ejecuta su `PUBLICAR_A_GITHUB_REV4.cmd`.

**La reparación se validó con `git diff --cached --check` contra un árbol de Git local.** No afirma que GitHub ya compiló el instalador de Windows ni que el resultado sea apto para trading real.
