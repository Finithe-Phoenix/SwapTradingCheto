# Alcance y plan de investigación

## Alcance vigente

Swing trading sistemático en BTC/USDT y ETH/USDT, spot, sin apalancamiento. La primera estrategia es una hipótesis de tendencia/ruptura; no se presenta como rentable. Capital de laboratorio: 1,000 unidades virtuales. Capital real necesario para investigar: cero.

## Fases

| Fase | Entregable | Estado de esta versión |
|---|---|---|
| Base | Entorno, configuración y pruebas | Implementado. |
| Datos | Descarga pública y auditoría | 2019–2023 recuperado; 60 horas ausentes por activo, con diagnóstico publicado. |
| Estrategia/riesgo | S1, stop ATR, exposición y pausa | Implementado con pruebas. |
| Histórico | Replay, costes, métricas y referencias | Diagnóstico continuo parcial ejecutado; 10 operaciones, evidencia insuficiente. |
| Prospectiva | Perfil Freqtrade y panel local | Integración incluida; observación prolongada pendiente. |
| Decisión | Evaluación documentada de evidencia | Filtros automatizados de diagnóstico; faltan muestra e independencia. |

## Separación temporal propuesta

| Periodo UTC, final excluido | Uso |
|---|---|
| 2019-01-01 a 2020-01-01 | Calentamiento, sujeto a disponibilidad. |
| 2020-01-01 a 2024-01-01 | Desarrollo. |
| 2024-01-01 a 2026-01-01 | Validación cronológica. |
| 2026-01-01 a 2026-09-01 | Prueba final reservada. |
| Desde el inicio efectivo del paper trading | Datos prospectivos. |

Cambiar parámetros tras mirar la prueba final consume ese periodo como validación. La nueva versión necesita evidencia independiente posterior. Todas las variantes, incluyendo las fallidas, deben permanecer registradas.

`configs/research.json` recoge estas fronteras. `evaluate` exige 365 días completos de calentamiento y ejecuta una etapa con configuración fija, sin optimización ni reinicios anuales. Los huecos del histórico descargado bloquean actualmente la etapa completa de desarrollo. La versión 0.2.0 conserva ese intento fallido y realiza únicamente un diagnóstico parcial sobre el mayor tramo común continuo, acotado a días UTC completos. No modifica la separación temporal por ese resultado.

## Revisión de evidencia

Comparar expectativa neta, drawdown, profit factor, costes adversos, exposición, contribución por activo y cartera de referencia. Un profit factor de 1.20 es un filtro de investigación propuesto, no un estándar universal. Los intervalos por bloques son exploratorios y requieren sensibilidad a sus supuestos.

Primera revisión operativa tras 4–8 semanas. Objetivo de revisión: 100 operaciones cerradas consistentes. Si el swing trading produce menos operaciones, extender observación; no incrementar frecuencia ni riesgo para completar una cuota. Ningún umbral del software activa operaciones reales.

## Pendientes prioritarios

1. Definir y probar una política explícita para interrupciones del histórico; no rellenar precios ni borrar el diagnóstico para pasar la auditoría.
2. Completar desarrollo y sensibilidad del calentamiento; el diagnóstico parcial actual usa 213 días y no cubre todos los regímenes del plan.
3. Contrastar decisiones y contabilidad del replay con la referencia Freqtrade.
4. Congelar versión, datos y supuestos antes de la validación final.
5. Ejecutar paper trading continuo, revisar interrupciones y conservar evidencia.
6. Decidir entre ampliar muestra, corregir o descartar la hipótesis.
