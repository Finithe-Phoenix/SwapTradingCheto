# Registro de evidencia de 0.2.0

Fecha de ejecución: 6 de septiembre de 2026. Fuente de mercado: endpoints públicos de Binance, sin autenticación. S1 y `configs/lab.json` mantienen sus parámetros de la versión 0.1.0.

| Intento | Resultado | Archivo |
|---|---|---|
| Recuperación 2019-01-01 a 2024-01-01 | 43,764 horas por activo; 60 ausentes. Auditoría completa bloqueada. | [Cobertura](coverage-2019-2023.json). |
| Extracción por cobertura | Mayor tramo común, acotado a medianoches UTC: 2021-09-30 a 2023-03-24. | Procedencia y hashes en el resumen. |
| Replay exploratorio inicial | 2022-05-01 a 2023-03-24, tres escenarios; diez operaciones en cada uno. | [Resumen inicial](development-contiguous-initial-summary.json). |
| Regeneración final del informe | Mismo dato, configuración, fechas y resultados; incorpora ajustes del informe y del diagnóstico operativo. | [Resumen final](development-contiguous/summary.json), [informe](development-contiguous/REPORT.md). |

Los objetos `scenarios` de los dos resúmenes son idénticos. No son dos muestras independientes, ni se eligió entre variantes de estrategia. El diagnóstico inicial y la regeneración conservan su propia huella de código; se ejecutaron con cambios locales, antes de publicarse el commit de esta versión. La huella de fuentes permite comprobar los archivos exactos aunque el campo `commit` señale al padre y `working_tree_dirty` sea verdadero.

El periodo evaluado tuvo 213 días anteriores completos de calentamiento y 327 días de observación. Elegir el tramo por continuidad limita la cobertura de regímenes; esos resultados no pueden atribuirse al desarrollo 2020–2023 completo. La política para simular interrupciones históricas sigue pendiente.

Se conservan las diez operaciones, el desglose mensual y anual de cada escenario. Los CSV de mercado y la curva horaria se regeneran con los comandos del README; sus hashes de entrada están en los resúmenes. No se suben credenciales ni bases de operación del usuario.

## Qué no demuestra este ensayo

Diez operaciones y un intervalo parcial no acreditan una ventaja estable. Los filtros de muestra y sensibilidad estadística fallan. El resultado positivo tampoco representa una previsión de ingreso mensual. Esta versión no ha evaluado validación 2024–2025 ni la prueba final 2026.
