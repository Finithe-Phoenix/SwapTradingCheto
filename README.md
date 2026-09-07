# SwapTradingCheto

[![Trading Lab CI](https://github.com/Finithe-Phoenix/SwapTradingCheto/actions/workflows/ci.yml/badge.svg)](https://github.com/Finithe-Phoenix/SwapTradingCheto/actions/workflows/ci.yml)

Laboratorio cuantitativo de **swing trading spot en BTC y ETH**. Incluye investigación histórica reproducible, replay con costes, controles de cartera y una integración de paper trading con Freqtrade 2026.8.

**Versión 0.2.0: simulación exclusivamente.** Incluye una primera evaluación exploratoria sobre precios históricos reales y un diagnóstico de cobertura. La muestra contiene solo 10 operaciones; todavía no acredita una ventaja estadística. La demo sigue usando datos sintéticos identificados como tales. Este proyecto no incluye una transición automática a operaciones reales.

## Qué puedes ejecutar

| Componente | Incluido |
|---|---|
| Estrategia S1 | Velas 4h, filtro diario EMA200, ruptura de 20 velas, ATR14 y salida de 10 velas. |
| Riesgo | 0.25% por entrada, 0.50% conjunto, 40% de exposición máxima, pausas diaria y por caída. |
| Replay | Cartera conjunta BTC/ETH; costes y tamaños recalculados; stops adversos y retraso de ejecución. |
| Datos | Descarga pública reanudable, páginas con SHA-256, diagnóstico de huecos y extracción explícita de tramos continuos. |
| Resultados | JSON, CSV, Markdown y SQLite; desglose mensual/anual de una cartera continua, pausas, filtros de evidencia y referencias. |
| Evaluación temporal | Etapas declaradas, calentamiento exigido y recorte de datos futuros; prueba final reservada. |
| Integración | Adaptador Freqtrade, panel FreqUI local, pausas persistentes y diagnóstico de estado de solo lectura. |
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
trading-lab download --start 2023-08-01 --end 2023-08-08 --output data/smoke-202308
trading-lab audit --data data/smoke-202308
```

Ese intervalo **no contiene el calentamiento necesario para EMA200 diaria**. Para investigar con la estrategia completa, descarga suficiente pasado y separa el periodo de evaluación:

```bash
trading-lab download --start 2019-01-01 --end 2024-01-01 --output data/development-2019-2023
```

**Resultado observado:** esta fuente devuelve 60 horas ausentes por activo en ese intervalo. La descarga conserva las páginas, publica el diagnóstico de cobertura y termina con error; no crea un dataset válido ni rellena velas. Véase [la evidencia de cobertura](docs/evidence/coverage-2019-2023.json).

Una interrupción de red se reanuda con las mismas fechas y destino:

```bash
trading-lab download --start 2019-01-01 --end 2024-01-01 --output data/development-2019-2023 --resume
trading-lab inspect-download --cache data/development-2019-2023.download
```

`--resume` verifica las páginas guardadas; no corrige huecos históricos. Ejecuta una sola descarga por destino. Conserva el directorio `.download` junto a sus diagnósticos. Los filtros de mínimos registrados corresponden al momento de la descarga; no reconstruyen cambios históricos del exchange.

Para repetir el diagnóstico publicado, extrae el tramo continuo elegido por cobertura, sin cambiar S1:

```bash
trading-lab extract --cache data/development-2019-2023.download --start 2021-09-30 --end 2023-03-24 --output data/development-contiguous
trading-lab run --data data/development-contiguous --start 2022-05-01 --end 2023-03-24 --output runs/development-contiguous-001
```

Usa 213 días completos de calentamiento y evalúa 327 días. Es un diagnóstico parcial de desarrollo, no una validación independiente. [Resultados y límites](docs/VALIDATION.md).

Para un dataset que sí cubra íntegramente la etapa declarada:

```bash
trading-lab evaluate --data data/complete-development --stage development --output runs/declared-development-001
```

`evaluate` usa `configs/research.json`, exige su calentamiento de 365 días y recorta el futuro antes del replay. Solo admite `development` o `validation`; el periodo final reservado no forma parte de ese comando. No reajusta parámetros ni reinicia el riesgo cada año. La cobertura descargada arriba todavía impide completar esa etapa. `run` es una herramienta exploratoria con fechas explícitas; registra cualquier uso que consuma periodos reservados.

Las comisiones de `configs/lab.json` son **supuestos de laboratorio**, no una tarifa vigente de tu cuenta. El escenario adverso duplica comisión, spread y deslizamiento, y vuelve a calcular la cartera. No basta con restar costes de una lista de operaciones ya seleccionada.

## Paper trading y panel local

Requiere Docker Engine con Compose o Docker Desktop. No requiere depositar fondos.

```bash
trading-lab init
docker compose build
docker compose up -d
docker compose logs --tail 100 freqtrade
trading-lab paper-status --directory user_data
```

Abre **http://localhost:8080**. Usuario: `lab`. La contraseña única se genera en `.env` como `LAB_UI_PASSWORD`; consúltala localmente. `.env` y la configuración de ejecución no se suben a Git. Si ya existe `.env`, `init` conserva el archivo y devuelve un error explicativo.

El contenedor publica el puerto solo en la interfaz local. En Linux debe poder escribir en `user_data`; el usuario `ftuser` de la imagen debe tener permisos sobre ese directorio. No uses `chmod 777` ni ejecutes el bot como root para resolverlo.

Para detenerlo:

```bash
docker compose down
```

El estado virtual permanece en `user_data`. Detener el proceso interrumpe también la simulación de protección; usa las pausas del bot para frenar entradas mientras sigues observando posiciones. `paper-status` informa la última señal de estado del control de riesgo: salida 0 si admite entradas, 3 si faltan datos, están vencidos o existe una pausa, y 2 si el estado es inválido. Consulta [recuperación y diagnóstico](docs/OPERATIONS.md).

Los comandos del motor usan sus propios históricos, separados de los CSV del replay:

```bash
docker compose run --rm freqtrade download-data --timeframes 1h 4h 1d --timerange 20190101-20240101
docker compose run --rm freqtrade backtesting --timeframe-detail 1h --timerange 20200101-20240101
```

El backtest de Freqtrade es una referencia distinta del replay adverso. Sus modelos de fills y stops no son idénticos. Las señales S1 comparten implementación; no se presume igualdad de P&L entre motores.

## Reglas y límites

Cada decisión usa únicamente velas cerradas. El máximo/mínimo del canal excluye la vela actual. La compra se procesa después de conocer la señal. El stop inicial es el precio de entrada menos dos ATR y se conserva; una pérdida no se promedia.

La pérdida de 0.25% es un presupuesto al stop, no una pérdida garantizada. Un gap puede excederlo. BTC y ETH comparten exposición y riesgo. Un importe inferior al mínimo de compra se rechaza, no se redondea hacia arriba.

Las pausas bloquean nuevas entradas y mantienen la gestión de salidas. El límite de caída permanece activo tras reinicios. Cambiar parámetros durante un experimento requiere archivarlo y comenzar otro con nombre y estado nuevos.

## Estado y siguientes validaciones

El repositorio entrega código, pruebas y evidencia histórica parcial. El diagnóstico sobre precios reales pasa algunos filtros, pero falla la muestra de 100 operaciones y la sensibilidad del intervalo exploratorio. No se ha completado una observación prospectiva de 4–8 semanas ni una evaluación independiente de rentabilidad. Véase [VALIDATION.md](docs/VALIDATION.md) para resultados comprobados y límites conocidos.

El siguiente trabajo es definir y probar el tratamiento de interrupciones históricas del mercado, completar desarrollo, comparar los dos motores y acumular datos prospectivos. La validación 2024–2025 y la prueba final 2026 permanecen sin evaluar en esta versión. El objetivo de 100 operaciones sirve para revisar evidencia; no activa dinero real.

Documentación adicional: [diseño](docs/ARCHITECTURE.md), [plan y alcance](docs/PLAN.md) y [operación](docs/OPERATIONS.md).

La [hoja de ruta hacia 1.0](docs/ROADMAP.md) prioriza protección, datos, investigación, API/panel, operación e IA con criterios de aceptación. Describe trabajo pendiente; la versión ejecutable actual sigue siendo 0.2.0.
