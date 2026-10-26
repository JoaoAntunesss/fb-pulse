"""The checks. Each returns a plain dict and never raises: a failing source shows its error on the card."""
from __future__ import annotations

import time
import urllib.error
import urllib.request

SLOW_MS = 2000


def check_url(url: str, timeout: float = 8.0) -> dict:
    """GET the URL. Up = any answer below 500 (a 401/404 still means the server is alive)."""
    req = urllib.request.Request(url, headers={"User-Agent": "fb-pulse/1.0"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception as e:  # noqa: BLE001 - DNS, timeout, TLS...
        return {"url": url, "ok": False, "code": None, "ms": None, "error": str(e)[:120]}
    ms = int((time.time() - t0) * 1000)
    return {"url": url, "ok": code < 500, "code": code, "ms": ms, "error": "" if code < 500 else f"HTTP {code}"}


class FirebaseSources:
    """Lazy, optional access to a project's Firebase data. Needs the 'firebase-admin' package."""

    def __init__(self, project):
        self.project = project
        self._app = None
        self._ga = None

    def _firebase_app(self):
        if self._app is None:
            import firebase_admin
            from firebase_admin import credentials

            cred = credentials.Certificate(str(self.project.service_account))
            self._app = firebase_admin.initialize_app(cred, name=f"pulse-{self.project.name}")
        return self._app

    def total_users(self, cap: int = 200_000) -> dict:
        try:
            from firebase_admin import auth

            n = 0
            page = auth.list_users(app=self._firebase_app())
            while page:
                n += len(page.users)
                if n >= cap:
                    break
                page = page.get_next_page()
            return {"value": n, "error": ""}
        except Exception as e:  # noqa: BLE001
            return {"value": None, "error": _short(e)}

    def active_users(self) -> dict:
        try:
            from google.analytics.data_v1beta import BetaAnalyticsDataClient
            from google.analytics.data_v1beta.types import Metric, RunRealtimeReportRequest

            if self._ga is None:
                self._ga = BetaAnalyticsDataClient.from_service_account_file(str(self.project.service_account))
            resp = self._ga.run_realtime_report(RunRealtimeReportRequest(
                property=f"properties/{self.project.ga4_property_id}", metrics=[Metric(name="activeUsers")]))
            value = 0
            if resp.rows:
                value = int(resp.rows[0].metric_values[0].value)
            elif getattr(resp, "totals", None):
                value = int(resp.totals[0].metric_values[0].value)
            return {"value": value, "error": ""}
        except Exception as e:  # noqa: BLE001
            return {"value": None, "error": _short(e)}

    def errors_24h(self, latest: int = 8) -> dict:
        """Count + latest entries of the errors collection. 1 count query + `latest` reads per poll."""
        try:
            from datetime import datetime, timedelta, timezone

            from firebase_admin import firestore
            from google.cloud.firestore_v1.base_query import FieldFilter

            db = firestore.client(app=self._firebase_app())
            col = db.collection(self.project.errors_collection)
            since = datetime.now(timezone.utc) - timedelta(hours=24)
            q = col.where(filter=FieldFilter("ts", ">=", since))
            count = q.count().get()[0][0].value
            rows = []
            for d in q.order_by("ts", direction=firestore.Query.DESCENDING).limit(latest).stream():
                x = d.to_dict() or {}
                ts = x.get("ts")
                rows.append({
                    "ts": ts.isoformat() if hasattr(ts, "isoformat") else "",
                    "app": str(x.get("app", ""))[:60],
                    "level": str(x.get("level", "error"))[:20],
                    "message": str(x.get("message", ""))[:300],
                })
            return {"count": int(count), "latest": rows, "error": ""}
        except Exception as e:  # noqa: BLE001
            return {"count": None, "latest": [], "error": _short(e)}


def _short(e: Exception) -> str:
    text = str(e).replace("\n", " ")
    return (type(e).__name__ + ": " + text)[:200]
