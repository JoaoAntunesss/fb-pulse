"""Configuration loading and validation. Keys are referenced by path and never sent to the browser."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(Exception):
    pass


@dataclass
class Project:
    name: str
    urls: list[str] = field(default_factory=list)
    service_account: Path | None = None
    ga4_property_id: str = ""
    errors_collection: str = ""


@dataclass
class Config:
    projects: list[Project]
    fast_seconds: int = 60  # uptime checks
    slow_seconds: int = 600  # users, active users, errors (keeps Firebase reads tiny)
    port: int = 8787
    base: Path = Path(".")


_URL = re.compile(r"^https?://[^\s]+$")
_COLLECTION = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_PROPERTY = re.compile(r"^\d{4,15}$")


def load(path) -> Config:
    p = Path(path)
    if not p.is_file():
        raise ConfigError(
            f"Config file not found: {p}\nCopy config.example.json to config.json and edit it (see SETUP.md), "
            "or run with --demo to see the dashboard with fake data."
        )
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"{p} is not valid JSON: {e}")
    base = p.parent
    projects = []
    for i, item in enumerate(raw.get("projects", [])):
        name = str(item.get("name", "")).strip()
        if not name:
            raise ConfigError(f"projects[{i}] needs a 'name'.")
        urls = list(item.get("urls", []))
        for u in urls:
            if not isinstance(u, str) or not _URL.match(u):
                raise ConfigError(f"{name}: '{u}' is not a valid http(s) URL.")
        sa = item.get("service_account")
        sa_path = None
        if sa:
            sa_path = (base / sa).resolve()
            if not sa_path.is_file():
                raise ConfigError(
                    f"{name}: service account file not found: {sa_path}\n"
                    "Download it from Firebase console > Project settings > Service accounts and save it there."
                )
        prop = str(item.get("ga4_property_id", "") or "")
        if prop and not _PROPERTY.match(prop):
            raise ConfigError(f"{name}: ga4_property_id must be the numeric property ID (e.g. 123456789).")
        col = str(item.get("errors_collection", "") or "")
        if col and not _COLLECTION.match(col):
            raise ConfigError(f"{name}: errors_collection must be a simple collection name (letters, digits, _ -).")
        if (prop or col) and not sa_path:
            raise ConfigError(f"{name}: ga4_property_id / errors_collection need a 'service_account'.")
        projects.append(Project(name, urls, sa_path, prop, col))
    if not projects:
        raise ConfigError("No projects in the config. Add at least one under \"projects\".")
    return Config(
        projects,
        max(15, int(raw.get("fast_seconds", 60))),
        max(120, int(raw.get("slow_seconds", 600))),
        int(raw.get("port", 8787)),
        base,
    )


def demo_config() -> Config:
    """Built-in fake projects for --demo (no files, no network)."""
    return Config([
        Project("Garage log (Android)", ["https://demo.invalid/garage"], None, "100000001", "app_errors"),
        Project("Freezer (Android)", ["https://demo.invalid/freezer-slow"], None, "100000002", "app_errors"),
        Project("License tool (web)", ["https://demo.invalid/licenses", "https://demo.invalid/api-down"], None, "", "app_errors"),
        Project("Landing page", ["https://demo.invalid/landing"], None, "", ""),
    ], 4, 6, 8787, Path("."))
