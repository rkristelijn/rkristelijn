#!/usr/bin/env python3
"""Regenerate README.md stats from live npm + GitHub data.

Source of truth: data/packages.json
Fills the block between <!-- STATS:START --> and <!-- STATS:END --> in README.md.

Usage:
    python3 scripts/update_stats.py            # update README.md in place
    python3 scripts/update_stats.py --check    # exit 1 if README would change (CI)

No third-party deps: stdlib urllib only. Works on macOS and Linux.
GITHUB_TOKEN (optional) raises the GitHub API rate limit.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "packages.json"
README = ROOT / "README.md"
START = "<!-- STATS:START -->"
END = "<!-- STATS:END -->"
UA = {"User-Agent": "rkristelijn-profile-stats"}


def get_json(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def npm_downloads_last_month(pkg: str) -> int:
    enc = urllib.parse.quote(pkg, safe="@/")
    try:
        return int(get_json(f"https://api.npmjs.org/downloads/point/last-month/{enc}").get("downloads", 0) or 0)
    except Exception:
        return 0


def github_stars(repo: str) -> int | None:
    headers = {}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    try:
        return int(get_json(f"https://api.github.com/repos/rkristelijn/{repo}", headers).get("stargazers_count", 0))
    except Exception:
        return None


def npm_badge(pkg: str) -> str:
    enc = urllib.parse.quote(pkg, safe="")
    link = "https://www.npmjs.com/package/" + urllib.parse.quote(pkg, safe="@/")
    return f"[![npm](https://img.shields.io/npm/dm/{enc}?label=%20&logo=npm)]({link})"


def fmt(n: int) -> str:
    return f"{n:,}"


def flupke_packages(data: dict) -> list[str]:
    """Discover the @flupkejs/* family live from the npm registry."""
    org = data["flupke"]["org"]
    try:
        res = get_json(
            "https://registry.npmjs.org/-/v1/search?"
            + urllib.parse.urlencode({"text": f"maintainer:rkristelijn", "size": 250})
        )
        return [o["package"]["name"] for o in res.get("objects", []) if o["package"]["name"].startswith(f"@{org}/")]
    except Exception:
        return []


def build_stats(data: dict) -> str:
    lines: list[str] = []
    total_dl = 0
    total_stars = 0

    for group in data["groups"]:
        lines.append(f"### {group['title']}")
        lines.append("")
        lines.append("| Package | Monthly downloads | Stars | What it does |")
        lines.append("|---|---|---|---|")
        for p in group["packages"]:
            dl = npm_downloads_last_month(p["npm"])
            st = github_stars(p["repo"])
            total_dl += dl
            if st:
                total_stars += st
            link = "https://www.npmjs.com/package/" + urllib.parse.quote(p["npm"], safe="@/")
            star_cell = f"★{st}" if st else "—"
            lines.append(f"| [`{p['npm']}`]({link}) | {fmt(dl)} | {star_cell} | {p['desc']} |")
        lines.append("")

    # flupke family (discovered live) — experimental, kept out of the headline total
    flupke = flupke_packages(data)
    flupke_dl = sum(npm_downloads_last_month(p) for p in flupke)
    org = data["flupke"]["org"]
    experimental = data["flupke"].get("status") == "experimental"
    heading = f"### [`@{org}/*`](https://www.npmjs.com/org/{org}) — native drop-in replacements"
    if experimental:
        heading += " ⚠️ experimental"
    lines.append(heading)
    lines.append("")
    if experimental:
        lines.append(
            "> **Work in progress — not yet proved.** A vibe-coded exploration that still "
            "needs validation (tests, benchmarks, API parity) before it's production-ready. "
            "Numbers below are informational, not a maturity claim."
        )
        lines.append("")
    lines.append(
        f"A family of **{len(flupke)} packages** — {fmt(flupke_dl)} downloads/month combined. "
        + data["flupke"]["note"]
    )
    lines.append("")

    proved_count = sum(len(g["packages"]) for g in data["groups"])
    header = (
        f"> **{fmt(total_dl)}** npm downloads/month across **{proved_count}** published tools · "
        f"**★{total_stars}** stars\n"
        f">\n"
        f"> Trusted in production by teams using **strapi-health-plugin** (Kubernetes health "
        f"checks for Strapi) and my **Next.js ESLint plugins** — the bulk of that traffic.\n"
        f">\n"
        f"> _Plus an experimental [`@{org}/*`](https://www.npmjs.com/org/{org}) family "
        f"({len(flupke)} packages) — work in progress, see below._\n"
    )
    return header + "\n" + "\n".join(lines)


def main() -> int:
    data = json.loads(DATA.read_text())
    stats = build_stats(data)
    text = README.read_text()
    if START not in text or END not in text:
        print(f"ERROR: markers {START} / {END} not found in README.md", file=sys.stderr)
        return 2
    pre = text.split(START)[0]
    post = text.split(END)[1]
    new = f"{pre}{START}\n{stats}\n{END}{post}"

    if "--check" in sys.argv:
        if new != text:
            print("README stats are stale — run scripts/update_stats.py")
            return 1
        print("README stats up to date.")
        return 0

    README.write_text(new)
    print("README.md stats updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
