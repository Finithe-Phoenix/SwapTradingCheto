# Hoja de ruta hacia un laboratorio cuantitativo avanzado

Revisión: 7 de septiembre de 2026. Base auditada: versión 0.2.0, commit `4c91d81e29114b40642bd11555ab221a0cf0faed`.

Este documento describe trabajo pendiente. Sus módulos, objetivos y criterios de aceptación no se presentan como funciones ya implementadas. Se mantiene el alcance BTC/ETH spot, simulación y ausencia de promoción automática a dinero real.

## Objetivo del siguiente salto

Construir una plataforma que pueda explicar y reproducir cada decisión, medir la incertidumbre de sus resultados y recuperarse de fallos conservando la contabilidad y el riesgo. La calidad técnica y la evidencia económica se evaluarán por separado: publicar una versión funcional no acredita que una estrategia sea rentable.

La base actual dispone de un motor causal, controles de cartera, datos verificables, reportes y una integración de paper trading. La validación publicada registra 65 pruebas locales y cuatro trabajos de CI correctos. La evaluación real sigue limitada a diez operaciones en un tramo continuo; no se ha completado desarrollo 2020–2023 ni iniciado observación prospectiva prolongada. [Evidencia de 0.2.0](VALIDATION.md).

## Hallazgos que determinan la prioridad

| Hallazgo | Evidencia revisada | Trabajo necesario |
|---|---|---|
| Stop de respaldo demasiado amplio | El adaptador declara `stoploss = -0.99`. Si faltan `fixed_stop` y la vela de entrada, su recuperación puede lanzar una excepción. | Probar ese fallo con el motor nativo y establecer una protección explícita; no considerar protegida una posición cuyo stop no esté verificado. |
| Frescura de valoración incompleta | Un ticker sin timestamp pasa la comprobación de edad actual. | Registrar tiempo de recepción y procedencia, definir frescura verificable y comportamiento cuando no pueda acreditarse. |
| Reservas de entrada transitorias | Las reservas viven en memoria y vencen a los 120 segundos. | Reconciliar intención, orden, fill y posición tras reinicios; demostrar ausencia de compras duplicadas ante eventos repetidos. |
| Histórico amplio incompleto | Se observaron 60 horas ausentes por activo en 20 intervalos. | Contrastar archivos oficiales, clasificar huecos y definir una política causal de interrupciones. |
| Evidencia económica pequeña | Diez operaciones; fallan muestra y sensibilidad del bootstrap. | Completar desarrollo y validación temporal con registro de todas las variantes y límites de incertidumbre. |
| Operación continua sin demostrar | Hay Docker, logs y señal de estado; falta un ensayo prolongado. | Pruebas de interrupción, restauración real de respaldos y seguimiento prospectivo. |

