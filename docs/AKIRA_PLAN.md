# Implementación del plan de AKIRA

Rama de desarrollo basada en `d6049d8b73beaa37e766ac221ecf38ca4a29f7e3` (Rev23). La compilación de referencia es [43687399503](https://github.com/juanpablo-ordo/akira/actions/runs/43687399503). Se comprobaron las 512 huellas de la fuente antes de aplicar cambios.

| Entrega prevista | Área | Archivos principales | Prueba disponible o pendiente |
| --- | --- | --- | --- |
| 0.1 | Micrófono, salida, interrupción y diagnóstico | `voice_session.py`, `desktop_qt.py` | Rutas y reanudación en pruebas. Falta monitor, audífonos y Yeti Nano con salida física. |
| 0.1 | IA local, memoria y hechos verificables | `voice_conversation.py`, `assistant_akira.py`, `web_facts.py` | Casos de consulta y memoria. Falta contrastar la pregunta del video con la llamada instalada. |
| 0.1 | Reconexión y autorización por cuenta | `mt5_connection.py`, `runtime.py`, `execution.py` | Dos identidades sintéticas y reconexión. Falta terminal nativo con dos cuentas demo. |
| 0.1 | Riesgo, margen y revisión neuronal exacta | `risk_limits.py`, `engine.py`, `execution_review.py` | Las pruebas usan valoraciones ficticias y tickets controlados. `strategy_lab.py` registra una variante de continuación bajista fuera de la operativa. Falta medirla con histórico bid/ask y costes. |
| 0.1 | Actualizador y respaldo | `release_updates.py`, `update_transaction.py` | Casos de firma inválida, fecha, versión, URL y huella. Pendientes firma de publicación, fallos de instalación y validación de versiones sucesivas. |
| 0.2 | Gráficos y niveles | `chart_indicators.py`, `market_cache.py`, `engine.py`, `desktop_qt.py` | El gráfico consume velas MT5, distingue en formación de cerradas y muestra propuesta, solicitud y confirmación. Falta verificación visual con el terminal instalado. |
| 0.2 | Informes, zona, divisa y privacidad | `operation_report.py`, `report_filter.py`, `studio_controller.py` | Casos sintéticos de PDF, Excel, JSON, saldo cero, oro cerrado, zona DST y aislamiento por cuenta en `tests/test_plan_report.py` y `tests/test_report_history_rev23.py`. Falta comparar el archivo de 12 cierres del 14/11. |
| 0.2 | PIN y Windows Hello | `privacy_guard.py`, `tools/windows_hello.cpp` | Pruebas de caducidad y persistencia de intentos. Falta diálogo nativo, bloqueo de Windows y recuperación en un equipo inscrito. |
| 0.2 | Región, idioma y recursos | `geo_preferences.py`, `studio_translations.py`, `resource_optimizer.py` | Catálogo [Unicode CLDR 48](https://github.com/unicode-org/cldr/tree/release-48/common/subdivisions). Falta cobertura completa de traducciones y medición física en los dos equipos. |
| 0.3 | Acompañante Android | `mobile_companion.py`, `mobile/` | APK técnico y pruebas del servicio. Falta prueba de red física, reactivación, marcador y borrador en un teléfono. |

## Compilación

El workflow de Windows parte de Python 3.11 x64, resuelve y guarda el conjunto de dependencias con SHA-256, instala ese conjunto, corre regresiones y construye el ejecutable y el instalador con modelo incluido. `diagnostics/requirements-windows-x64.lock` conserva el entorno exacto de la compilación. Las revisiones, huellas y licencias del modelo y los binarios vienen de los verificadores bajo `installer/` y `third_party/`. El mismo instalador que pasa la instalación y la actualización sintéticas obtiene una huella y tamaño en `VERIFICATION_REV19.json`.

La interfaz Qt recibe capturas del coordinador MT5. El modelo corre como proceso llama.cpp y la voz usa trabajadores separados. La interfaz de informe lee una captura y sus registros; nunca envía órdenes. Las pruebas y el código fuente excluyen datos privados de clientes.

El flujo de firma necesita una identidad propia de publicación, un certificado Authenticode de confianza y un alojamiento permanente que acepte el tamaño del instalador. Para una entrega estable, compilar con la configuración de confianza pública `AKIRA_RELEASE_TRUST_CONFIG`, firmar el instalador antes de validarlo, validar ese archivo y crear el manifiesto con `python tools/release_files.py manifest --help`. Conservar las claves privadas fuera del repositorio.

El código actual reúne las funciones del plan en una rama de desarrollo. Cada entrega requiere su paquete y comprobación propios.

## Móvil

Compilar con `mobile/build.ps1`, Android SDK 36 y JDK. El APK sin firma sirve como artefacto de compilación. Para instalarlo en Android se necesita una firma de prueba o de publicación.

Desde Ajustes → Aplicación → AKIRA Móvil, iniciar el servicio en la IPv4 privada de la PC, generar la invitación y copiarla en el teléfono. Confirmar el dispositivo y sus permisos en la PC. La aplicación comprueba la huella del certificado emparejado en cada petición. El marcador y el envío se terminan en las interfaces nativas de Android. El servicio no escucha hasta activarlo desde el escritorio.
