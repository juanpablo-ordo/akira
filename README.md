# AKIRA 16.5.2 - Studio Rev17

Rev17 incorpora protección proporcional del capital, revisión continua de pendientes y conversación de mentor. [Descargar instalador Windows con IA incluida](https://github.com/juanpablo-ordo/akira/actions/runs/40655274399/artifacts/12802939072). Requiere iniciar sesión en GitHub y el archivo caduca el 2026-11-04.

La [ejecución Windows](https://github.com/juanpablo-ordo/akira/actions/runs/40655274399) terminó con regresiones, inferencia real, instalación limpia y actualización desde Rev15 aprobadas. La compilación corresponde a `67e71bd0ff761b2036b7f3c1baac23bd1ac0b9b6`; las actualizaciones posteriores de documentación registran la evidencia sin cambiar ese ejecutable.

En Ajustes > Riesgo, la protección limita por orden, símbolo y cartera, y pausa nuevas entradas por pérdida diaria o caída desde la referencia. También retira pendientes propias incompatibles; conserva las órdenes externas y la protección de posiciones. La vista previa muestra el menor límite efectivo. Un lote mínimo puede hacer incompatible una cuenta pequeña con un SL estructural adecuado. No se estrecha el SL para forzar actividad.

En Ajustes > IA y voz se puede elegir conversación natural, mentor o detallada y otro archivo GGUF local compatible. El motor gratuito incluido es llama.cpp. La conversación consulta el estado real mediante el actor y separa hechos confirmados de propuestas; no modifica límites ni manda operaciones por inferencia libre del modelo.

[Alcance y criterios de aceptación](ACEPTACION_REV17.md) · [Estado de verificación](VALIDACION_REV17.json)

La rama `akira-rev17-capital-mentor` ejecuta la validación de Windows y solo publica su instalador si terminan todas las comprobaciones. La verificación técnica no demuestra rentabilidad, conciencia ni inteligencia infalible. Se usan modelos previamente entrenados. Las pruebas financieras son sintéticas, sin una cuenta real, y no sustituyen una evaluación prospectiva con costes.
