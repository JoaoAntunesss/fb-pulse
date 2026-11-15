"""Regista, várias vezes por dia, quantas vezes cada APK/instalador foi descarregado no GitHub.

O GitHub só guarda o contador atual de cada ficheiro. Quando um ficheiro é substituído (como o
"latest" do AWplayer, que é carregado de novo a cada versão), o contador volta a zero. Por isso
guardamos uma linha por ficheiro e por dia em history.csv e somamos o máximo que cada ficheiro
(asset_id) chegou a ter: assim os downloads antigos não se perdem.

python downloads/track.py            # junta o dia de hoje a history.csv e refaz summary.md
python downloads/track.py --dry-run  # só mostra, não escreve
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
HIST = HERE / "history.csv"
SUMMARY = HERE / "summary.md"
FIELDS = ["date", "app", "tag", "asset", "asset_id", "count"]


def api(path: str):
    req = urllib.request.Request("https://api.github.com" + path, headers={"Accept": "application/vnd.github+json", "User-Agent": "app-downloads"})
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def snapshot(cfg: dict, today: str) -> list[dict]:
    rows = []
    for app in cfg["apps"]:
        page = 1
        while True:
            rels = api(f"/repos/{cfg['owner']}/{app['repo']}/releases?per_page=100&page={page}")
            for rel in rels:
                for a in rel.get("assets", []):
                    if a["name"] in cfg.get("skip_assets", []):
                        continue
                    rows.append({"date": today, "app": app["name"], "tag": rel["tag_name"], "asset": a["name"], "asset_id": str(a["id"]), "count": str(a["download_count"])})
            if len(rels) < 100:
                break
            page += 1
    return rows


def load() -> list[dict]:
    if not HIST.exists():
        return []
    with HIST.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def totals_by_day(rows: list[dict]) -> dict[str, dict[str, int]]:
    """Para cada dia, o total acumulado de cada app = soma do máximo visto (até esse dia) de cada ficheiro."""
    best: dict[tuple[str, str], int] = {}
    out: dict[str, dict[str, int]] = {}
    for day in sorted({r["date"] for r in rows}):
        for r in rows:
            if r["date"] == day:
                k = (r["app"], r["asset_id"])
                best[k] = max(best.get(k, 0), int(r["count"]))
        tot: dict[str, int] = defaultdict(int)
        for (app, _), n in best.items():
            tot[app] += n
        out[day] = dict(tot)
    return out


def write_summary(rows: list[dict], apps: list[str]) -> None:
    days = totals_by_day(rows)
    order = sorted(days)
    last = days[order[-1]] if order else {}
    lines = ["# Downloads das apps", "", f"Atualizado a {order[-1] if order else '-'} (contagem do GitHub, de 2 em 2 horas).", "",
             "| App | Total | Últimos 7 dias | Últimos 30 dias |", "|---|---:|---:|---:|"]

    def ago(n: int) -> dict[str, int]:
        ref = (dt.date.fromisoformat(order[-1]) - dt.timedelta(days=n)).isoformat() if order else ""
        prev = [d for d in order if d <= ref]
        return days[prev[-1]] if prev else {}

    w, m = ago(7), ago(30)
    for a in apps:
        t = last.get(a, 0)
        d7 = f"+{t - w.get(a, 0)}" if w else "-"
        d30 = f"+{t - m.get(a, 0)}" if m else "-"
        lines.append(f"| {a} | {t} | {d7} | {d30} |")
    lines += ["", "Inclui os teus próprios downloads e as atualizações feitas dentro das apps.", "",
              "## Por dia", "", "| Dia | " + " | ".join(apps) + " |", "|---|" + "---:|" * len(apps)]
    for d in reversed(order[-60:]):
        lines.append(f"| {d} | " + " | ".join(str(days[d].get(a, 0)) for a in apps) + " |")
    SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    cfg = json.loads((HERE / "apps.json").read_text(encoding="utf-8"))
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    new = snapshot(cfg, today)
    old = load()
    # Corre várias vezes por dia: um ficheiro substituído entretanto (outro asset_id) fica guardado,
    # e para o mesmo ficheiro fica o maior número visto hoje.
    seen = {r["asset_id"]: r for r in old if r["date"] == today}
    for r in new:
        if r["asset_id"] in seen and int(seen[r["asset_id"]]["count"]) > int(r["count"]):
            continue
        seen[r["asset_id"]] = r
    rows = [r for r in old if r["date"] != today] + list(seen.values())
    apps = [a["name"] for a in cfg["apps"]]
    if "--dry-run" in sys.argv:
        print(json.dumps(totals_by_day(rows).get(today, {}), ensure_ascii=False))
        return 0
    with HIST.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=FIELDS)
        wr.writeheader()
        wr.writerows(sorted(rows, key=lambda r: (r["date"], r["app"], r["tag"], r["asset"])))
    write_summary(rows, apps)
    print(json.dumps(totals_by_day(rows)[today], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
