# Diseño técnico

## Módulos

| Archivo | Responsabilidad |
|---|---|
| `market.py` | Velas, agregación UTC, EMA, ATR y señales S1 compartidas. |
| `risk.py` | Costes, presupuestos, dimensionamiento y estado de pausa. |
| `data.py` | Fuente pública, auditoría, CSV y manifiestos verificables. |
| `replay.py` | Secuencia horaria, cartera común, fills adversos, stops y entradas rechazadas. |
| `metrics.py` | Métricas netas, referencias e intervalos exploratorios por bloques diarios. |
| `storage.py` | Snapshots y eventos SQLite con escritura transaccional e IDs idempotentes. |
| `cli.py` | Demo, descarga, auditoría y reportes de experimentos. |
| `SwingBreakoutS1.py` | Adaptador a Freqtrade y controles previos a entradas simuladas. |

## Orden temporal del replay

En cada hora se valoran posiciones al precio de apertura y se revisa el presupuesto. Se procesan stops con salto y salidas pendientes; después, señales que ya estaban disponibles. Se calcula tamaño con costes y riesgo conjunto, luego se consideran stops dentro de la hora y se valora el cierre. El orden de activos es estable. La vela final liquida posiciones con los mismos costes para reconciliar P&L y efectivo.

El replay de costes adversos vuelve a ejecutar las señales candidatas: los costes cambian efectivo, patrimonio, tamaño y admisión. Un ajuste posterior de P&L no sustituye este cálculo.

Las velas 1h no describen el orden exacto de ticks. Los stops durante una hora usan supuestos conservadores y los saltos se ejecutan al precio de apertura desfavorable. No se simulan cola de prioridad, profundidad histórica, impacto no lineal o latencia medida de red.

## Señales

Las velas de 4h y 1d solo se generan con todos sus componentes horarios presentes. EMA200 diaria se inicializa con la media de 200 cierres; ATR14 usa suavizado de Wilder. La información diaria se asocia por fecha de cierre disponible. Las pruebas comparan señales de un prefijo con las obtenidas con datos futuros adicionales.

El calentamiento de EMA puede afectar resultados. Mantener la misma procedencia y longitud de historial entre experimentos; verificar sensibilidad con diferentes calentamientos antes de comparar P&L con Freqtrade.

## Costes y riesgo

Coste de ejecución por lado: `slippage_bps + spread_bps / 2`. La comisión se cobra sobre el importe de cada ejecución. El precio de compra incorpora impacto adverso; el de venta lo resta. El presupuesto incluye comisión de entrada y salida y ejecución desfavorable del stop, sin volver a cobrar el impacto de entrada ya incorporado al precio.

La valoración del replay usa liquidación estimada neta de costes. En Freqtrade, el patrimonio de riesgo usa capital virtual inicial, beneficio cerrado y beneficio abierto calculado por su modelo. Esta diferencia debe medirse; no se declara equivalencia de simulaciones.

## Entornos

La investigación offline utiliza la biblioteca estándar de Python. El paper trading usa la imagen publicada `freqtradeorg/freqtrade:2026.8` y el mismo código de señales y dimensionamiento. Las claves de API de exchange permanecen vacías. El punto de entrada rechaza modo real y sobrescrituras de entorno; la estrategia verifica también su propio modo.

Fuentes técnicas consultadas el 6 de septiembre de 2026: [Freqtrade 2026.8](https://github.com/freqtrade/freqtrade/releases/tag/2026.8), [callbacks](https://www.freqtrade.io/en/stable/strategy-callbacks/), [supuestos de backtest](https://www.freqtrade.io/en/stable/backtesting/#assumptions-made-by-backtesting) y [datos públicos de Binance](https://developers.binance.com/en/docs/introduction).
