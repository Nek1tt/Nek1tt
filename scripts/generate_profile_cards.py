#!/usr/bin/env python3
"""
Generate all local GitHub profile statistics cards.

Outputs:
    userstats.svg  - selected account/repository metrics + Top 5 languages
    streak.svg     - current streak, all-time longest streak, yearly contributions
    activity.svg   - GitHub-style contribution heatmap for the last 365 days

The script uses only the Python standard library and GitHub REST / GraphQL APIs.

Environment:
    GITHUB_TOKEN       GitHub Actions token
    GITHUB_LOGIN       GitHub username
    OUTPUT_DIR         output directory, default ".generated"
    PROFILE_TIMEZONE   timezone used for "today", default "Europe/Berlin"
"""

from __future__ import annotations

import datetime as dt
import json
import os
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo


GRAPHQL_URL = "https://api.github.com/graphql"
REST_ROOT = "https://api.github.com"

FONT = "-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"

BG = "#0d1117"
BORDER = "#30363d"
TEXT = "#c9d1d9"
MUTED = "#8b949e"
BLUE = "#58a6ff"
TRACK = "#21262d"

LANGUAGE_COLORS = {
    "C++": "#f34b7d",
    "Python": "#3572A5",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "Cuda": "#3A4E3A",
    "CUDA": "#3A4E3A",
    "C": "#555555",
    "Shell": "#89e051",
    "HTML": "#e34c26",
    "CSS": "#663399",
    "Jupyter Notebook": "#DA5B0B",
    "CMake": "#DA3434",
    "Dockerfile": "#384d54",
    "Java": "#b07219",
    "Rust": "#dea584",
    "Go": "#00ADD8",
}

CONTRIB_COLORS = {
    "NONE": "#161b22",
    "FIRST_QUARTILE": "#0e4429",
    "SECOND_QUARTILE": "#006d32",
    "THIRD_QUARTILE": "#26a641",
    "FOURTH_QUARTILE": "#39d353",
}


PROFILE_QUERY = r"""
query($login: String!) {
  user(login: $login) {
    login
    createdAt
    pullRequests(first: 1) {
      totalCount
    }
    repositoriesContributedTo(
      first: 1
      contributionTypes: [COMMIT, ISSUE, PULL_REQUEST, PULL_REQUEST_REVIEW]
      includeUserRepositories: false
    ) {
      totalCount
    }
  }
}
"""

CONTRIBUTIONS_QUERY = r"""
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
            contributionLevel
          }
        }
      }
    }
  }
}
"""


def iso_z(value: dt.datetime) -> str:
    value = value.astimezone(dt.timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def api_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Nek1tt-profile-action",
    }


