# Criterios de aceptación de AKIRA en Windows

**Este documento no certifica una instalación, ni equivale a la compilación.**

## Instalador único e identidad
- Pantalla de bienvenida inicial, con el logo definitivo del Samoyedo pixel art apoyado sobre un huesito con AKIRA, sin collar ni aro.
- Dos acciones claras: **Instalar** y **Cancelar**. El proceso NO inicia automáticamente antes de pulsar Instalar.
- Apariencia consistente con toda la app: azul marino, cian discreto, dibujo clásico sencillo y legible.
- Progreso sobrio por etapas: preparando, instalando aplicación, configurando IA, verificando y listo. Sin imprimir lista de megabytes o cada fichero.
- Trabajo en segundo plano y eventos de progreso en la interfaz principal para que Windows no marque la ventana como «No responde».
- Cancelar solicita confirmación, interrumpe el trabajador, cierra los procesos propios, elimina sus archivos parciales y no deja servicios ocultos. Si la conexión se interrumpe *sin* Cancelar, reintentar con verificación de integridad.
- Descargar binarios oficiales `llama-server.exe` y modelo Qwen3 4B GGUF con integridad verificada, comprobar inicio y respuesta de la IA. No afirmar que están instalados si la respuesta local falla.
- Instalar la aplicación compilada como AKIRA.exe (sin depender de abrir `.py` o un CMD) en ruta de usuario estable, con accesos directos e icono personalizados.
- Si hubo una versión previa, preservar estado, chats, diarios y riesgo; validar la nueva antes de retirar la anterior. Si el usuario pide desinstalación completa, mostrar confirmación aparte para borrar todos los datos propios. Nunca borrar MT5, Python global ni archivos de terceros.
- Proporcionar **registro resumido** para uso normal y diagnóstico ampliado solo si existe un error. Al terminar: botón **Iniciar Akira**.

## Motor financiero y evidencia
- Solo BTCUSDm y XAUUSDm. Pendientes, sin scalp.
- No recrear ni cancelar constantemente pendientes válidas. Invalidación real y riesgo mínimo de 0.01 lot prevalecen sobre la obligación de operar.
- Aprendizaje de resultados reales etiquetados, separado de hipótesis extraídas de videos, páginas y titulares. Ninguna fuente web cambia directamente lotaje ni envía operaciones.
- Analizar múltiples traders/canales; guardar fecha, autor, transcripción consultada y si hubo evidencia completa. Reconocer contradicciones; probar hipótesis con datos Bid/Ask, spread, comisiones, entrenamiento fuera de muestra y demo.
- La actualidad de las noticias de BTC/oro depende de la conectividad y la fecha real de cada fuente; no simular actualidad.

## Experiencia de usuario y llamada
- Mantener los diez PNG sencillos basados en el logo original; estados de reposo, parpadeo, hablar, pensar, analizar, alegría, alerta y dormir, sin render 3D/VRAM pesada.
- En llamada: escuchar/reconocer, pensar, hablar, interrupción, silencio, error, finalización. Mantener estados sincronizados con la sesión, ignorar eventos de una sesión anterior.
- Optimizar de arranque, perfiles con ajustes visibles, scroll correcto sobre notificaciones; no dejar modelos locales residentes innecesariamente.

## Puertas de salida obligatorias
1. Compilar y ejecutar el `.exe` en Windows 10/11, desde un PC limpio y otro con instalaciones anteriores.
2. Verificar botón Instalar, Cancelar durante descarga, durante desempaquetado, rollback, cancelación repetida, y reparación.
3. Comprobar que el modelo real responde; medir CPU, RAM, VRAM, y que no haya proceso huérfano al cerrar.
4. Comprobar llamada con micrófono real y 10 cambios de expresión correctos.
5. Conectar MT5 demo; no ejecutar real hasta auditar cancelaciones, SL, TP y riesgos.

**No declarar «FINAL» si falta alguna puerta.**
