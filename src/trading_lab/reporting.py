"""Portable research reports and source fingerprints."""
import hashlib
from pathlib import Path
import subprocess


def provenance():
    root = Path(__file__).resolve().parents[2]
    try:
        commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], stderr=subprocess.DEVNULL, text=True).strip())
    except (subprocess.SubprocessError, FileNotFoundError):
        commit, dirty = None, None
    paths = sorted({path for pattern in ("src/**/*.py", "user_data/strategies/*.py", "scripts/*.py",
                                         "configs/*.json", "pyproject.toml", "requirements*.txt", "Dockerfile")
                    for path in root.glob(pattern) if "__pycache__" not in path.parts})
    files = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    payload = "".join(f"{name}\0{value}\n" for name, value in files.items()).encode()
    return {"commit": commit, "working_tree_dirty": dirty,
            "source_sha256": hashlib.sha256(payload).hexdigest() if files else None, "source_files": files}


def display(value, percent=False):
    if value is None:
        return "No definido"
    return f"{value:.2%}" if percent else f"{value:.3f}"


def render_report(report):
    base = report["scenarios"]["base"]
    lines = ["# Informe del laboratorio", "", f"Origen: **{report['data_manifest']['origin']}**.", "",
             f"Periodo UTC: {base['period']['start']} → {base['period']['end_exclusive']} (final excluido).",
             f"Etapa: `{report['evaluation_stage']}`. Versión: `{report['engine_version']}`.", "",
             "Simulación exclusivamente. Un backtest positivo no acredita ingresos futuros. Los datos sintéticos solo comprueban mecánica.", "",
             "## Escenarios de la misma cartera", "",
             "| Escenario | Retorno neto | Caída máxima | Operaciones | Factor de beneficio | Expectativa (USDT) |",
             "|---|---:|---:|---:|---:|---:|"]
    for name, scenario in report["scenarios"].items():
        m = scenario["metrics"]
        lines.append(f"| {name} | {m['net_return']:.2%} | {m['max_drawdown']:.2%} | {m['closed_trades']} | {display(m['profit_factor'])} | {display(m['expectancy_quote'])} |")
    m = base["metrics"]
    risk = m["risk_diagnostics"]
    lines += ["", f"Referencia comprar/mantener BTC/ETH 50/50: {m['buy_hold_50_50_return']:.2%}; caída máxima {m['buy_hold_max_drawdown']:.2%}.",
              f"La referencia invierte el 100% inicial; S1 limita exposición al {report['config']['max_total_exposure']:.0%}. Sus riesgos son distintos.", "",
              "## Estado del riesgo", "",
              f"Primera pausa permanente por caída: **{risk['first_drawdown_halt_at'] or 'ninguna'}**.",
              f"Marcas horarias con pausa permanente: {risk['halted_hourly_marks']}; con pausa diaria: {risk['daily_paused_hourly_marks']}.",
              f"Duración máxima bajo el último máximo: {risk['max_underwater_hours']:.0f} horas.",
              f"Marcas horarias con posición abierta: {risk['fraction_hourly_marks_in_position']:.2%}; exposición media sobre todas las marcas horarias: {risk['mean_exposure_fraction_at_hourly_marks']:.2%} (incluye horas sin posición).",
              "Una pausa bloquea entradas nuevas; no reinicia la cuenta al cambiar de mes o año. Puede haber pérdidas adicionales en posiciones existentes.", "",
              "## Años de la ejecución continua", "",
              "| Año | Retorno | Referencia 50/50 | Caída dentro del año | Marcas con pausa |",
              "|---|---:|---:|---:|---:|"]
    for row in m["annual"]:
        lines.append(f"| {row['period']} | {row['net_return']:.2%} | {row['buy_hold_return']:.2%} | {row['max_drawdown_within_period']:.2%} | {row['halted_hourly_marks']} |")
    lines += ["", "Los periodos parciales conservan sus fechas y horas en los CSV. Los retornos mensuales se componen sobre la misma cartera; no son backtests reiniciados.", "",
              "## Filtros de investigación", "", "| Filtro | Cumple | Regla |", "|---|---|---|"]
    for check in report["evidence"]["checks"]:
        lines.append(f"| {check['name']} | {'Sí' if check['passed'] else 'No'} | {check['rule']} |")
    lines += ["", "Estos filtros se declaran antes de evaluar; no son estándares universales ni habilitan dinero real.",
              "El bootstrap por bloques es exploratorio: dependencia temporal, selección de variantes y cambios de régimen limitan su interpretación.", "",
              "## Reproducibilidad", "",
              f"Código SHA-256: `{report['provenance']['source_sha256']}`.",
              f"Configuración SHA-256: `{report['config_sha256']}`.",
              f"Cambios locales al ejecutar: `{report['provenance']['working_tree_dirty']}`.",
              "Cada escenario conserva operaciones, patrimonio, decisiones y desglose mensual/anual. summary.json incluye filtros, calentamiento, hashes y supuestos."]
    if any(not x["daily_warmup_sufficient"] for x in report["warmup"].values()):
        lines += ["", "**Calentamiento diario insuficiente al inicio.** El periodo inicial incluye aprendizaje del indicador; no equivale a una evaluación precalentada."]
    if "extraction" in report["data_manifest"]:
        lines += ["", "**Diagnóstico sobre un tramo continuo extraído.** No representa todo el periodo de desarrollo ni completa su evaluación. Los huecos de la fuente se conservan en el informe de cobertura original."]
    return "\n".join(lines) + "\n"