def graphql(token: str, query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={**api_headers(token), "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        data = json.load(response)

    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"], ensure_ascii=False))

    return data["data"]


def rest_get(token: str, url: str):
    request = urllib.request.Request(url, headers=api_headers(token))
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.load(response), response.headers


def get_all_public_repositories(token: str, login: str) -> list[dict]:
    repositories = []
    page = 1

    while True:
        query = urllib.parse.urlencode(
            {
                "per_page": 100,
                "page": page,
                "type": "owner",
                "sort": "updated",
            }
        )
        url = f"{REST_ROOT}/users/{urllib.parse.quote(login)}/repos?{query}"
        rows, _headers = rest_get(token, url)

        if not rows:
            break

        repositories.extend(rows)

        if len(rows) < 100:
            break
        page += 1

    return repositories


def get_language_totals(token: str, repositories: list[dict]) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)

    # Forks are deliberately excluded: the language card should describe
    # code in the user's own public repositories.
    for repo in repositories:
        if repo.get("fork"):
            continue

        languages_url = repo.get("languages_url")
        if not languages_url:
            continue

        languages, _headers = rest_get(token, languages_url)
        for language, byte_count in languages.items():
            totals[language] += int(byte_count)

    return dict(totals)


def contribution_windows(start: dt.datetime, end: dt.datetime):
    """
    GitHub contributionsCollection accepts at most a one-year window.
    Use slightly smaller non-overlapping windows for safety.
    """
    cursor = start

    while cursor < end:
        window_end = min(
            cursor + dt.timedelta(days=364, hours=23, minutes=59, seconds=59),
            end,
        )
        yield cursor, window_end
        cursor = window_end + dt.timedelta(seconds=1)


def fetch_contribution_history(
    token: str,
    login: str,
    joined_at: dt.datetime,
    now: dt.datetime,
):
    days: dict[dt.date, dict] = {}
    total_commits = 0

    for start, end in contribution_windows(joined_at, now):
        data = graphql(
            token,
            CONTRIBUTIONS_QUERY,
            {"login": login, "from": iso_z(start), "to": iso_z(end)},
        )

        collection = data["user"]["contributionsCollection"]
        total_commits += int(collection["totalCommitContributions"])

        for week in collection["contributionCalendar"]["weeks"]:
            for day in week["contributionDays"]:
                date = dt.date.fromisoformat(day["date"])
                days[date] = {
                    "date": date,
                    "count": int(day["contributionCount"]),
                    "level": day["contributionLevel"],
                }

    return total_commits, days


def calculate_streaks(days: dict[dt.date, dict], today: dt.date):
    by_date = {date: row["count"] for date, row in days.items()}

    cursor = today
    if by_date.get(cursor, 0) == 0:
        cursor -= dt.timedelta(days=1)

    current = 0
    while by_date.get(cursor, 0) > 0:
        current += 1
        cursor -= dt.timedelta(days=1)

    longest = 0
    running = 0

    if by_date:
        first = min(by_date)
        last = min(today, max(by_date))
        cursor = first

        while cursor <= last:
            if by_date.get(cursor, 0) > 0:
                running += 1
                longest = max(longest, running)
            else:
                running = 0
            cursor += dt.timedelta(days=1)

    return current, longest


def svg_text(
    x,
    y,
    text,
    size=16,
    weight=400,
    anchor="start",
    fill=TEXT,
):
    return (
        f'<text x="{x}" y="{y}" text-anchor="{anchor}" '
        f'font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}">{escape(str(text))}</text>'
    )


def compact_number(value: int) -> str:
    return f"{value:,}"


def generate_stats_svg(
    joined_year: int,
    repo_count: int,
    commits_year: int,
    commits_total: int,
    prs_total: int,
    contributed_to: int,
    languages: dict[str, int],
):
    width, height = 900, 385
    xs = [150, 450, 750]

    metrics = [
        (str(joined_year), "Year Joined"),
        (compact_number(repo_count), "Repositories"),
        (compact_number(commits_year), "Commits · Year"),
        (compact_number(commits_total), "Total Commits"),
        (compact_number(prs_total), "Pull Requests"),
        (compact_number(contributed_to), "Contributed To"),
    ]

    total_language_bytes = sum(languages.values())
    top_languages = sorted(
        languages.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:5]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" '
        f'rx="10" fill="{BG}" stroke="{BORDER}"/>',
        svg_text(24, 35, "GitHub Stats", 20, 650),
    ]

    for index, (value, label) in enumerate(metrics):
        row = index // 3
        col = index % 3
        x = xs[col]
        value_y = 86 + row * 70
        label_y = 110 + row * 70

        parts.append(svg_text(x, value_y, value, 29, 700, "middle", BLUE))
        parts.append(svg_text(x, label_y, label, 13, 450, "middle", MUTED))

    parts.append(
        f'<line x1="24" y1="195" x2="876" y2="195" stroke="{BORDER}" />'
    )
    parts.append(svg_text(24, 226, "Top Languages", 17, 600))

    if not top_languages or total_language_bytes == 0:
        parts.append(svg_text(24, 266, "No language data available", 14, 400, fill=MUTED))
    else:
        label_x = 24
        bar_x = 155
        bar_width = 615
        percent_x = 876
        start_y = 247
        row_gap = 25

        for i, (language, byte_count) in enumerate(top_languages):
            percent = 100.0 * byte_count / total_language_bytes
            y = start_y + i * row_gap
            fill_width = max(3, bar_width * percent / 100.0)
            color = LANGUAGE_COLORS.get(language, "#8b949e")

            parts.append(svg_text(label_x, y + 11, language, 13, 500))
            parts.append(
                f'<rect x="{bar_x}" y="{y + 2}" width="{bar_width}" height="10" '
                f'rx="5" fill="{TRACK}"/>'
            )
            parts.append(
                f'<rect x="{bar_x}" y="{y + 2}" width="{fill_width:.2f}" height="10" '
                f'rx="5" fill="{color}"/>'
            )
            parts.append(
                svg_text(
                    percent_x,
                    y + 11,
                    f"{percent:.1f}%",
                    12,
                    500,
                    "end",
                    MUTED,
                )
            )

    parts.append("</svg>")
    return "\n".join(parts)


