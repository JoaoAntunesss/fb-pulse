"""FB Pulse — a local, free dashboard for the health of your Firebase projects.

python main.py            -> uses config.json
python main.py --demo     -> fake data, no keys needed
"""
import argparse
import sys
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pulse import config as cfg  # noqa: E402
from pulse.monitor import Monitor  # noqa: E402
from pulse.server import make_server  # noqa: E402

ROOT = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    ap.add_argument("--demo", action="store_true", help="show fake data (no keys needed)")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    try:
        conf = cfg.demo_config() if args.demo else cfg.load(args.config)
    except cfg.ConfigError as e:
        print(e)
        raise SystemExit(1)
    mon = Monitor(conf, demo=args.demo, history_file=None if args.demo else ROOT / "data" / "history.json")
    srv = make_server(mon, conf.port)
    mon.start()
    url = f"http://127.0.0.1:{conf.port}"
    print(f"FB Pulse running at {url}  (Ctrl+C to stop)" + ("  [DEMO DATA]" if args.demo else ""))
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        mon.stop.set()
        mon._save_history()


if __name__ == "__main__":
    main()
