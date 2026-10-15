# AKIRA 16.3.4 R7

Código completo de la corrección de IA local, fuentes y expresiones. El código ha superado la verificación local R7. Todavía no se ha compilado ni probado el instalador R7 en Windows.

Para crear el instalador, copia **todo el contenido** de este ZIP en la raíz de tu repositorio `akira`, incluyendo `.github`, `assets`, `installer`, `tests` y `third_party`. Conserva los datos de usuario fuera del repositorio. En GitHub Desktop haz Commit y Push. Después abre Actions → AKIRA Windows - verificar y compilar → Run workflow.

Cuando termine correctamente, descarga el artefacto `AKIRA-16.3.4-R7-IA-fuentes-expresiones-instalador-Windows-IA-INCLUIDA`. Ejecuta `AKIRA_16_3_4_R7_IA_INCLUIDA.exe` y comprueba que la ventana muestra 16.3.4 R7. El ZIP de código no instala ni actualiza por sí solo la aplicación.

La compilación anterior #11, de R6, verificó instalación y una respuesta visible de la IA en Windows. Eso corrige el modelo eliminado por el instalador anterior; no prueba los cambios R7. La compilación R7 debe pasar de nuevo la instalación completa y la respuesta de su propio modelo instalado antes de publicar el EXE.

Cambios de esta entrega:

- IA incluida en el instalador con SHA-256 verificado. Chat e investigación comparten un único supervisor; las revisiones de pendientes despiertan el modelo cuando se libera de memoria y recuperan la ruta del motor incluido en lugar del antiguo puerto de Ollama. Se conserva el modelo instalado y el motor CPU de respaldo. Se recuperan rutas antiguas o vacías desde la ubicación real de AKIRA.exe. El registro `IA_LOCAL.log` conserva la salida del proceso. Reparar solo confirma disponibilidad después de una respuesta visible real.
- Ajustes → IA / INTERNET → ACCESO A FUENTES contiene campos enmascarados para CoinGlass y YouTube Data API. Los campos vacíos conservan claves anteriores. Windows protege las claves con DPAPI. CoinGlass directo es opcional; para oro no se presentan derivados BTC como datos XAU.
- YouTube incluye Deno oficial verificado y los componentes EJS compatibles con yt-dlp. Se puede importar una sesión mediante un archivo Netscape seleccionado por el usuario. Akira no lee perfiles de navegadores. YouTube puede exigir sesión, limitar consultas o no ofrecer subtítulos; esos estados no se cuentan como videos aprendidos. Una clave Data API permite búsquedas, pero no garantiza acceso a subtítulos.
- La IA textual incluida puede analizar subtítulos completos sin descargar imágenes para un modelo visual que no está instalado. La interfaz distingue análisis textual, parcial y visual muestreado. No afirma haber visto cada fotograma.
- Se conservan las 108 ilustraciones originales basadas en las referencias del usuario. Barra lateral, operaciones, chat y llamada comparten la misma cara. Hay transiciones breves; la variación durante el habla usa el nivel del audio reproducido. No es sincronización fonética. Se retira el botón superior duplicado de chat.
- Las transcripciones completas alimentan hipótesis finitas y citadas: dirección H1, volumen M15 y extensión RSI. Cada filtro observa las mismas candidatas válidas que la estrategia base, con bid/ask, comisiones estimadas y rechazo de huecos de datos. Requiere 40 cierres de entrenamiento y al menos 100 posteriores en 20 días distintos, comparación conservadora por días, suficientes entradas aceptadas/rechazadas y resultado neto positivo. Sin evidencia suficiente se conserva la selección base. Solo se aplica un filtro por familia, símbolo y dirección. Los cambios de cuenta, configuración, versión o costes separan los estudios. Los filtros no cambian lotes, Entry, SL, TP ni gestión, y por sí solos no cancelan pendientes vigentes.

El Directorio de estrategias → VER APRENDIZAJE muestra fuentes, reglas, tamaños de muestra, comparación y filtros aplicables. Las variantes geométricas anteriores del laboratorio siguen siendo experimentos sin activación automática. Aprender una fuente no demuestra rentabilidad ni garantiza mejores operaciones.

La comprobación local no equivale a probar el PC del usuario, ejecutar órdenes reales ni demostrar beneficios. Los informes R6 se conservan como antecedentes; los resultados de esta revisión se guardan en VERIFICACION_R7.

La conexión a GitHub permite leer, pero devuelve 403 al crear la rama de esta revisión. R7 se entrega en este ZIP y aún no está publicado en el repositorio. En Actions, una ejecución nueva de este código mostrará el nombre «AKIRA 16.3.4 R7 · IA incluida». Repetir una ejecución antigua usa el código de su commit antiguo.

Verificación local final: 1.094 pruebas pytest y 83 subpruebas; 1.091 pruebas unittest con la red bloqueada, sin fallos, errores ni omisiones; autocontrol nativo v7; 108 celdas distintas; 24 combinaciones de pantalla. También se comprobó conservación de pendientes con una muestra de cotizaciones aportadas por el usuario. Las cifras no son métricas de acierto ni de rentabilidad.
