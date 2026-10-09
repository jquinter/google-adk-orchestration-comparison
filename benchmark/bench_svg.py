"""
bench_svg.py — Turn a bench_report.py CSV into the three result charts as
inline SVG snippets for the talk deck (navy background, GDE palette), so the
slides show measured data in the same visual language as the rest of the deck.

Uso:
    .venv/bin/python benchmark/bench_report.py --infile benchmark/full/calculator_adk1_n10.jsonl \
        --csv benchmark/full/calculator_adk1_n10.csv
    .venv/bin/python benchmark/bench_svg.py --csv benchmark/full/calculator_adk1_n10.csv --outdir benchmark/full

Salidas: svg1_escalado.svg, svg2_predictibilidad.svg, svg3_coordinacion.svg
Colores como CSS custom properties del deck (var(--red), var(--blue), ...).
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

W, H = 520, 220                      # same viewBox as the deck's schematic charts
X0, X1, Y0, Y1 = 56, 500, 22, 182    # plot area
AXIS = "rgba(255,255,255,.25)"
GRID = "rgba(255,255,255,.08)"
TEXT = 'fill="var(--muted)" font-family="Roboto Mono" font-size="11"'

COLOR = {
    "multiagent": "var(--red)",
    "workflow": "var(--blue)",
    "single_structured": "var(--limegreen)",
    "single_naive": "var(--muted)",
}
LABEL = {
    "multiagent": "multi-agente",
    "workflow": "workflow",
    "single_structured": "agente único (estructurado)",
    "single_naive": "agente único (mínima)",
}


def load(path):
    by_pat = defaultdict(dict)
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for k, v in row.items():
                if k not in ("pattern", "rung", "ok_pct"):
                    row[k] = float(v) if v not in (None, "") else 0.0
            by_pat[row["pattern"]][row["rung"]] = row
    return by_pat


def ladder(by_pat):
    """Complexity rungs (graded ones with ops > 0), ordered by number of operations."""
    seen = {}
    for rows in by_pat.values():
        for rung, r in rows.items():
            if r["ops"] > 0:
                seen[rung] = r["ops"]
    return [k for k, _ in sorted(seen.items(), key=lambda kv: kv[1])]


def svg(body, label):
    return (f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:auto" role="img" aria-label="{label}">\n'
            f'{body}\n</svg>\n')


def axes(ymax, yfmt, xlabels, xs, ylabel):
    out = [f'<line x1="{X0}" y1="{Y1}" x2="{X1}" y2="{Y1}" stroke="{AXIS}"/>',
           f'<line x1="{X0}" y1="{Y0}" x2="{X0}" y2="{Y1}" stroke="{AXIS}"/>']
    for i in range(1, 5):
        v = ymax * i / 4
        y = Y1 - (Y1 - Y0) * i / 4
        out.append(f'<line x1="{X0}" y1="{y:.1f}" x2="{X1}" y2="{y:.1f}" stroke="{GRID}"/>')
        out.append(f'<text x="{X0 - 6}" y="{y + 4:.1f}" {TEXT} text-anchor="end">{yfmt(v)}</text>')
    for x, lab in zip(xs, xlabels):
        out.append(f'<text x="{x:.1f}" y="{Y1 + 16}" {TEXT} text-anchor="middle">{lab}</text>')
    out.append(f'<text x="{X0}" y="{Y0 - 8}" {TEXT}>{ylabel}</text>')
    return out


def nice(v):
    for step in (1, 2, 2.5, 5, 10, 20, 25, 50, 100):
        if v <= step * 4:
            return step * 4
    return v


def fig1(by_pat, rungs, pats):
    """LLM calls per run vs. rung (mean ± σ)."""
    ymax = nice(max(by_pat[p][r]["llm_calls_mean"] + by_pat[p][r]["llm_calls_sd"]
                    for p in pats for r in rungs if r in by_pat[p]))
    xs = [X0 + 30 + i * (X1 - X0 - 60) / max(1, len(rungs) - 1) for i in range(len(rungs))]
    y = lambda v: Y1 - (Y1 - Y0) * v / ymax  # noqa: E731
    out = axes(ymax, lambda v: f"{v:.0f}", [f"{r} · {int(by_pat[pats[0]][r]['ops'])} ops" for r in rungs], xs,
               "llamadas al LLM por corrida (media ± σ)")
    ends = []
    for p in pats:
        pts = [(x, by_pat[p][r]) for x, r in zip(xs, rungs) if r in by_pat[p]]
        c = COLOR.get(p, "var(--muted)")
        out.append('<polyline fill="none" stroke="{}" stroke-width="3" points="{}"/>'.format(
            c, " ".join(f"{x:.1f},{y(r['llm_calls_mean']):.1f}" for x, r in pts)))
        for x, r in pts:
            m, s = r["llm_calls_mean"], r["llm_calls_sd"]
            out.append(f'<line x1="{x:.1f}" y1="{y(m + s):.1f}" x2="{x:.1f}" y2="{y(max(0, m - s)):.1f}" stroke="{c}" stroke-width="1.5"/>')
            out.append(f'<circle cx="{x:.1f}" cy="{y(m):.1f}" r="4" fill="{c}"/>')
        ends.append((y(pts[-1][1]["llm_calls_mean"]), pts[-1][0], c, pts[-1][1]["llm_calls_mean"]))
    # end-of-line labels, nudged apart when they would overlap (half-up rounding)
    ends.sort()
    for i in range(1, len(ends)):
        if ends[i][0] - ends[i - 1][0] < 13:
            ends[i] = (ends[i - 1][0] + 13,) + ends[i][1:]
    for ly, lx, c, v in ends:
        out.append(f'<text x="{lx + 8:.1f}" y="{ly + 4:.1f}" fill="{c}" '
                   f'font-family="Roboto Mono" font-size="11">{int(v + 0.5)}</text>')
    return svg("\n".join(out), "Llamadas al LLM por corrida según la complejidad")


def bars(by_pat, rungs, pats, value, ymax, yfmt, ylabel, label):
    group = (X1 - X0) / len(rungs)
    bw = min(34, (group - 18) / len(pats))
    y = lambda v: Y1 - (Y1 - Y0) * v / ymax  # noqa: E731
    centers = [X0 + group * (i + .5) for i in range(len(rungs))]
    out = axes(ymax, yfmt, [f"{r}" for r in rungs], centers, ylabel)
    for i, r in enumerate(rungs):
        for j, p in enumerate(pats):
            if r not in by_pat[p]:
                continue
            v = value(by_pat[p][r])
            x = centers[i] - bw * len(pats) / 2 + j * bw
            shown = min(v, ymax)  # values above the axis are clipped and labelled
            out.append(f'<rect x="{x:.1f}" y="{y(shown):.1f}" width="{bw - 3:.1f}" height="{Y1 - y(shown):.1f}" '
                       f'rx="2" fill="{COLOR.get(p, "var(--muted)")}"/>')
            if v > ymax:
                out.append(f'<text x="{x + (bw - 3) / 2:.1f}" y="{Y0 + 14}" fill="#ffffff" '
                           f'font-family="Roboto Mono" font-size="10" text-anchor="middle">{yfmt(v)}↑</text>')
    return svg("\n".join(out), label)


def cv(r):
    return 100.0 * r["cost_usd_sd"] / r["cost_usd_mean"] if r["cost_usd_mean"] > 0 else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--patterns", default="multiagent,workflow,single_structured")
    args = ap.parse_args()

    by_pat = load(args.csv)
    pats = [p for p in args.patterns.split(",") if p in by_pat]
    rungs = ladder(by_pat)
    out = Path(args.outdir)

    (out / "svg1_escalado.svg").write_text(fig1(by_pat, rungs, pats))

    cv_max = min(100, nice(max(cv(by_pat[p][r]) for p in pats for r in rungs if r in by_pat[p]) or 1))
    (out / "svg2_predictibilidad.svg").write_text(bars(
        by_pat, rungs, pats, cv, cv_max, lambda v: f"{v:.0f}%",
        "variación del costo entre corridas (σ / media)", "Coeficiente de variación del costo por peldaño"))

    coord_pats = [p for p in pats if p in ("multiagent", "workflow")]
    c_max = nice(max(by_pat[p][r]["transfers_mean"] for p in coord_pats for r in rungs if r in by_pat[p]) or 1)
    (out / "svg3_coordinacion.svg").write_text(bars(
        by_pat, rungs, coord_pats, lambda r: r["transfers_mean"], c_max, lambda v: f"{v:.0f}",
        "transfer_to_agent por corrida (media)", "Llamadas de coordinación por peldaño"))

    print("legend:", ", ".join(f"{LABEL.get(p, p)}={COLOR.get(p)}" for p in pats))
    print(f"wrote {out}/svg1_escalado.svg, svg2_predictibilidad.svg, svg3_coordinacion.svg")


if __name__ == "__main__":
    main()
