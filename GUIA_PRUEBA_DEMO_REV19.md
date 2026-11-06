# AKIRA Rev19: prueba en una cuenta demo

Esta configuración es para experimentar con una cuenta **demo**, con límites de
riesgo muy amplios. Puede agotar su saldo rápidamente. No garantiza operaciones,
ganancias ni protección del saldo.

## 1. Operación

En **Ajustes → Operación**:

- Comprueba en MT5 que la cuenta conectada sea demo y selecciona
  **DEMO · Experimentación controlada** como perfil.
- Selecciona **Operativa automática**, guarda y pulsa **Activar operativa**
  para autorizar la cuenta conectada.
- Activa Bitcoin y/u oro según lo que quieras probar. Para permitir entradas
  runner directas, deja desactivado **Entradas únicamente mediante pendientes**
  y activa **Gestionar runners normales**.
- La opción **Motor técnico · sin dictamen neuronal** evita esperar la aprobación
  de IA previa; las reglas técnicas y las comprobaciones de MT5 siguen vigentes.
  Elige esa opción solo si quieres hacer la prueba sin esa revisión previa.

## 2. Riesgo

En **Ajustes → Riesgo**, para la prueba demo con el mayor margen que ofrece la
interfaz existente:

| Ajuste | Valor |
| --- | --- |
| Proteger el capital de esta cuenta | Desactivado |
| Tope por orden en dinero | 100 000 000 USD |
| Tope por orden sobre el patrimonio | 100 % |
| Parte del capital disponible para riesgo | 100 % |
| Tope adicional del presupuesto en dinero | 0 USD |
| Pérdida máxima del día en dinero | 0 USD |
| Pérdida máxima del día en porcentaje | 0 % |
| Nivel mínimo de margen | 1 % |
| Riesgo runner: % del límite por operación | 100 % |
| Pausa tras pérdida de runner | 60 segundos |
| Tope de pérdidas runner en 24 h | 3 veces el límite general |

Pulsa **Guardar y aplicar riesgo** y comprueba que el motor indique que los
ajustes se aplicaron. El valor cero tiene significados distintos según el campo:
en el tope adicional del presupuesto y los dos topes diarios, desactiva ese tope
en particular. En los dos topes por orden, cero no habilita una orden.

Al desactivar la protección de capital también se desactivan sus topes
protegidos, su pausa por racha, su ventana FOMC y su límite de una posición por
símbolo. No cambia la gestión de SL, breakeven o trailing. La regla propia de
runner de una posición por símbolo sigue existiendo.

Por ejemplo, con un patrimonio de 29 USD y un tope por orden del 6 %, el límite
porcentual es 1,74 USD aunque el límite monetario sea 100 millones. Una candidata
con pérdida estimada de 2,86 USD no cabe en ese límite. El patrimonio real y las
reservas pueden cambiar entre capturas y se calculan con los datos de MT5.

## Límites que continúan

No existe un ajuste en esta revisión que quite **todos** los bloqueos de riesgo
en cualquier circunstancia. Aunque los porcentajes estén al máximo, el riesgo
por orden sigue limitado al patrimonio y el riesgo conjunto al menor entre el
balance y el patrimonio, menos las reservas. Una pérdida acumulada en runners
o la pausa mínima tras una pérdida también pueden detener runners directos.

Además, Akira y MT5 exigen conexión, margen, volumen y niveles válidos; la
estrategia debe encontrar y aprobar una entrada. El bróker puede rechazar una
orden incluso si los topes de Akira la permiten. El stop loss y la ejecución no
garantizan que la pérdida real sea exactamente la estimada.
