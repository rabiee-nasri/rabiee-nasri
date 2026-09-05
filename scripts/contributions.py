#!/usr/bin/env python3
"""Render contribution heatmaps for three accounts into two SVGs.

Sources: GitHub GraphQL (public contribution calendars) for the personal and the
work account, and GitLab's public calendar endpoint. Counts only; no
repository names or details are read or written. Standard library only.
"""
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request

ACCOUNTS = [
    {"kind": "github", "login": "rabiee-nasri", "label": "GitHub",
     "note": "personal", "url": "https://github.com/rabiee-nasri"},
    {"kind": "github", "login": "RabieeNasri", "label": "GitHub",
     "note": "Akkodis work account, private repositories",
     "url": "https://github.com/RabieeNasri"},
    {"kind": "gitlab", "login": "rabiee-nasri", "label": "GitLab",
     "note": "personal projects, 2020 onwards", "url": "https://gitlab.com/rabiee-nasri"},
]
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
TODAY = dt.date.today()
UA = "rabiee-nasri profile README contributions script"


def http_json(url, headers=None, data=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def github_calendar(login, since, until):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is required for the GitHub GraphQL API")
    query = """
    query($login:String!, $from:DateTime!, $to:DateTime!) {
      user(login:$login) {
        createdAt
        contributionsCollection(from:$from, to:$to) {
          restrictedContributionsCount
          contributionCalendar {
            totalContributions
            weeks { contributionDays { date contributionCount } }
          }
        }
      }
    }"""
    body = json.dumps({"query": query, "variables": {
        "login": login,
        "from": since.isoformat() + "T00:00:00Z",
        "to": until.isoformat() + "T23:59:59Z"}}).encode()
    res = http_json("https://api.github.com/graphql",
                    {"Authorization": f"bearer {token}", "Content-Type": "application/json"}, body)
    if "errors" in res:
        raise RuntimeError(res["errors"])
    user = res["data"]["user"]
    coll = user["contributionsCollection"]
    days = {}
    for w in coll["contributionCalendar"]["weeks"]:
        for d in w["contributionDays"]:
            days[d["date"]] = d["contributionCount"]
    return days, coll["contributionCalendar"]["totalContributions"], user["createdAt"][:4]


def github_total_since(login, first_year):
    total = 0
    for y in range(int(first_year), TODAY.year + 1):
        start, end = dt.date(y, 1, 1), min(dt.date(y, 12, 31), TODAY)
        _, t, _ = github_calendar(login, start, end)
        total += t
    return total


def gitlab_calendar(username):
    try:
        data = http_json(f"https://gitlab.com/users/{username}/calendar.json")
    except urllib.error.HTTPError:
        data = {}
    return {k: int(v) for k, v in data.items()}


def year_window():
    # 53 columns of weeks ending with the current week, Sunday-first like GitHub.
    end = TODAY
    start = end - dt.timedelta(days=end.weekday() + 1 if end.weekday() != 6 else 0)  # this week's Sunday
    start = start - dt.timedelta(weeks=52)
    return start, end


def collect():
    start, end = year_window()
    rows = []
    for acc in ACCOUNTS:
        if acc["kind"] == "github":
            days, total, created = github_calendar(acc["login"], start, end)
            since_total = github_total_since(acc["login"], created)
            since_label = f"{since_total:,} since {created}"
        else:
            days = gitlab_calendar(acc["login"])
            days = {k: v for k, v in days.items() if start.isoformat() <= k <= end.isoformat()}
            total = sum(days.values())
            since_label = "public calendar covers the last twelve months only"
        rows.append({**acc, "days": days, "total": total, "since": since_label})
    return start, end, rows


THEMES = {
    "light": {"bg": "none", "text": "#1f2328", "muted": "#59636e", "empty": "#ebedf0",
              "scale": ["#c9efe8", "#8fdccb", "#3fb8a2", "#0f766e"], "rule": "#d0d7de"},
    "dark": {"bg": "none", "text": "#e6edf3", "muted": "#9198a1", "empty": "#161b22",
             "scale": ["#0f3f3a", "#156b60", "#1c9c88", "#2dd4bf"], "rule": "#30363d"},
}
CELL, GAP, LEFT, TOP = 11, 3, 24, 56
ROW_HEADER, ROW_GAP = 30, 22
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(theme_name, start, end, rows):
    t = THEMES[theme_name]
    step = CELL + GAP
    cols = 53
    width = LEFT + cols * step + 16
    grid_h = 7 * step
    row_h = ROW_HEADER + 14 + grid_h + ROW_GAP
    height = TOP + len(rows) * row_h + 28
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
           f'font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif" font-size="12">']
    out.append(f'<title>Contributions in the last twelve months across three accounts</title>')
    out.append(f'<text x="{LEFT}" y="22" font-size="15" font-weight="600" fill="{t["text"]}">'
               f'Contributions, last twelve months, across three accounts</text>')
    out.append(f'<text x="{LEFT}" y="40" fill="{t["muted"]}">Counts only. Client repositories are private and no repository '
               f'details are read or shown. Updated {TODAY.isoformat()}.</text>')
    y0 = TOP
    for row in rows:
        days = row["days"]
        mx = max(days.values()) if days else 0
        # header
        out.append(f'<text x="{LEFT}" y="{y0 + 14}" font-weight="600" fill="{t["text"]}">{esc(row["label"])} · '
                   f'<a href="{row["url"]}" fill="{t["text"]}">{esc(row["login"])}</a>'
                   f'<tspan fill="{t["muted"]}" font-weight="400">  {esc(row["note"])}</tspan></text>')
        right = f'{row["total"]:,} in the last year' + (f' · {esc(row["since"])}' if row["kind"] == "github" else "")
        out.append(f'<text x="{width - 16}" y="{y0 + 14}" text-anchor="end" fill="{t["muted"]}">{right}</text>')
        gy = y0 + ROW_HEADER + 14
        # month labels
        # One label per month, on the first column that falls in it. The first
        # column is labelled only if its month still owns the next column, so
        # two labels never land 14px apart.
        d = start
        prev_month = None
        for c in range(cols):
            if d.month != prev_month:
                owns_next = (d + dt.timedelta(weeks=1)).month == d.month
                if c > 0 or owns_next:
                    out.append(f'<text x="{LEFT + c * step}" y="{gy - 4}" font-size="10" fill="{t["muted"]}">{MONTHS[d.month - 1]}</text>')
                prev_month = d.month
            d += dt.timedelta(weeks=1)
        # cells
        d = start
        for c in range(cols):
            for r in range(7):
                if d > end:
                    break
                v = days.get(d.isoformat(), 0)
                if v <= 0 or mx == 0:
                    fill = t["empty"]
                else:
                    q = v / mx
                    fill = t["scale"][0 if q <= 0.25 else 1 if q <= 0.5 else 2 if q <= 0.75 else 3]
                # No per-cell <title>: GitHub serves README images through a proxy as
                # plain images, so tooltips never show and only add weight.
                out.append(f'<rect x="{LEFT + c * step}" y="{gy + r * step}" width="{CELL}" height="{CELL}" rx="2" fill="{fill}"/>')
                d += dt.timedelta(days=1)
        if row["kind"] == "gitlab" and not days:
            out.append(f'<text x="{LEFT}" y="{gy + grid_h + 14}" font-size="11" fill="{t["muted"]}">'
                       f'No public calendar data yet: GitLab hides private contributions until the profile setting is on.</text>')
        y0 += row_h
    out.append("</svg>")
    return "\n".join(out)


def main():
    start, end, rows = collect()
    os.makedirs(OUT_DIR, exist_ok=True)
    for name in THEMES:
        with open(os.path.join(OUT_DIR, f"contributions-{name}.svg"), "w", encoding="utf-8") as f:
            f.write(render(name, start, end, rows))
    snapshot = {"updated": TODAY.isoformat(), "window": [start.isoformat(), end.isoformat()],
                "accounts": [{"label": r["label"], "login": r["login"], "last_year": r["total"], "since": r["since"]} for r in rows]}
    with open(os.path.join(OUT_DIR, "contributions.json"), "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)
    for r in rows:
        print(f'{r["label"]:<6} {r["login"]:<14} last year={r["total"]:>5}  {r["since"]}')


if __name__ == "__main__":
    main()
