#!/usr/bin/env python3
"""
Generate local streak and activity SVGs from GitHub's GraphQL contribution
calendar. Uses only the Python standard library.

Environment:
    GITHUB_TOKEN  - token supplied automatically by GitHub Actions
    GITHUB_LOGIN  - GitHub username
    OUTPUT_DIR    - output directory, defaults to ".generated"
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo


GRAPHQL_URL = "https://api.github.com/graphql"

QUERY = r"""
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    name
    login
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          firstDay
          contributionDays {
            date
            contributionCount
            contributionLevel
            weekday
          }
        }
      }
    }
  }
}
"""


def github_graphql(token: str, variables: dict) -> dict:
    payload = json.dumps({"query": QUERY, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Nek1tt-profile-action",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.load(response)

    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"], ensure_ascii=False))

    user = data.get("data", {}).get("user")
    if not user:
        raise RuntimeError("GitHub user was not returned by GraphQL")

    return user


def parse_calendar(user: dict):
    cal = user["contributionsCollection"]["contributionCalendar"]
    days = []
    weeks = cal["weeks"]

    for week_index, week in enumerate(weeks):
        for day in week["contributionDays"]:
            days.append(
                {
                    "date": dt.date.fromisoformat(day["date"]),
                    "count": int(day["contributionCount"]),
                    "level": day["contributionLevel"],
                    "weekday": int(day["weekday"]),
                    "week": week_index,
                }
            )

    days.sort(key=lambda d: d["date"])
    return int(cal["totalContributions"]), days, weeks


def calculate_streaks(days, today):
    by_date = {d["date"]: d["count"] for d in days}

    # Today is still in progress. If it has no contribution yet,
    # calculate the current streak through yesterday.
    cursor = today
    if by_date.get(today, 0) == 0:
        cursor -= dt.timedelta(days=1)

    current = 0
    while by_date.get(cursor, 0) > 0:
        current += 1
        cursor -= dt.timedelta(days=1)

    longest = 0
    running = 0
    for item in days:
        if item["count"] > 0:
            running += 1
            longest = max(longest, running)
        else:
            running = 0

    active_days = sum(1 for d in days if d["count"] > 0)
    return current, longest, active_days


def svg_text(x, y, text, size=16, weight=400, anchor="start", fill="#c9d1d9"):
    return (
        f'<text x="{x}" y="{y}" text-anchor="{anchor}" '
        f'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{fill}">{escape(str(text))}</text>'
    )


def generate_streak_svg(login, total, current, longest, active_days):
    width, height = 900, 178
    col_x = [150, 450, 750]
    labels = ["Current streak", "Longest streak", "Contributions · 365d"]
    values = [f"{current} days", f"{longest} days", f"{total:,}"]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" rx="10" fill="#0d1117" stroke="#30363d"/>',
        svg_text(24, 34, f"Contribution streak · @{login}", 18, 600),
    ]

    for x, label, value in zip(col_x, labels, values):
        parts.append(svg_text(x, 86, value, 28, 700, "middle", "#58a6ff"))
        parts.append(svg_text(x, 112, label, 13, 400, "middle", "#8b949e"))

    parts.append(svg_text(24, 154, f"Active days in the last 365 days: {active_days}", 12, 400, "start", "#8b949e"))
    parts.append("</svg>")
    return "\n".join(parts)


def generate_activity_svg(login, total, days):
    width, height = 900, 190
    left, top = 28, 62
    cell, gap = 11, 3

    level_colors = {
        "NONE": "#161b22",
        "FIRST_QUARTILE": "#0e4429",
        "SECOND_QUARTILE": "#006d32",
        "THIRD_QUARTILE": "#26a641",
        "FOURTH_QUARTILE": "#39d353",
    }

    max_week = max((d["week"] for d in days), default=0)
    available_width = width - left - 28
    natural_width = (max_week + 1) * (cell + gap)
    shift = max(0, available_width - natural_width)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" rx="10" fill="#0d1117" stroke="#30363d"/>',
        svg_text(24, 33, f"Contribution activity · @{login}", 18, 600),
        svg_text(width - 24, 33, f"{total:,} contributions / 365 days", 13, 400, "end", "#8b949e"),
    ]

    for d in days:
        x = left + shift + d["week"] * (cell + gap)
        y = top + d["weekday"] * (cell + gap)
        color = level_colors.get(d["level"], "#161b22")
        title = f'{d["date"].isoformat()}: {d["count"]} contribution{"s" if d["count"] != 1 else ""}'
        parts.append(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{color}">'
            f"<title>{escape(title)}</title></rect>"
        )

    # Compact legend.
    parts.append(svg_text(width - 164, height - 20, "Less", 11, 400, "start", "#8b949e"))
    lx = width - 126
    for level in ["NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE"]:
        parts.append(
            f'<rect x="{lx}" y="{height - 31}" width="10" height="10" rx="2" fill="{level_colors[level]}"/>'
        )
        lx += 14
    parts.append(svg_text(width - 24, height - 20, "More", 11, 400, "end", "#8b949e"))
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    token = os.environ.get("GITHUB_TOKEN")
    login = os.environ.get("GITHUB_LOGIN")
    out_dir = Path(os.environ.get("OUTPUT_DIR", ".generated"))
    timezone_name = os.environ.get("PROFILE_TIMEZONE", "Europe/Berlin")

    if not token:
        raise SystemExit("GITHUB_TOKEN is missing")
    if not login:
        raise SystemExit("GITHUB_LOGIN is missing")

    now = dt.datetime.now(dt.timezone.utc)
    local_today = dt.datetime.now(ZoneInfo(timezone_name)).date()
    start = now - dt.timedelta(days=364)

    user = github_graphql(
        token,
        {
            "login": login,
            "from": start.isoformat().replace("+00:00", "Z"),
            "to": now.isoformat().replace("+00:00", "Z"),
        },
    )

    total, days, _weeks = parse_calendar(user)
    current, longest, active_days = calculate_streaks(days, local_today)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "streak.svg").write_text(
        generate_streak_svg(login, total, current, longest, active_days),
        encoding="utf-8",
    )
    (out_dir / "activity.svg").write_text(
        generate_activity_svg(login, total, days),
        encoding="utf-8",
    )

    print(
        f"Generated contribution cards: total={total}, "
        f"current={current}, longest={longest}, active_days={active_days}"
    )


if __name__ == "__main__":
    main()
