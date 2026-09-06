# Informe del laboratorio

Origen: **binance-spot-public**.

Periodo UTC: 2022-05-01T00:00:00Z → 2023-03-24T00:00:00Z (final excluido).
Etapa: `exploratory`. Versión: `0.2.0`.

Simulación exclusivamente. Un backtest positivo no acredita ingresos futuros. Los datos sintéticos solo comprueban mecánica.

## Escenarios de la misma cartera

| Escenario | Retorno neto | Caída máxima | Operaciones | Factor de beneficio | Expectativa (USDT) |
|---|---:|---:|---:|---:|---:|
| base | 1.30% | 1.05% | 10 | 2.299 | 1.296 |
| double_cost | 1.02% | 0.97% | 10 | 1.996 | 1.018 |
| delayed_1h | 0.86% | 1.19% | 10 | 1.805 | 0.855 |

Referencia comprar/mantener BTC/ETH 50/50: -29.37%; caída máxima 62.44%.
La referencia invierte el 100% inicial; S1 limita exposición al 40%. Sus riesgos son distintos.

## Estado del riesgo

Primera pausa permanente por caída: **ninguna**.
Marcas horarias con pausa permanente: 0; con pausa diaria: 0.
Duración máxima bajo el último máximo: 603 horas.
Marcas horarias con posición abierta: 9.40%; exposición media sobre todas las marcas horarias: 0.95% (incluye horas sin posición).
Una pausa bloquea entradas nuevas; no reinicia la cuenta al cambiar de mes o año. Puede haber pérdidas adicionales en posiciones existentes.

## Años de la ejecución continua

| Año | Retorno | Referencia 50/50 | Caída dentro del año | Marcas con pausa |
|---|---:|---:|---:|---:|
| 2022 | 0.00% | -56.23% | 0.00% | 0 |
| 2023 | 1.30% | 61.35% | 1.05% | 0 |

Los periodos parciales conservan sus fechas y horas en los CSV. Los retornos mensuales se componen sobre la misma cartera; no son backtests reiniciados.

## Filtros de investigación

| Filtro | Cumple | Regla |
|---|---|---|
| closed_trade_sample | No | >= 100; review target, not proof |
| net_expectancy | Sí | > 0 after modeled costs |
| profit_factor | Sí | >= 1.20; proposed research filter |
| drawdown | Sí | <= 0.05 |
| drawdown_halt | Sí | no persistent drawdown halt |
| double_cost | Sí | positive net return under the stated stress |
| delayed_1h | Sí | positive net return under the stated stress |
| bootstrap_sensitivity | No | exploratory lower bound > 0 for blocks of 3, 7 and 14 days |

Estos filtros se declaran antes de evaluar; no son estándares universales ni habilitan dinero real.
El bootstrap por bloques es exploratorio: dependencia temporal, selección de variantes y cambios de régimen limitan su interpretación.

## Reproducibilidad

Código SHA-256: `f69208cf570e9393a81e64090365f44ee4050ddb938db357238d65afe57f1dca`.
Configuración SHA-256: `dbef9bd5e39a1537ad1f5e61692765cab4dcb39792bed0608dc3d00569db3b2e`.
Cambios locales al ejecutar: `True`.
Cada escenario conserva operaciones, patrimonio, decisiones y desglose mensual/anual. summary.json incluye filtros, calentamiento, hashes y supuestos.

**Diagnóstico sobre un tramo continuo extraído.** No representa todo el periodo de desarrollo ni completa su evaluación. Los huecos de la fuente se conservan en el informe de cobertura original.
