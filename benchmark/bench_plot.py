"""
bench_plot.py — Lee el CSV de bench_report.py y genera las tres figuras
listas para slides (PNG, alta resolución, con barras de error).

Uso:
    .venv/bin/python bench_report.py --csv bench.csv     # genera bench.csv
    .venv/bin/python bench_plot.py --csv bench.csv        # genera los 3 PNG

Salidas:
    fig1_escalado.png       El impuesto de coordinación escala (llamadas y costo vs. ops)
    fig2_predictibilidad.png  Coeficiente de variación: quién es más predecible
    fig3_coordinacion.png   En qué se van los tool-calls (transfers vs. updates)

Sin dependencias más allá de matplotlib. No usa red.
"""

import argparse
import csv
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")  # backend sin display
import matplotlib.pyplot as plt

# --- Estética para proyector: fuentes grandes, líneas gruesas -----------------
plt.rcParams.update({
    "figure.dpi": 160,
    "savefig.dpi": 160,
    "font.size": 14,
    "axes.titlesize": 17,
    "axes.titleweight": "bold",
    "axes.labelsize": 14,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "lines.linewidth": 2.4,
    "lines.markersize": 8,
})

# Colores fijos por patrón (consistentes en las 3 figuras)
COLOR = {
    "multiagent": "#D1495B",   # rojo — el patrón que paga el impuesto
    "workflow":   "#2E86AB",   # azul — el loop determinista
}
LABEL = {
    "multiagent": "Multi-agente (ruteo dinámico)",
    "workflow":   "Workflow loop (LoopAgent)",
}


def load(path):
    """Devuelve {pattern: [filas ordenadas por ops]} desde el CSV."""
    by_pat = defaultdict(list)
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for k in ("ops", "llm_calls_mean", "llm_calls_sd",
                      "cost_usd_mean", "cost_usd_sd",
                      "in_tok_mean", "out_tok_mean",
                      "transfers_mean", "updates_mean"):
                row[k] = float(row[k]) if row.get(k) not in (None, "") else 0.0
            by_pat[row["pattern"]].append(row)
    for pat in by_pat:
        by_pat[pat].sort(key=lambda r: r["ops"])
    return by_pat


def fig1_escalado(by_pat, out):
    """Dos paneles: llamadas al LLM y costo, ambos vs. n_ops, con barras de error."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2))

    for pat, rows in by_pat.items():
        x = [r["ops"] for r in rows]
        c = COLOR.get(pat, "#666")
        ax1.errorbar(x, [r["llm_calls_mean"] for r in rows],
                     yerr=[r["llm_calls_sd"] for r in rows],
                     marker="o", capsize=4, color=c, label=LABEL.get(pat, pat))
        ax2.errorbar(x, [r["cost_usd_mean"] for r in rows],
                     yerr=[r["cost_usd_sd"] for r in rows],
                     marker="o", capsize=4, color=c, label=LABEL.get(pat, pat))

    ax1.set_title("Llamadas al LLM")
    ax1.set_xlabel("Operaciones en la expresión")
    ax1.set_ylabel("Llamadas (media ± σ)")

    ax2.set_title("Costo por corrida")
    ax2.set_xlabel("Operaciones en la expresión")
    ax2.set_ylabel("USD (media ± σ)")

    ax1.legend(frameon=False, fontsize=11)
    fig.suptitle("El impuesto de coordinación escala con la complejidad",
                 fontsize=19, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out)
    plt.close(fig)
    print(f"  {out}")


def fig2_predictibilidad(by_pat, out):
    """Coeficiente de variación (σ/media, %) del costo por peldaño y patrón."""
    rungs = _ordered_rungs(by_pat)
    x = range(len(rungs))
    width = 0.38
    fig, ax = plt.subplots(figsize=(11, 5.4))

    pats = list(by_pat.keys())
    for i, pat in enumerate(pats):
        m = {r["rung"]: r for r in by_pat[pat]}
        cv = []
        for rg in rungs:
            r = m.get(rg)
            if r and r["cost_usd_mean"] > 0:
                cv.append(100.0 * r["cost_usd_sd"] / r["cost_usd_mean"])
            else:
                cv.append(0.0)
        offset = (i - (len(pats) - 1) / 2) * width
        ax.bar([xi + offset for xi in x], cv, width,
               color=COLOR.get(pat, "#666"), label=LABEL.get(pat, pat))

    ax.set_title("Predictibilidad: variación del costo entre corridas")
    ax.set_ylabel("Coeficiente de variación del costo (σ/media, %)")
    ax.set_xlabel("Peldaño de complejidad")
    ax.set_xticks(list(x))
    ax.set_xticklabels(rungs)
    ax.legend(frameon=False, fontsize=11)
    ax.text(0.5, -0.18, "Barra más baja = más predecible (mejor para forecast de costo y SLOs)",
            transform=ax.transAxes, ha="center", fontsize=11, color="#555")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    print(f"  {out}")


def fig3_coordinacion(by_pat, out):
    """Tool-calls por corrida: transfers (coordinación) vs. updates (trabajo)."""
    rungs = _ordered_rungs(by_pat)
    x = range(len(rungs))
    width = 0.38
    fig, ax = plt.subplots(figsize=(11, 5.4))

    ma = {r["rung"]: r for r in by_pat.get("multiagent", [])}
    wf = {r["rung"]: r for r in by_pat.get("workflow", [])}

    transfers = [ma.get(rg, {}).get("transfers_mean", 0.0) for rg in rungs]
    updates = [wf.get(rg, {}).get("updates_mean", 0.0) for rg in rungs]

    ax.bar([xi - width / 2 for xi in x], transfers, width,
           color=COLOR["multiagent"], label="transfer_to_agent (coordinación)")
    ax.bar([xi + width / 2 for xi in x], updates, width,
           color=COLOR["workflow"], label="update_expression (trabajo)")

    ax.set_title("¿En qué se van los tool-calls?")
    ax.set_ylabel("Tool-calls por corrida (media)")
    ax.set_xlabel("Peldaño de complejidad")
    ax.set_xticks(list(x))
    ax.set_xticklabels(rungs)
    ax.legend(frameon=False, fontsize=11)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    print(f"  {out}")


def _ordered_rungs(by_pat):
    """Lista de peldaños ordenada por ops, unión de ambos patrones."""
    seen = {}
    for rows in by_pat.values():
        for r in rows:
            seen[r["rung"]] = r["ops"]
    return [rg for rg, _ in sorted(seen.items(), key=lambda kv: kv[1])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="benchmark/bench.csv")
    ap.add_argument("--prefix", default="", help="prefijo para los PNG, p.ej. 'invoice_'")
    args = ap.parse_args()

    by_pat = load(args.csv)
    print("Generando figuras:")
    fig1_escalado(by_pat, f"{args.prefix}fig1_escalado.png")
    fig2_predictibilidad(by_pat, f"{args.prefix}fig2_predictibilidad.png")
    fig3_coordinacion(by_pat, f"{args.prefix}fig3_coordinacion.png")
    print("Listo.")


if __name__ == "__main__":
    main()
