"""
bench_report.py — Agrega results.jsonl en la tabla comparativa
(patrón × peldaño -> llamadas, tokens in/out, costo, wall-clock) con media ± σ,
más el desglose del "impuesto de coordinación" (transfers vs. updates).

Uso:
    .venv/bin/python bench_report.py                 # tabla a stdout
    .venv/bin/python bench_report.py --csv out.csv   # además exporta CSV para graficar

La σ (población) NO es adorno: el ancho de las barras de error es tu segunda
slide estrella. Espera ver al multi-agente con σ visiblemente más gorda.
"""

import argparse
import csv
import json
import statistics as st
from collections import defaultdict


def agg(vals):
    m = st.mean(vals) if vals else 0.0
    s = st.pstdev(vals) if len(vals) > 1 else 0.0
    return m, s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--infile", default="benchmark/results.jsonl")
    ap.add_argument("--csv", default=None)
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.infile, encoding="utf-8")]
    cells = defaultdict(list)
    for r in rows:
        cells[(r["pattern"], r["rung"], r["ops"])].append(r)

    hdr = (f'{"patrón":10} {"peld":4} {"ops":>3} {"llamadas":>12} '
           f'{"in_tok":>14} {"out_tok":>13} {"costo_usd":>17} '
           f'{"wall_s":>12} {"transf":>8} {"updt":>6} {"ok%":>5}')
    print(hdr)
    print("-" * len(hdr))

    export = []
    for key in sorted(cells, key=lambda k: (k[0], k[2])):  # ordena por patrón, luego por ops
        pat, rung, ops = key
        g = cells[key]

        c_m, c_s = agg([r["llm_calls"] for r in g])
        i_m, i_s = agg([r["in_tok"] for r in g])
        o_m, o_s = agg([r["out_tok"] for r in g])
        d_m, d_s = agg([r["cost_usd"] for r in g])
        w_m, w_s = agg([r["wall_s"] for r in g])
        # Calculator: transfer_to_agent vs. update_expression. Examples: coordination vs. work tool calls.
        if g[0].get("example", "calculator") == "calculator":
            tr_m, _ = agg([r["tool_calls"].get("transfer_to_agent", 0) for r in g])
            up_m, _ = agg([r["tool_calls"].get("update_expression", 0) for r in g])
        else:
            tr_m, _ = agg([r["coordination_calls"] for r in g])
            up_m, _ = agg([r["work_calls"] for r in g])

        graded = [r["correct"] for r in g if r["correct"] is not None]
        okp = 100 * sum(graded) / len(graded) if graded else float("nan")

        print(f'{pat:10} {rung:4} {ops:>3} '
              f'{c_m:>6.1f}±{c_s:<4.1f} '
              f'{i_m:>8.0f}±{i_s:<4.0f} '
              f'{o_m:>7.0f}±{o_s:<4.0f} '
              f'${d_m:>9.5f}±{d_s:<5.5f} '
              f'{w_m:>6.1f}±{w_s:<4.1f} '
              f'{tr_m:>7.1f} {up_m:>5.1f} '
              f'{okp:>4.0f}')

        export.append({
            "pattern": pat, "rung": rung, "ops": ops,
            "llm_calls_mean": round(c_m, 2), "llm_calls_sd": round(c_s, 2),
            "in_tok_mean": round(i_m, 1), "in_tok_sd": round(i_s, 1),
            "out_tok_mean": round(o_m, 1), "out_tok_sd": round(o_s, 1),
            "cost_usd_mean": round(d_m, 6), "cost_usd_sd": round(d_s, 6),
            "wall_s_mean": round(w_m, 2), "wall_s_sd": round(w_s, 2),
            "transfers_mean": round(tr_m, 2), "updates_mean": round(up_m, 2),
            "ok_pct": round(okp, 1) if graded else "",
        })

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(export[0].keys()))
            w.writeheader()
            w.writerows(export)
        print(f"\nCSV escrito en {args.csv}")


if __name__ == "__main__":
    main()
