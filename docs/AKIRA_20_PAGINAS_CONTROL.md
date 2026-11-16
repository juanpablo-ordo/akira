# AKIRA · Control de aceptación del PDF (20 páginas)

Base reproducible: Rev23 `d6049d8b73beaa37e766ac221ecf38ca4a29f7e3`.
El PDF exige entregas **acumulativas**: 0.1 fiabilidad, 0.2 interfaz e informes y
0.3 móvil. Una prueba sintética no equivale a una prueba en hardware real.
No llamar "final" a una compilación de desarrollo sin todos los criterios de
la página 19, firma de publicación y pruebas en equipos físicos.

| Página | Requisito concreto | Código / comprobación | Estado de aceptación |
| --- | --- | --- | --- |
| 3 | Rev23, copia de datos demo, eventos inmutables y casos del video | `akira_version.py`, `runtime.py`, `tests/` | Base y CI disponibles; falta ensayo con cuenta demo y material exacto del video |
| 4 | Micrófono/salida correctos; Yeti, WASAPI, interrupción | `voice_session.py`, `desktop_qt.py` | Pruebas automatizadas; pendiente escucha física y desconexión |
| 5 | LLM local, Zelda, memoria, continuidad y recuperación | `assistant_akira.py`, `voice_conversation.py`, `chat_store.py` | Pruebas de diálogo real en CI; faltan métricas comparadas en dos equipos |
| 6 | Noticias actuales, fuentes fechadas, fallos de escritura y sin API de pago | `web_facts.py`, `knowledge_update.py` | Ruta de fuentes disponible; falta contraste exacto video/fecha sin red |
| 7 | Teléfono cifrado, emparejamiento, WoL, web, SMS, llamada y permisos | `mobile_companion.py`, `mobile/` | Implementación y CI Android en desarrollo; falta teléfono real |
| 8 | Detección MT5, identidad por cuenta y vista unificada | `mt5_connection.py`, `desktop_qt.py` | Vista unificada y pruebas sintéticas; falta cambio demo-real físico |
| 9 | Límite 0.5 % de patrimonio, lote, SL, reservas y margen exacto | `risk_limits.py`, `execution.py`, `risk_reservations.py` | Pruebas de cálculo; falta rechazos reales demo MT5 |
| 10 | Estrategia aplicada, dictamen obligatorio, runners y ventas en estudio | `execution_review.py`, `strategy_lab.py` | Dictamen probado; hipótesis bajista bloqueada para aplicación en vivo |
| 11 | Gráficos de MT5, datos frescos, pendientes y auditoría | `chart_indicators.py`, `desktop_qt.py`, `operation_report.py` | Pruebas de modelo; falta auditoría visual contra MT5 |
| 12 | Optimización automática 8 GB y RTX 5060 Ti, recursos medidos | `resource_optimizer.py`, `akira_model_runtime.py` | Políticas y simulación; sin mediciones físicas en ambos equipos |
| 13 | Avatar original, sin importador activo, pestañeo y sprites sin salto | `studio_widgets.py`, `desktop_qt.py` | Regresiones de Qt; falta captura de 60 FPS y DPI 100/150/200 % |
| 14 | UI traducible, CLDR, zona, números y ventanas en dos monitores | `studio_translations.py`, `geo_preferences.py`, `desktop_qt.py` | Parcial: traducciones abiertas y pruebas físicas de dos pantallas |
| 15 | PIN, Windows Hello, DPAPI y exportaciones ocultas | `privacy_guard.py`, `akira_secrets.py` | Pruebas de bloqueo; falta sesión Windows inscrita y pantalla compartida |
| 16 | Informes con instantánea única, filtros y datos fieles PDF/XLSX | `operation_report.py`, `report_filter.py` | Pruebas sintéticas; falta comparar los 12 cierres originales del 14/11 |
| 17 | 0.1→0.2→0.3, canal firmado, Authenticode y rollback | `release_updates.py`, `update_transaction.py` | Código de validación; falta identidad de firma y publicación estable |
| 18 | Windows EXE+instalador, ZIP fuente, SHA, pruebas de instalación | `build_windows.py`, `installer/`, `tools/source_archive.py`, GitHub Actions | ZIP de fuentes y instalador se empaquetan por separado desde el mismo commit después de la comprobación; falta publicación firmada permanente |
| 19 | Aceptación integral física, demo, rendimiento, voz, móvil y privacidad | `tests/`, `qa_*.py` | **NO APROBADO** hasta pruebas con hardware y evidencias reales |
| 20 | Preguntas abiertas: runners, Android, canal y firma | `docs/AKIRA_PLAN.md` | Android elegido; firma y dominios del canal requieren titular |

**Reglas de cierre**: No forzar entradas para aparentar actividad. No afirmar
rentabilidad sin muestra fuera de entrenamiento. Nunca hacer pasar un APK de
pruebas (firmado temporalmente) por publicación Android estable. Un `0.3.0`
compilado con CI es candidato, no producto aprobado hasta superar la página 19.
