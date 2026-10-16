# AKIRA R8 Studio Rev4 — fuente completa + estabilización de CI Windows

## Qué incluye
- Código fuente completo R8 Studio Rev4 y recursos del proyecto.
- Validación de pendientes y runners existente (sin activar cuenta real).
- Preparación de Tcl/Tk y comprobación SHA256.
- Nuevo ejecutor `ci_windows_tests.py`: **38 casos gráficos recopilados**, cada uno en su propio intérprete Python y, en Windows CI, con copia privada completa de Tcl/Tk.
- Ejecuta también el resto de la suite de regresión. No omite los 38 casos: los registra individualmente y falla ante errores y saltos.
- Genera informes JUnit por caso y un manifiesto de pruebas en `diagnostics`.

## Publicar y compilar
1. Extrae este ZIP en una carpeta nueva. **No borres ni desinstales Akira actual.**
2. Ejecuta `PUBLICAR_A_GITHUB_REV4.cmd` desde esa carpeta. Git debe estar instalado y autenticado.
3. El publicador clona la rama existente `akira-r8-studio-rev4-20261016`, comprueba su versión exacta, excluye datos privados y sube el código completo mediante un commit. No toca `main`, ni usa `push --force`.
4. Revisa https://github.com/juanpablo-ordo/akira/actions para saber si la ejecución de Windows se completa.
5. Si pasa, descarga el **instalador** únicamente de la sección Artifacts del run exitoso. El ZIP de este chat es código fuente, no es un instalador `.exe`.

## Limitaciones, importantes
El último error registrado en GitHub era intermitente al abrir la segunda ventana de una misma clase: Tcl no podía leer `menu.tcl` durante un conjunto de pruebas GUI en el mismo proceso. La separación por **caso**, y no solo por módulo, ataca esa interferencia y utiliza bibliotecas privadas verificadas. **Esto todavía debe confirmarse en Windows Actions**. No se garantiza que resuelva futuros errores de compilación.
No se ha demostrado rentabilidad, no se ha validado Exness demo durante seis horas y siguen pendientes requisitos visuales y de IA del documento maestro. No ejecutar en real hasta validar el instalador y las órdenes con MT5 demo.

Si GitHub responde con un commit distinto del esperado, el publicador se detiene para conservar los cambios remotos.
