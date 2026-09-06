# Validación de la versión 0.2.0

Fecha: 6 de septiembre de 2026. Se mantiene S1 y la configuración de riesgo de 0.1.0, sin ajustar parámetros al resultado observado.

## Funcionamiento comprobado

- 65 pruebas locales correctas en Python 3.12, incluyendo Freqtrade 2026.8 instalado: 20 más que en 0.1.0.
- Reanudación tras interrupción, rechazo de páginas alteradas y de solicitudes incompatibles, diagnóstico de huecos y extracción estricta.
- Evaluación temporal con calentamiento suficiente, recorte del futuro y plan identificado por SHA-256.
- Composición de retornos mensuales, continuidad entre meses, conciliación del P&L y duración de las caídas.
- Reinicio con pausa por caída conservada; bloqueo cuando existen operaciones y falta su estado de riesgo; lectura de estado vencido y recuperación tras fallo de valoración.
- Se mantienen las pruebas de señales causales, costes, stops, contabilidad, restricciones de configuración y esquema nativo de Freqtrade.
- Demo sintética completa de 520 días y tres escenarios ejecutada. Sus cifras solo comprueban mecánica.

La construcción del contenedor y los entornos Python de CI se verifican mediante [GitHub Actions](https://github.com/Finithe-Phoenix/SwapTradingCheto/actions/workflows/ci.yml). El entorno local no dispone de Docker. CI ejecuta pruebas finitas, no aloja paper trading continuo.

## Cobertura real y prueba amplia bloqueada

Se consultaron los endpoints públicos de Binance para 2019-01-01 a 2024-01-01, final excluido. Cada activo devuelve **43,764 velas horarias frente a 43,824 esperadas: faltan 60 horas distribuidas en 20 huecos**. Los dos activos presentan los mismos intervalos ausentes en esta descarga.

La auditoría bloqueó correctamente la publicación de un dataset completo. No se rellenaron precios ni se borraron huecos. [Diagnóstico completo y tramos comunes](evidence/coverage-2019-2023.json).

Esto impide completar por ahora la etapa de desarrollo 2020–2023. No se atribuye la causa de cada hueco sin contrastarla con evidencia adicional del exchange.

## Diagnóstico parcial sobre precios reales

Se eligió el **mayor tramo común continuo**, antes de mirar sus resultados, y se acotó a días UTC completos: 2021-09-30 a 2023-03-24. Contiene 12,960 velas por activo. De ese tramo, 213 días sirven de calentamiento y 327 días de evaluación, desde 2022-05-01. El calentamiento supera el mínimo EMA200, pero su sensibilidad todavía no está resuelta.

Capital virtual inicial: 1,000 USDT. Comisión por lado: 0.10%; deslizamiento: 5 puntos base; spread completo: 2 puntos base. Son supuestos del modelo, no tarifas verificadas de una cuenta del usuario.

| Escenario | Retorno neto | Caída máxima | Operaciones cerradas |
|---|---:|---:|---:|
| Base | +1.30% | 1.05% | 10 |
| Doble coste | +1.02% | 0.97% | 10 |
| Ejecución una hora después | +0.86% | 1.19% | 10 |

Las tres cifras proceden de carteras recalculadas con cada supuesto. S1 no abrió posiciones durante la parte de 2022 evaluada; las operaciones aparecen en 2023. No hubo pausa por caída en este ensayo. Una operación termina liquidada al final del intervalo: también cuenta dentro de las 10 y está identificada en el CSV.

La referencia BTC/ETH 50/50 obtuvo −29.37% y una caída máxima de 62.44%. Invierte todo el capital inicial y asume más exposición que S1; no es una comparación a igual riesgo.

**La evidencia sigue siendo insuficiente.** Fallan el objetivo de muestra de 100 operaciones y la sensibilidad de los límites inferiores del bootstrap por bloques. Un profit factor de 2.30 con diez operaciones no demuestra estabilidad. El periodo es parcial, pertenece a desarrollo y fue seleccionado por continuidad de datos; no sustituye una validación independiente.

[Informe](evidence/development-contiguous/REPORT.md), [resumen completo](evidence/development-contiguous/summary.json) y [registro de intentos](evidence/README.md).

## Límites pendientes

1. Completar desarrollo exige una política probada de interrupciones históricas o una fuente con cobertura verificada y procedencia explícita. El replay actual rechaza huecos.
2. No se han evaluado 2024–2025 ni el periodo final reservado de 2026. La prueba corta de conectividad de agosto de 2026, hecha en 0.1.0, no fue una evaluación de S1.
3. No se ha realizado observación prospectiva continua de 4–8 semanas.
4. Las velas horarias no reconstruyen libro, colas, liquidez intrabar o impacto no lineal; los máximos de caída observados pueden omitir movimientos intrahorarios.
5. Freqtrade y replay comparten señales y dimensionamiento, pero no se presume igualdad de fills o P&L. Falta comparación amplia entre motores.
6. Los filtros descargados son actuales. Su historia y todos los controles del motor de órdenes no se reconstruyen.
7. La señal de estado del bot no prueba disponibilidad continua del exchange ni frescura de todos los datos; un ticker sin timestamp no permite verificar su edad.
8. Los intervalos estadísticos son exploratorios y el conjunto pequeño no demuestra rentabilidad futura. El software mantiene `live_eligible: false`.

## Repetir la validación

```bash
python -m pip install -e . -r requirements-freqtrade.txt
python -m unittest discover -s tests -v
trading-lab demo --output runs/validation-new
```

El README incluye los comandos exactos de descarga, inspección, extracción y replay real. Conservar cada intento y los hashes; no concatenar las ejecuciones repetidas como muestras independientes.