def generate_streak_svg(
    current: int,
    longest: int,
    yearly_contributions: int,
):
    width, height = 900, 145
    xs = [150, 450, 750]
    values = [
        f"{current} day" if current == 1 else f"{current} days",
        f"{longest} day" if longest == 1 else f"{longest} days",
        compact_number(yearly_contributions),
    ]
    labels = ["Current Streak", "Longest Streak", "Contributions · Year"]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" '
        f'rx="10" fill="{BG}" stroke="{BORDER}"/>',
        svg_text(24, 32, "Contribution Streak", 18, 600),
    ]

    for x, value, label in zip(xs, values, labels):
        parts.append(svg_text(x, 82, value, 27, 700, "middle", BLUE))
        parts.append(svg_text(x, 107, label, 13, 450, "middle", MUTED))

    parts.append("</svg>")
    return "\n".join(parts)


def sunday_before_or_equal(value: dt.date) -> dt.date:
    # Python: Monday=0 ... Sunday=6.
    return value - dt.timedelta(days=(value.weekday() + 1) % 7)


def generate_activity_svg(
    days: dict[dt.date, dict],
    today: dt.date,
):
    width, height = 900, 215
    left = 58
    top = 72
    cell = 11
    gap = 3

    visible_start = today - dt.timedelta(days=364)
    grid_start = sunday_before_or_equal(visible_start)
    grid_end = today

    total = sum(
        row["count"]
        for date, row in days.items()
        if visible_start <= date <= today
    )

    week_count = ((grid_end - grid_start).days // 7) + 1

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" '
        f'rx="10" fill="{BG}" stroke="{BORDER}"/>',
        svg_text(24, 31, "Contribution Activity", 18, 600),
        svg_text(
            876,
            31,
            f"{compact_number(total)} contributions in the last year",
            12,
            450,
            "end",
            MUTED,
        ),
    ]

    # Month labels: show the month near its first visible week.
    last_label_x = -999
    month_cursor = dt.date(visible_start.year, visible_start.month, 1)

    if month_cursor < visible_start:
        if month_cursor.month == 12:
            month_cursor = dt.date(month_cursor.year + 1, 1, 1)
        else:
            month_cursor = dt.date(month_cursor.year, month_cursor.month + 1, 1)

    while month_cursor <= today:
        week = (sunday_before_or_equal(month_cursor) - grid_start).days // 7
        x = left + week * (cell + gap)

        if x - last_label_x >= 34 and x < width - 35:
            parts.append(
                svg_text(
                    x,
                    57,
                    month_cursor.strftime("%b"),
                    11,
                    450,
                    fill=MUTED,
                )
            )
            last_label_x = x

        if month_cursor.month == 12:
            month_cursor = dt.date(month_cursor.year + 1, 1, 1)
        else:
            month_cursor = dt.date(
                month_cursor.year,
                month_cursor.month + 1,
                1,
            )

    # GitHub-style weekday labels.
    for weekday, label in [(1, "Mon"), (3, "Wed"), (5, "Fri")]:
        y = top + weekday * (cell + gap) + 10
        parts.append(svg_text(45, y, label, 10, 400, "end", MUTED))

    cursor = grid_start
    while cursor <= grid_end:
        week = (cursor - grid_start).days // 7
        github_weekday = (cursor.weekday() + 1) % 7  # Sunday=0
        x = left + week * (cell + gap)
        y = top + github_weekday * (cell + gap)

        in_visible_window = visible_start <= cursor <= today
        row = days.get(cursor)

        if in_visible_window:
            level = row["level"] if row else "NONE"
            count = row["count"] if row else 0
            color = CONTRIB_COLORS.get(level, CONTRIB_COLORS["NONE"])
            title = (
                f'{cursor.isoformat()}: {count} '
                f'contribution{"s" if count != 1 else ""}'
            )
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" '
                f'fill="{color}"><title>{escape(title)}</title></rect>'
            )

        cursor += dt.timedelta(days=1)

    legend_y = 190
    parts.append(svg_text(760, legend_y, "Less", 10, 400, "end", MUTED))
    lx = 770
    for level in [
        "NONE",
        "FIRST_QUARTILE",
        "SECOND_QUARTILE",
        "THIRD_QUARTILE",
        "FOURTH_QUARTILE",
    ]:
        parts.append(
            f'<rect x="{lx}" y="{legend_y - 10}" width="10" height="10" rx="2" '
            f'fill="{CONTRIB_COLORS[level]}"/>'
        )
        lx += 14
    parts.append(svg_text(876, legend_y, "More", 10, 400, "end", MUTED))

    parts.append("</svg>")
    return "\n".join(parts)


