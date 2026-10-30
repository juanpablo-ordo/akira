# Rev19 — reconstrucción verificable

Base preservada: Rev18 `de98b491fdb67ca0e207b0bca379e77da5f1df51`.
Referencia preservada: Rev10 `201e839`; fuente compilada `513adb9`.
Rama de trabajo: `akira-rev19-verifiable-core`.

No operar cuentas desde las pruebas. No confundir pruebas funcionales con validación de rentabilidad. No publicar informes privados, credenciales ni identificadores de cuentas.

## Trabajo y aceptación

- [ ] Comparación reproducible Rev10/Rev18/Rev19; mismo historial y costes. Informar datos ausentes, sin inventar la curva histórica.
- [ ] Sesión, cotización, análisis, estrategia, riesgo y ejecución independientes. Recuperación de velas UTC y huecos de sesión.
- [ ] Proveedores local/nube/automático comprobados; presupuestos independientes; veinte turnos consecutivos y recuperación de fallos.
- [ ] Salud de fuentes con DNS/HTTP/autenticación/cuota diferenciados; respaldo y esperas acotadas. YouTube fuera del proceso automático.
- [ ] Selección explicable; revisión IA obligatoria, estructurada y vinculada a geometría, volumen, evidencia y cuenta.
- [ ] Gestión runner acorde al horizonte original; registro de origen, salida, MFE/MAE y protección durante pausas de entrada.
- [ ] Riesgo efectivo único y explicado; perfiles histórico/demo/real; pausa configurable con auditoría y vencimiento visible.
- [ ] País, región, idioma y zona IANA; UTC interno y presentación configurable, con pruebas DST.
- [ ] Gateway con comprobación, idempotencia, reconciliación y trazabilidad real de estados.
- [ ] Validación del selector reproducible y sin premio para modelos no validados; evaluación cronológica por símbolo/estrategia.
- [ ] Estado compartido/versionado, ajustes acusados por motor, voz independiente, rendimiento medido.
- [ ] Pruebas completas, CI Windows, instalación limpia y actualización, artefacto final y limitaciones explícitas.

## Hallazgos iniciales del código

La antigüedad H1 se compara con 7200 s sin descontar huecos de sesión; el runner conserva el estado anterior al retornar por datos incompletos. El presupuesto de fuentes consume tiempo desde el inicio del turno, incluida la carga/inferencia. `execution_gate` etiqueta cualquier bloqueo compuesto como `BROKER_BLOCK`. La revisión individual IA sigue siendo opcional. La gestión de posiciones se omite por conectividad pública aunque MT5 pueda seguir disponible.

Estado: EN DESARROLLO. Ninguna casilla pendiente acredita una función terminada.
