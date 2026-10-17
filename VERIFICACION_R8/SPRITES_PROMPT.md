# Sprites de estado R8

Archivo de proyecto: `assets/avatar_states/akira_r8_states.png`.
Contrato y secuencia: `assets/avatar_states/states.json`.
Generación: herramienta integrada ImageGen, con fondo transparente. Sin CLI.
Referencia visual: ilustración AKIRA_001 del catálogo existente; identidad del mismo samoyedo blanco de Akira.

Especificación final reutilizable del prompt (resumen de producción):

> Crear un único atlas de sprites pixel art transparente en una cuadrícula regular de cuatro columnas y dos filas, ocho celdas del mismo tamaño. Mantener al samoyedo blanco Akira de la referencia, su identidad tierna, proporciones, paleta y encuadre consistentes. Fila superior: reposo con ojos abiertos, párpados a medio cerrar, ojos cerrados para un parpadeo y regreso al reposo. Fila inferior: esperando mientras procesa, dormido y acurrucado al perder Internet, despertando al recuperar la conexión y escuchando con atención. Siluetas limpias, todas las orejas y patas dentro de cada celda, sin rótulos ni contadores, sin cuadrícula visible y con transparencia real. Evitar caras inquietantes o anatomía exagerada.

La secuencia de carga usa doce fases de un arco Canvas sobre el sprite de espera; no contiene texto ni crea una imagen nueva en cada fase. Los eventos de la aplicación seleccionan los estados. El reloj sólo programa el cierre de párpados, no la rotación de expresiones completas.