def main():
    token = os.environ.get("GITHUB_TOKEN")
    login = os.environ.get("GITHUB_LOGIN")
    output_dir = Path(os.environ.get("OUTPUT_DIR", ".generated"))
    timezone_name = os.environ.get("PROFILE_TIMEZONE", "Europe/Berlin")

    if not token:
        raise SystemExit("GITHUB_TOKEN is missing")
    if not login:
        raise SystemExit("GITHUB_LOGIN is missing")

    tz = ZoneInfo(timezone_name)
    local_now = dt.datetime.now(tz)
    today = local_now.date()
    now_utc = dt.datetime.now(dt.timezone.utc)

    profile = graphql(token, PROFILE_QUERY, {"login": login})["user"]
    joined_at = dt.datetime.fromisoformat(
        profile["createdAt"].replace("Z", "+00:00")
    )

    repositories = get_all_public_repositories(token, login)
    own_nonfork_repositories = [
        repo for repo in repositories if not repo.get("fork")
    ]
    language_totals = get_language_totals(token, repositories)

    total_commits, contribution_days = fetch_contribution_history(
        token,
        login,
        joined_at,
        now_utc,
    )

    visible_start = today - dt.timedelta(days=364)
    commits_year = 0
    yearly_contributions = 0

    # totalCommitContributions and contribution-calendar totals are different:
    # the latter includes issues, PRs, reviews, etc.
    # Query one exact current-year window for commit count.
    year_data = graphql(
        token,
        CONTRIBUTIONS_QUERY,
        {
            "login": login,
            "from": iso_z(
                dt.datetime.combine(
                    visible_start,
                    dt.time.min,
                    tzinfo=tz,
                ).astimezone(dt.timezone.utc)
            ),
            "to": iso_z(now_utc),
        },
    )
    year_collection = year_data["user"]["contributionsCollection"]
    commits_year = int(year_collection["totalCommitContributions"])
    yearly_contributions = int(
        year_collection["contributionCalendar"]["totalContributions"]
    )

    current_streak, longest_streak = calculate_streaks(
        contribution_days,
        today,
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "userstats.svg").write_text(
        generate_stats_svg(
            joined_year=joined_at.year,
            repo_count=len(own_nonfork_repositories),
            commits_year=commits_year,
            commits_total=total_commits,
            prs_total=int(profile["pullRequests"]["totalCount"]),
            contributed_to=int(
                profile["repositoriesContributedTo"]["totalCount"]
            ),
            languages=language_totals,
        ),
        encoding="utf-8",
    )

    (output_dir / "streak.svg").write_text(
        generate_streak_svg(
            current=current_streak,
            longest=longest_streak,
            yearly_contributions=yearly_contributions,
        ),
        encoding="utf-8",
    )

    (output_dir / "activity.svg").write_text(
        generate_activity_svg(
            days=contribution_days,
            today=today,
        ),
        encoding="utf-8",
    )

    print(
        "Generated profile cards:",
        f"repos={len(own_nonfork_repositories)}",
        f"commits_year={commits_year}",
        f"commits_total={total_commits}",
        f"prs={profile['pullRequests']['totalCount']}",
        f"contributed_to={profile['repositoriesContributedTo']['totalCount']}",
        f"current_streak={current_streak}",
        f"longest_streak={longest_streak}",
        f"year_contributions={yearly_contributions}",
    )


if __name__ == "__main__":
    main()
