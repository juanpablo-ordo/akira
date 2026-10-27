# AKIRA 16.5.1 · Studio Rev16

[Descargar el instalador completo con la IA incluida](https://github.com/juanpablo-ordo/akira/actions/runs/40464092340/artifacts/12718016406)

Cierra AKIRA, extrae el ZIP descargado y ejecuta `AKIRA_16_5_1_STUDIO_REV16_IA_INCLUIDA.exe`. La actualización conserva los datos; no hace falta desinstalar ni borrar tu configuración. La descarga requiere una cuenta con acceso a este repositorio y estará disponible hasta el 3 de noviembre de 2026 a las 07:46 UTC.

La tarjeta **Riesgo por orden** muestra tu límite efectivo. El riesgo ya reservado y el presupuesto conjunto aparecen separados. **Ajustar** abre los controles y **Guardar y aplicar riesgo** permanece visible al desplazarte. Los cambios se guardan, llegan al motor y se recuperan al volver a abrir. La rueda y el touchpad recorren las páginas sin alterar importes accidentalmente.

Los controles del chat se distribuyen al reducir la ventana. Los temas breves y las historias van al modelo local; las preguntas explícitas sobre hechos mantienen la investigación. El estado refleja el análisis del motor y da prioridad al chat activo. La integración usa Qwen3 previamente entrenado; no supone entrenamiento de nuevos pesos desde cero.

Verificación Windows del código `101dbfd17ca953758d439bed2ff484b6ef96f590`:

- **1551 pruebas y 195 subpruebas aprobadas**, sin fallos ni omisiones.
- 15 respuestas completas del modelo real, además de las comprobaciones anteriores de IA.
- 24 comprobaciones del recorrido con ratón, teclado, rueda, guardado y reapertura, tanto en origen como en el ejecutable.
- Instalación limpia con respuesta de la IA instalada y 16 comprobaciones de actualización desde Rev15.
- 20 informes aprobados y 450 archivos de origen verificados mediante SHA-256.

[Ver la ejecución completa](https://github.com/juanpablo-ordo/akira/actions/runs/40464092340) · [Ver criterios y resultados](ACEPTACION_REV16.md) · [Ver evidencia íntegra](VALIDACION_REV16.json)

La política Dell de 8 GB se probó con dos CPU disponibles en CI, sin medir la laptop física. Con el modelo activo, aplicación y modelo alcanzaron 2768.5 MiB y 66.9% de esas dos CPU; la primera respuesta generada comenzó a los 57.157 s. No se afirma conversación instantánea. Los límites y una imprecisión matemática observada se detallan en la aceptación. Las pruebas de operaciones usan FakeMT5 y no acreditan ganancias.

El instalador compilado corresponde al commit indicado. Los documentos de resultados se actualizan después de completar sus pruebas; esa actualización no cambia el código de la aplicación.
