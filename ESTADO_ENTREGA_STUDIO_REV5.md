# Studio Rev5 · corrección Windows 3

FIX2 está publicado pero su ejecución 24 se bloqueó durante la prueba nueva de gráficos de alto DPI, antes de crear el ejecutable. FIX3 aísla y limita esa prueba, conserva diagnósticos y retira una llamada que vuelve a procesar eventos en la decoración de Windows. La causa interna Win32 y la compilación deben confirmarse allí. Consulta `CORRECCION_WINDOWS_3.md`, `README.md` y `VERIFICACION_STUDIO_FIX3`. Publicar con `PUBLICAR_A_GITHUB_REV5.cmd`; no reejecutar el código antiguo.
