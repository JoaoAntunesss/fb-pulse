"""Background polling and the JSON snapshot the dashboard reads."""
from __future__ import annotations

import json
import random
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

from .checks import SLOW_MS, FirebaseSources, check_url

HIST = 120  # samples kept per series


class Monitor:
    def __init__(self, config, demo: bool = False, history_file=None):
        self.config = config
        self.demo = demo
        self.history_file = history_file
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.state = {}
        for p in config.projects:
            self.state[p.name] = {
                "urls": {u: {"last": None, "ms": deque(maxlen=HIST), "ok": deque(maxlen=HIST)} for u in p.urls},
                "users": {"value": None, "error": "", "at": None},
                "active": {"value": None, "error": "", "hist": deque(maxlen=HIST), "at": None},
                "errors": {"count": None, "latest": [], "error": "", "at": None},
            }
        self.sources = {} if demo else {p.name: FirebaseSources(p) for p in config.projects if p.service_account}
        self._load_history()

    # ------------------------------------------------------------ polling
    def start(self) -> None:
        threading.Thread(target=self._loop, args=(self.poll_fast, self.config.fast_seconds), daemon=True).start()
        threading.Thread(target=self._loop, args=(self.poll_slow, self.config.slow_seconds), daemon=True).start()

    def _loop(self, fn, every: int) -> None:
        while not self.stop.is_set():
            try:
                fn()
            except Exception:  # noqa: BLE001 - a bad poll must never kill the loop
                pass
            self.stop.wait(every)

    def poll_fast(self) -> None:
        for p in self.config.projects:
            for url in p.urls:
                res = self._demo_url(url) if self.demo else check_url(url)
                with self.lock:
                    s = self.state[p.name]["urls"][url]
                    s["last"] = res
                    s["ms"].append(res["ms"])
                    s["ok"].append(1 if res["ok"] else 0)
        self._save_history()

    def poll_slow(self) -> None:
        for p in self.config.projects:
            if self.demo:
                self._demo_slow(p)
                continue
            src = self.sources.get(p.name)
            if not src:
                continue
            users = src.total_users()
            active = src.active_users() if p.ga4_property_id else None
            errors = src.errors_24h() if p.errors_collection else None
            now = datetime.now(timezone.utc).isoformat()
            with self.lock:
                st = self.state[p.name]
                st["users"] = {**users, "at": now}
                if active:
                    st["active"].update({"value": active["value"], "error": active["error"], "at": now})
                    if active["value"] is not None:
                        st["active"]["hist"].append(active["value"])
                if errors:
                    st["errors"] = {**errors, "at": now}

    # ------------------------------------------------------------ demo data (clearly fake)
    def _demo_url(self, url: str) -> dict:
        if "down" in url:
            return {"url": url, "ok": False, "code": None, "ms": None, "error": "demo: connection refused"}
        ms = int(random.gauss(2600 if "slow" in url else 180, 40))
        return {"url": url, "ok": True, "code": 200, "ms": max(40, ms), "error": ""}

    def _demo_slow(self, p) -> None:
        now = datetime.now(timezone.utc)
        with self.lock:
            st = self.state[p.name]
            seed = sum(map(ord, p.name))
            st["users"] = {"value": 800 + seed * 7 % 4000, "error": "", "at": now.isoformat()}
            if p.ga4_property_id:
                base = 12 + seed % 40
                v = max(0, int(random.gauss(base, 4)))
                st["active"].update({"value": v, "error": "", "at": now.isoformat()})
                st["active"]["hist"].append(v)
            if p.errors_collection:
                msgs = ["NullPointerException in CarListViewModel", "Firestore: PERMISSION_DENIED", "Timeout loading dashboard",
                        "JSONException: unexpected token"]
                n = (seed + int(now.minute)) % 9
                st["errors"] = {"count": n, "error": "", "at": now.isoformat(), "latest": [
                    {"ts": (now - timedelta(minutes=17 * i)).isoformat(), "app": p.name, "level": "error",
                     "message": "(demo) " + msgs[i % len(msgs)]} for i in range(min(n, 5))]}

    # ------------------------------------------------------------ snapshot
    def snapshot(self) -> dict:
        out = []
        with self.lock:
            for p in self.config.projects:
                st = self.state[p.name]
                urls, status = [], "unknown"
                for u, s in st["urls"].items():
                    last = s["last"]
                    oks = list(s["ok"])
                    urls.append({
                        "url": u, "last": last, "ms": list(s["ms"]), "ok": oks,
                        "uptime": round(100 * sum(oks) / len(oks), 1) if oks else None,
                    })
                lasts = [x["last"] for x in urls if x["last"]]
                if lasts:
                    if any(not l["ok"] for l in lasts):
                        status = "down"
                    elif any((l["ms"] or 0) > SLOW_MS for l in lasts):
                        status = "slow"
                    else:
                        status = "up"
                out.append({
                    "name": p.name, "status": status, "urls": urls,
                    "users": dict(st["users"]),
                    "active": {k: (list(v) if k == "hist" else v) for k, v in st["active"].items()},
                    "errors": dict(st["errors"]),
                    "configured": {"urls": bool(p.urls), "users": bool(p.service_account) or self.demo,
                                   "active": bool(p.ga4_property_id), "errors": bool(p.errors_collection)},
                })
        return {"generated": datetime.now(timezone.utc).isoformat(), "demo": self.demo, "projects": out,
                "fast_seconds": self.config.fast_seconds, "slow_seconds": self.config.slow_seconds}

    # ------------------------------------------------------------ history on disk (survives restarts)
    def _save_history(self) -> None:
        if not self.history_file or self.demo:
            return
        try:
            with self.lock:
                data = {name: {"urls": {u: {"ms": list(s["ms"]), "ok": list(s["ok"])} for u, s in st["urls"].items()},
                               "active": list(st["active"]["hist"])} for name, st in self.state.items()}
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            self.history_file.write_text(json.dumps(data), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    def _load_history(self) -> None:
        if not self.history_file or self.demo or not self.history_file.is_file():
            return
        try:
            data = json.loads(self.history_file.read_text(encoding="utf-8"))
            for name, d in data.items():
                st = self.state.get(name)
                if not st:
                    continue
                for u, s in d.get("urls", {}).items():
                    if u in st["urls"]:
                        st["urls"][u]["ms"].extend(s.get("ms", [])[-HIST:])
                        st["urls"][u]["ok"].extend(s.get("ok", [])[-HIST:])
                st["active"]["hist"].extend(d.get("active", [])[-HIST:])
        except Exception:  # noqa: BLE001
            pass
