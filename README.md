# SwapTradingCheto

[![Trading Lab CI](https://github.com/Finithe-Phoenix/SwapTradingCheto/actions/workflows/ci.yml/badge.svg)](https://github.com/Finithe-Phoenix/SwapTradingCheto/actions/workflows/ci.yml)

Laboratorio cuantitativo de **swing trading spot en BTC y ETH**. Incluye investigación histórica reproducible, replay con costes, controles de cartera y una integración de paper trading con Freqtrade 2026.8.

**Versión 0.1.0: simulación exclusivamente.** La demo usa datos sintéticos identificados como tales. Sus resultados comprueban mecánica, no rentabilidad. Este proyecto no incluye una transición automática a operaciones reales.

## Qué puedes ejecutar

| Componente | Incluido |
|---|---|
| Estrategia S1 | Velas 4h, filtro diario EMA200, ruptura de 20 velas, ATR14 y salida de 10 velas. |
| Riesgo | 0.25% por entrada, 0.50% conjunto, 40% de exposición máxima, pausas diaria y por caída. |
| Replay | Cartera conjunta BTC/ETH; costes y tamaños recalculados; stops adversos y retraso de ejecución. |
| Datos | Descarga pública de velas 1h, agregación 4h/1d, manifiesto SHA-256 y auditoría estricta. |
| Resultados | JSON, CSV, Markdown y registro SQLite; referencias de efectivo y comprar/mantener 50/50. |
| Integración | Adaptador Freqtrade, perfil simulado, panel FreqUI local y estado de riesgo persistente. |
| CI | Pruebas del motor, pruebas con Freqtrade real, demo reproducible y construcción del contenedor. |

## Arranque rápido: demo sin cuenta de exchange

Requiere Python 3.11 o posterior. El motor de investigación utiliza la biblioteca estándar de Python.

```bash
git clone https://github.com/Finithe-Phoenix/SwapTradingCheto.git
cd SwapTradingCheto
python -m venv .venv
```

Activa el entorno en PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

En Linux o macOS:

```bash
source .venv/bin/activate
```

Después, desde la raíz del repositorio:

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
trading-lab demo --output runs/demo-001
```

Abre `runs/demo-001/results/REPORT.md`. Los detalles están en `summary.json` y las carpetas `base`, `double_cost` y `delayed_1h`. Usa un nombre nuevo para cada ejecución: el programa no sobrescribe experimentos existentes.

Los tests del adaptador se omiten cuando Freqtrade no está instalado. Para ejecutarlos con sus clases reales:

```bash
python -m pip install -r requirements-freqtrade.txt
python -m unittest discover -s tests -v
```

## Datos reales y evaluación histórica

El descargador accede únicamente a los endpoints públicos `klines` y `exchangeInfo` de Binance. No necesita claves ni dispone de endpoints de órdenes. Verifica acceso permitido y cobertura desde tu ubicación. Un bloqueo de red o de disponibilidad se informa como error; no se sustituye la fuente silenciosamente.

Prueba primero un intervalo pequeño:

```bash
trading-lab download --start 2026-08-01 --end 2026-08-08 --output data/smoke-202608
trading-lab audit --data data/smoke-202608
```

Ese intervalo **no contiene el calentamiento necesario para EMA200 diaria**. Para investigar con la estrategia completa, descarga suficiente pasado y separa el periodo de evaluación:

```bash
trading-lab download --start 2019-01-01 --end 2026-09-01 --output data/history-2019-2026
trading-lab run --data data/history-2019-2026 --start 2020-01-01 --end 2024-01-01 --output runs/development-001
```

La descarga amplia puede tardar y depende de la cobertura disponible. Un hueco detiene la auditoría. Los tamaños mínimos registrados son los actuales; no se reconstruyen cambios históricos de filtros del exchange.

Las comisiones de `configs/lab.json` son **supuestos de laboratorio**, no una tarifa vigente de tu cuenta. El escenario adverso duplica comisión, spread y deslizamiento, y vuelve a calcular la cartera. No basta con restar costes de una lista de operaciones ya seleccionada.

## Paper trading y panel local

Requiere Docker Engine con Compose o Docker Desktop. No requiere depositar fondos.

```bash
trading-lab init
docker compose build
docker compose up -d
docker compose logs --tail 100 freqtrade
```

Abre **http://localhost:8080**. Usuario: `lab`. La contraseña única se genera en `.env` como `LAB_UI_PASSWORD`; consúltala localmente. `.env` y la configuración de ejecución no se suben a Git. Si ya existe `.env`, `init` conserva el archivo y devuelve un error explicativo.

El contenedor publica el puerto solo en la interfaz local. En Linux debe poder escribir en `user_data`; el usuario `ftuser` de la imagen debe tener permisos sobre ese directorio. No uses `chmod 777` ni ejecutes el bot como root para resolverlo.

Para detenerlo:

```bash
docker compose down
```

El estado virtual permanece en `user_data`. Detener el proceso interrumpe también la simulación de protección; usa las pausas del bot para frenar entradas mientras sigues observando posiciones.

Los comandos del motor usan sus propios históricos, separados de los CSV del replay:

```bash
docker compose run --rm freqtrade download-data --timeframes 1h 4h 1d --timerange 20190101-20260901
docker compose run --rm freqtrade backtesting --timeframe-detail 1h --timerange 20200101-20240101
```

El backtest de Freqtrade es una referencia distinta del replay adverso. Sus modelos de fills y stops no son idénticos. Las señales S1 comparten implementación; no se presume igualdad de P&L entre motores.

## Reglas y límites

Cada decisión usa únicamente velas cerradas. El máximo/mínimo del canal excluye la vela actual. La compra se procesa después de conocer la señal. El stop inicial es el precio de entrada menos dos ATR y se conserva; una pérdida no se promedia.

La pérdida de 0.25% es un presupuesto al stop, no una pérdida garantizada. Un gap puede excederlo. BTC y ETH comparten exposición y riesgo. Un importe inferior al mínimo de compra se rechaza, no se redondea hacia arriba.

Las pausas bloquean nuevas entradas y mantienen la gestión de salidas. El límite de caída permanece activo tras reinicios. Cambiar parámetros durante un experimento requiere archivarlo y comenzar otro con nombre y estado nuevos.

## Estado y siguientes validaciones

El repositorio entrega código y pruebas de funcionamiento. La demo sintética no prueba ingresos y no se ha completado una observación prospectiva de 4–8 semanas ni una evaluación independiente de rentabilidad. Véase [VALIDATION.md](docs/VALIDATION.md) para resultados comprobados y límites conocidos.

El siguiente trabajo de investigación es auditar un histórico amplio, congelar S1, ejecutar validación temporal, comparar los dos motores y acumular datos prospectivos. El objetivo de 100 operaciones sirve para revisar evidencia; no activa dinero real.

Documentación adicional: [diseño](docs/ARCHITECTURE.md), [plan y alcance](docs/PLAN.md) y [operación](docs/OPERATIONS.md).
