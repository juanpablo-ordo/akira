# Verificación Studio Rev7 · 16.4.2

Código de aplicación construido: `6070db2184476e325b186d71d8dcbddbc7b5a054`.

Los archivos Linux documentan la comprobación del código fuente. Los informes Windows se incorporan únicamente cuando finaliza la instalación real y se comprueba la IA instalada. El artefacto y la ejecución exactos se identifican en `VALIDACION_STUDIO_REV7.json`.

## Qué se comprueba

- HTTPS real con certificado válido, nombre incorrecto y raíz desconocida. Las dos últimas conexiones deben rechazarse.
- Modelo gestionado descubierto después de un estado negativo anterior al arranque, tanto en chat como en investigación.
- Recortes individuales, anclaje, limpieza de la expresión anterior, parpadeo y reutilización de imagen durante el redimensionado.
- Cola individual atendida antes del planificador de trabajo auxiliar; precios vigentes y actor financiero activo cada 0,2 segundos en el ensayo.
- Interfaz con afinidad de dos núcleos, datos en movimiento y ventanas visible y minimizada.
- Modelo Qwen3-4B real: revisión de ambos activos en contexto de 2.048 tokens y perfil de ahorro.
- Conversación con errores de escritura, seguimiento, cambio de tema y una ficha de noticias sintética identificada como tal.
- Instalador terminado: archivos propios, SHA-256 del modelo, ocho páginas, reconocimiento visual y respuesta generada con el modelo que acaba de instalar.

## Alcance

Los ensayos usan datos financieros sintéticos y FakeMT5; no envían órdenes a una cuenta real. La medición de CPU del ejecutable no incluye generación de texto del modelo. El tiempo del modelo se informa aparte. No se extrapolan estos valores a la laptop del usuario ni se certifican rentabilidad, micrófonos físicos, todos los monitores o coincidencia visual exacta de todos los diálogos.

En ahorro se resume la entrada del modelo y se espacian a diez minutos las revisiones auxiliares. El análisis técnico conserva sus cálculos, los requisitos de revisión individual se respetan y los controles de riesgo permanecen activos.

La suite no omite pruebas gráficas. La recuperación de lectura Tcl sólo actúa sobre una fuente seleccionada que existe y puede leerse; los errores reales siguen deteniendo la validación.