Los tres primeros son hallazgos de revisión de código, no incidentes observados con fondos. En Freqtrade 2026.8 instalado se comprobó que una excepción de `custom_stoploss` puede devolver `None` a través de su wrapper, y que el motor inicializa el stop con el valor de la estrategia si todavía no existe. Falta el ensayo integrado de esa combinación de fallos. La documentación describe el contrato del [stop personalizado](https://www.freqtrade.io/en/stable/strategy-callbacks/#custom-stoploss).

## Entregas ordenadas y definición de terminado

| Entrega propuesta | Resultado que debe quedar utilizable | Criterio de aceptación |
|---|---|---|
| **0.2.1 — Protección y recuperación** | Stop recuperable, valoración con frescura explícita y reconciliación de órdenes simuladas. | Los escenarios de metadata ausente, callback fallido, evento repetido y reinicio no restablecen riesgo ni duplican exposición. Una posición sin protección válida queda identificada y activa la ruta de contingencia probada. |
| **0.3 — Datos e interrupciones** | Archivo bruto versionado, contraste REST/archivo, catálogo de huecos y replay con política de disponibilidad. | Cada intervalo tiene procedencia y estado de calidad. Los periodos no verificables no se ejecutan como si tuvieran precios observados. El informe cuantifica cobertura, incertidumbre y exclusiones. |
| **0.4 — Investigación reproducible** | Registro de experimentos, validación cronológica, estabilidad del calentamiento y comparación con Freqtrade. | Resultados repetibles a partir de configuración, datos, código y dependencias fijados; diferencias de señales y contabilidad explicadas. Todas las variantes quedan registradas. |
| **0.5 — Aplicación del laboratorio** | API propia y panel web para datos, experimentos, decisiones, riesgo y estado operativo. | Navegar desde una cifra hasta sus operaciones y velas de origen; comparar experimentos compatibles; mostrar correctamente errores, ausencia de datos y estados vencidos. |
| **0.6 — Operación verificable** | Proceso de paper trading supervisado, telemetría, respaldos, restauración y simulación de fallos. | Recuperar el último estado consistente, reconciliar operaciones y conservar pausas tras cada fallo de la matriz publicada. Registro explícito de los intervalos sin servicio. |
| **0.7 — Asistencia y modelos evaluados** | Copiloto de investigación y, si la evidencia lo justifica, modelos candidatos de contexto de mercado. | Cada afirmación numérica enlaza un cálculo reproducible. Cada modelo supera una referencia sencilla en datos posteriores al entrenamiento y se evalúa incluyendo costes y riesgo. |
| **1.0 — Laboratorio validado** | Un tercero puede instalar, reproducir, auditar y recuperar el sistema usando su documentación. | Se cumplen las pruebas técnicas anteriores y se publica una decisión económica independiente: ampliar muestra, continuar paper, modificar o descartar. La versión 1.0 no habilita trading real. |

Las versiones expresan orden de trabajo. No se asigna una fecha de rentabilidad ni se comprime la observación de mercado para ajustarla a un sprint.

## 0.2.1: primer bloque ejecutable

| ID | Trabajo | Prueba de aceptación |
|---|---|---|
| RISK-01 | Definir el contrato de protección inicial y recuperación de `fixed_stop`. | Inyectar pérdida de metadata, historia no disponible y error en `order_filled` usando callbacks reales. Ningún resultado silencioso presenta la posición como protegida por ATR. |
| RISK-02 | Diseñar la contingencia de salida y sus estados operativos. | La ausencia de datos bloquea entradas; las salidas no se inventan a precios vencidos. Se conserva el último stop válido y se documenta qué ocurre si tampoco existe. |
| RISK-03 | Incorporar edad y calidad de cada valoración. | Tickers vencidos, sin edad acreditable y con reloj desajustado producen el estado definido por contrato y una razón observable. |
| EXEC-01 | Persistir o reconstruir reservas desde órdenes y posiciones. | Reiniciar antes y después de un fill, y repetir su evento, produce la misma exposición y contabilidad final dentro de la precisión declarada. |
| OPS-01 | Probar restauración de las dos bases del mismo experimento. | Un respaldo coherente restaura pausas; una combinación incompatible se detecta y bloquea admisiones. |

La política de contingencia se especificará antes de implementarla y se comprobará en simulación. Un stop sigue sujeto a disponibilidad y ejecución; el criterio técnico no promete una pérdida máxima garantizada.

## 0.3: tratamiento de los huecos

Consultar los archivos diarios/mensuales oficiales del mismo mercado y verificar sus checksums. Son otro canal de distribución de Binance; no constituyen por sí mismos una fuente independiente ni garantizan que aparezcan velas ausentes. Binance también documenta que sus archivos pueden corregirse posteriormente y que los timestamps spot del archivo cambian a microsegundos desde enero de 2025. El importador necesitará conversión explícita por formato; el contrato REST actual no se reutilizará a ciegas. [Binance Public Data](https://github.com/binance/binance-public-data).

La política propuesta deberá distinguir recuperación verificable, interrupción confirmada y ausencia de causa desconocida. Para cada caso definirá admisión de entradas, continuidad de indicadores, valoración informativa y evaluación del stop al reaparecer una cotización válida. Los datos brutos se conservarán junto a las transformaciones, la incertidumbre y la versión de la política. La imposibilidad de reconstruir un intervalo se declarará en el resultado de la etapa.

Los precios de otro exchange podrán servir para contraste externo, identificados como otro mercado. No reemplazarán automáticamente los fills o la liquidez histórica de Binance.

## 0.4: investigación que permita tomar decisiones

La separación temporal vigente continúa: desarrollo 2020–2023, validación 2024–2025 y prueba final reservada enero–agosto de 2026. Cualquier nueva hipótesis se declara con sus parámetros, número de variantes, métricas y regla de evaluación antes de mirar su resultado. Volver a ajustar usando un periodo evaluado cambia su papel dentro de la evidencia.

El registro de experimentos guardará identificación, hipótesis, padre, hashes, dependencias, semilla, etapa, universo, política de datos, costes y resultado, incluyendo intentos fallidos. La validación móvil sobre desarrollo usará ventanas sucesivas; cualquier entrenamiento utilizará exclusivamente su pasado. Se tratarán explícitamente las posiciones que atraviesen fronteras temporales.

Se medirán expectativa neta, incertidumbre, drawdown y duración, concentración de beneficio por activo/periodo, exposición, sensibilidad a costes y retrasos y estabilidad de parámetros cercanos. Los filtros actuales seguirán siendo diagnósticos, no certificados de rentabilidad. Una muestra de cien operaciones es un objetivo de revisión, no un tamaño universal suficiente.

Se añadirán ensayos nativos de [anticipación de información](https://www.freqtrade.io/en/stable/lookahead-analysis/) y [dependencia del calentamiento](https://www.freqtrade.io/en/stable/recursive-analysis/), documentando su cobertura y limitaciones. La comparación entre motores separará señales, dimensionamiento, fills, costes y valoración; no exigirá igualdad de P&L entre modelos de ejecución distintos.

## 0.5: arquitectura y experiencia de uso propuestas

| Componente | Elección inicial propuesta | Propósito |
|---|---|---|
| Núcleo cuantitativo | Python y contratos compartidos | Mantener una definición comprobable de señal, riesgo y eventos. |
| Consulta histórica | Parquet + DuckDB | Consultar rangos y variables sin cargar repetidamente todo el histórico; medir memoria y duración frente al lector actual. |
| API del laboratorio | FastAPI | Exponer experimentos, estados e informes mediante contratos tipados y OpenAPI. |
| Panel | Angular | Interfaz coherente con navegación entre datos, decisiones, riesgo e investigación. |
| Trabajos largos | Procesos de trabajo separados de la API | Ejecutar, cancelar y reanudar experimentos con identificadores persistentes. |
| Estado operativo | Conservar SQLite en el bot; evaluar PostgreSQL para el servicio compartido | Evolucionar almacenamiento cuando exista concurrencia de trabajos/usuarios y una migración verificable. |
| Observabilidad | OpenTelemetry con un destino de métricas/logs elegido al implementar | Relacionar un evento de mercado con señal, decisión de riesgo y resultado de ejecución. |
| Despliegue inicial | Docker Compose en un equipo definido | Entorno reproducible con costes, recursos y recuperación medidos. |

Estas son decisiones propuestas, sujetas a una prueba pequeña de compatibilidad y rendimiento antes de introducir dependencias. Referencias primarias: [DuckDB y Parquet](https://duckdb.org/docs/current/data/parquet/overview), [FastAPI](https://fastapi.tiangolo.com/), [Angular](https://angular.dev/overview) y [OpenTelemetry](https://opentelemetry.io/docs/what-is-opentelemetry/).

El panel tendrá cinco recorridos: estado de la cartera simulada; salud/cobertura de datos; experimentos comparables; explicación de cada entrada o rechazo; y recuperación/incidentes. Desde el móvil se podrán revisar esos estados con texto legible y estados de error explícitos. La primera API del panel consultará el bot y solicitará trabajos de investigación; no incorporará controles de trading real.

## 0.6: operación y despliegue

Definir una matriz de fallos: red interrumpida, respuestas duplicadas o atrasadas, proceso terminado, disco lleno, SQLite bloqueado, corrupción de snapshot y reinicio durante un fill. Registrar el efecto sobre posiciones, órdenes, riesgo y decisiones. El registro conservará identificadores que permitan reconstruir el orden causal y detectar diferencias contables.

Medir tiempo hasta detectar cada fallo, tiempo hasta recuperar un estado consistente, antigüedad de cotizaciones, cola de trabajos y recursos. Los objetivos operativos se fijarán sobre una máquina de referencia y se distinguirán de la disponibilidad del exchange. Una copia de seguridad se considerará validada después de restaurarla y conciliarla.

La observación prospectiva empieza tras cerrar los hallazgos de protección y recuperación. La primera revisión seguirá siendo a las 4–8 semanas; se ampliará si la muestra es pequeña. CI no sustituye al equipo que ejecuta el bot. La selección del equipo y su coste se evaluarán cuando el proceso esté listo; esta hoja de ruta no contrata infraestructura.

## 0.7: uso concreto de inteligencia artificial

El primer copiloto consultará resultados existentes: explicar por qué se rechazó una entrada, localizar un cambio de comportamiento y resumir evidencia contradictoria con enlaces a los artefactos. Sus cifras procederán de funciones deterministas. Se evaluará con preguntas cuya respuesta ya está calculada y con casos sin datos suficientes; en esos casos deberá reconocer la falta de evidencia.

Los modelos predictivos serán nuevas hipótesis. Se ensayarán primero referencias sencillas para tendencia, volatilidad o probabilidad de continuación, con entrenamiento separado por tiempo, registro de versiones y seguimiento de cambios en los datos. Su complejidad solo se incorporará si aporta una mejora medible fuera de entrenamiento. El motor de riesgo seguirá aplicando límites definidos y auditables a todas las estrategias.

## Regla para introducir tecnología adicional

Cada incorporación debe responder a un problema medido: reducir tiempo de investigación, detectar un fallo, mejorar reproducibilidad, facilitar una decisión o aportar evidencia nueva. Se compararán tiempo, memoria, coste y carga operativa antes y después. El crecimiento de infraestructura seguirá esas mediciones y el número real de activos, usuarios y trabajos.

El siguiente cambio de código corresponde a **0.2.1: protección y recuperación**. El trabajo de **0.3: datos e interrupciones** puede investigarse durante ese bloque sin consumir la prueba final reservada.
