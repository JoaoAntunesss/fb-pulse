"""One-shot collector for the hosted (GitHub Pages) version of FB Pulse.

python collect.py --out site            # real data: config.json + keys/ (CI writes them from secrets)
python collect.py --demo --out site     # fake data, for trying the hosted page locally

Writes <out>/index.html, app.js, app.css and data.json. History is carried over from the previous
published data.json (env PREV_URL), so the sparklines keep growing between runs.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from pulse import config as cfg  # noqa: E402
from pulse.monitor import HIST, Monitor  # noqa: E402

SAMPLES = 3       # uptime checks per run
SAMPLE_GAP = 15   # seconds between them


def write_keys(env: str | None, dest: Path) -> None:
    """PULSE_KEYS is one secret holding {"file.json": {...service account...}, ...}."""
    if not env:
        return
    dest.mkdir(exist_ok=True)
    for name, body in json.loads(env).items():
        if "/" in name or "\\" in name or not name.endswith(".json"):
            raise SystemExit(f"Bad key file name in PULSE_KEYS: {name}")
        (dest / name).write_text(json.dumps(body), encoding="utf-8")


def fetch_previous(url: str | None) -> dict:
    if not url:
        return {}
    try:
        with urllib.request.urlopen(url + "?t=" + str(int(time.time())), timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - first run, or the site is not up yet
        return {}


def seed_history(mon: Monitor, prev: dict) -> None:
    for p in prev.get("projects", []):
        st = mon.state.get(p.get("name"))
        if not st:
            continue
        for u in p.get("urls", []):
            s = st["urls"].get(u.get("url"))
            if s:
                s["ms"].extend(u.get("ms", [])[-HIST:])
                s["ok"].extend(u.get("ok", [])[-HIST:])
        st["active"]["hist"].extend(p.get("active", {}).get("hist", [])[-HIST:])


def redact(snap: dict, show_errors: bool) -> dict:
    """The hosted page is public: by default only error COUNTS are published, not their messages."""
    if not show_errors:
        for p in snap["projects"]:
            p["errors"]["latest"] = []
    return snap


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "site"))
    args = ap.parse_args()
    out = Path(args.out)

    if not args.demo:
        if os.environ.get("PULSE_CONFIG"):
            Path(args.config).write_text(os.environ["PULSE_CONFIG"], encoding="utf-8")
        write_keys(os.environ.get("PULSE_KEYS"), ROOT / "keys")
    try:
        conf = cfg.demo_config() if args.demo else cfg.load(args.config)
    except cfg.ConfigError as e:
        raise SystemExit(str(e))
    try:
        show_errors = bool(json.loads(Path(args.config).read_text()).get("public_error_messages")) if not args.demo else True
    except Exception:  # noqa: BLE001
        show_errors = False

    mon = Monitor(conf, demo=args.demo)
    seed_history(mon, fetch_previous(os.environ.get("PREV_URL")))
    for i in range(SAMPLES):
        mon.poll_fast()
        if i < SAMPLES - 1 and not args.demo:
            time.sleep(SAMPLE_GAP)
    mon.poll_slow()
    snap = redact(mon.snapshot(), show_errors)

    out.mkdir(parents=True, exist_ok=True)
    for f in ("index.html", "app.js", "app.css"):
        shutil.copyfile(ROOT / "pulse" / "static" / f, out / f)
    html = (out / "index.html").read_text(encoding="utf-8")
    if 'name="pulse-data"' not in html:
        html = html.replace("<title>", '<meta name="pulse-data" content="data.json">\n<meta name="robots" content="noindex">\n<title>', 1)
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / "data.json").write_text(json.dumps(snap), encoding="utf-8")
    print(f"Wrote {out} ({len(snap['projects'])} projects)")


if __name__ == "__main__":
    main()
