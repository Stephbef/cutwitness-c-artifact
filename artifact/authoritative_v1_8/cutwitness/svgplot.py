"""Dependency-free deterministic SVG figures."""
from __future__ import annotations
from typing import Dict, List, Tuple

W, H, PAD = 640, 400, 56


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _frame(title, label):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="sans-serif" font-size="12">',
            f'<rect width="{W}" height="{H}" fill="white"/>', f'<text x="{PAD}" y="22" font-size="14">{_esc(title)}</text>',
            f'<text x="{PAD}" y="{H - 8}" fill="#a00">{_esc(label)}</text>',
            f'<line x1="{PAD}" y1="{H - PAD}" x2="{W - 16}" y2="{H - PAD}" stroke="black"/>',
            f'<line x1="{PAD}" y1="{H - PAD}" x2="{PAD}" y2="36" stroke="black"/>']


COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf", "#000000", "#aec7e8"]


def steps(title: str, series: Dict[str, List[Tuple[float, float]]], xmax: float, label: str) -> str:
    out = _frame(title, label); ph = H - PAD - 36; pw = W - 16 - PAD
    for i, (name, pts) in enumerate(sorted(series.items())):
        c = COLORS[i % len(COLORS)]; path = []
        prev = 1.0; px = PAD
        for x, y in pts:
            X = PAD + pw * min(x, xmax) / max(xmax, 1e-9)
            path.append(f"{px:.1f},{36 + ph * (1 - prev):.1f} {X:.1f},{36 + ph * (1 - prev):.1f} {X:.1f},{36 + ph * (1 - y):.1f}")
            px, prev = X, y
        path.append(f"{px:.1f},{36 + ph * (1 - prev):.1f} {PAD + pw:.1f},{36 + ph * (1 - prev):.1f}")
        out.append(f'<polyline fill="none" stroke="{c}" stroke-width="2" points="{" ".join(path)}"/>')
        out.append(f'<text x="{W - 200}" y="{50 + 14 * i}" fill="{c}">{_esc(name)}</text>')
    out.append("</svg>")
    return "\n".join(out)


def bars(title: str, values: Dict[str, float], label: str) -> str:
    out = _frame(title, label); items = sorted(values.items()); n = max(len(items), 1)
    vmax = max([v for _, v in items] + [1e-9]); ph = H - PAD - 36; bw = (W - 16 - PAD) / n
    for i, (k, v) in enumerate(items):
        h = ph * v / vmax; x = PAD + i * bw + 4
        out.append(f'<rect x="{x:.1f}" y="{H - PAD - h:.1f}" width="{bw - 8:.1f}" height="{h:.1f}" fill="{COLORS[i % len(COLORS)]}"/>')
        out.append(f'<text x="{x:.1f}" y="{H - PAD + 14}" font-size="9" transform="rotate(20 {x:.1f},{H - PAD + 14})">{_esc(k)}</text>')
        out.append(f'<text x="{x:.1f}" y="{H - PAD - h - 3:.1f}" font-size="10">{v:g}</text>')
    out.append("</svg>")
    return "\n".join(out)
