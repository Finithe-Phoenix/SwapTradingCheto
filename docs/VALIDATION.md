# Validación de la versión 0.1.0

Fecha de la validación local: 6 de septiembre de 2026.

## Comprobado

- Suite de 45 pruebas ejecutada correctamente en Python 3.12, incluyendo pruebas con Freqtrade 2026.8 instalado.
- Configuración validada contra el esquema real de Freqtrade.
- Señales del adaptador y del replay contrastadas sobre el mismo conjunto de entrada.
- Ausencia de anticipación comprobada en pruebas de prefijos y alteraciones de futuro.
- Casos de riesgo conjunto, mínimos de compra, costes, gaps, persistencia, duplicados y bloqueo de configuración.
- Demo completa de 520 días sintéticos ejecutada con escenarios base, doble coste y retraso de una hora.
- Descarga pública de BTC/USDT y ETH/USDT del 1 al 3 de agosto de 2026, con 48 velas por activo, auditada en el entorno de desarrollo.

Las cifras de la demo no se presentan como rentabilidad observada del mercado. El intervalo de descarga comprueba conectividad y formato; no contiene el calentamiento necesario para evaluar EMA200 diaria.

La configuración Compose se ha leído y comprobado localmente. El entorno local de desarrollo no dispone del daemon de Docker; la construcción de la imagen se verifica mediante el workflow de GitHub Actions. El estado actualizado de esa ejecución está disponible en la pestaña Actions.

## Límites concretos

1. No se ha completado el backtest de varios años ni una evaluación final fuera del periodo de desarrollo.
2. No se ha realizado una observación prospectiva continua de 4–8 semanas.
3. El replay usa velas horarias; no reproduce libro histórico, colas, liquidez intrabar o impacto no lineal.
4. El modelo de ejecución de Freqtrade difiere del replay. Se comparte señal y dimensionamiento, no se presume igualdad de fills o P&L.
5. Los filtros de mercado descargados son actuales. Las modificaciones históricas de mínimos y precisión no se reconstruyen.
6. La integración reinicia la evaluación de admisiones si no puede valorar una posición; requiere revisar cualquier fallo persistente de datos o metadata de riesgo.
7. Los intervalos de confianza son exploratorios. Muestras reducidas, cambios de régimen y selección de variantes pueden invalidar conclusiones optimistas.
8. No se han activado operaciones reales ni se incluyen credenciales de trading.

## Repetir la validación

```bash
python -m pip install -e . -r requirements-freqtrade.txt
python -m unittest discover -s tests -v
trading-lab demo --output runs/validation-new
```

Para investigar datos reales, seguir la separación temporal de `PLAN.md` y conservar manifiesto, configuración, versión de código e intentos fallidos.
