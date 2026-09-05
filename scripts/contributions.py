#!/usr/bin/env python3
"""Render the contribution graphic for the profile README.

Three blocks: a stacked monthly timeline since 2020 across every account, the
daily heatmap of the current work account for the last twelve months, and a
table of yearly totals. Sources: GitHub GraphQL (public contribution
calendars) and the GitLab events API (GITLAB_TOKEN, read_api, lets it count
private-project events; without it only public events are counted). Counts
only; no repository names or details are read or written. Standard library.
"""
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

FIRST_YEAR = 2020
TODAY = dt.date.today()
UA = "rabiee-nasri profile README contributions script"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")

# Order is stacking order (bottom to top) and legend order.
ACCOUNTS = [
    {"kind": "gitlab", "login": "rabiee-nasri", "id": 9038451, "label": "GitLab",
     "note": "Automax and client projects", "url": "https://gitlab.com/rabiee-nasri",
     "color": {"light": "#d9a300", "dark": "#f2c94c"}},
    {"kind": "github", "login": "Mohammad-Nasri-Developer", "label": "GitHub",
     "note": "Smart Science Gate", "url": "https://github.com/Mohammad-Nasri-Developer",
     "color": {"light": "#d13b3b", "dark": "#f47272"}},
    {"kind": "github", "login": "RabieeNasri", "label": "GitHub",
     "note": "Akkodis", "url": "https://github.com/RabieeNasri",
     "color": {"light": "#0f766e", "dark": "#2dd4bf"}, "heatmap": True},
    {"kind": "github", "login": "rabiee-nasri", "label": "GitHub",
     "note": "personal", "url": "https://github.com/rabiee-nasri",
     "color": {"light": "#2f6fdd", "dark": "#79a8ff"}},
]

THEMES = {
    "light": {"text": "#1f2328", "muted": "#59636e", "empty": "#ebedf0", "rule": "#d0d7de",
              "scale": ["#c9efe8", "#8fdccb", "#3fb8a2", "#0f766e"]},
    "dark": {"text": "#e6edf3", "muted": "#9198a1", "empty": "#161b22", "rule": "#30363d",
             "scale": ["#0f3f3a", "#156b60", "#1c9c88", "#2dd4bf"]},
}


def http_json(url, headers=None, data=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------------------------------------------------------------- GitHub
def github_days(login, since, until):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is required for the GitHub GraphQL API")
    query = """
    query($login:String!, $from:DateTime!, $to:DateTime!) {
      user(login:$login) {
        createdAt
        contributionsCollection(from:$from, to:$to) {
          contributionCalendar { weeks { contributionDays { date contributionCount } } }
        }
      }
    }"""
    body = json.dumps({"query": query, "variables": {
        "login": login, "from": since.isoformat() + "T00:00:00Z", "to": until.isoformat() + "T23:59:59Z"}}).encode()
    res = http_json("https://api.github.com/graphql",
                    {"Authorization": f"bearer {token}", "Content-Type": "application/json"}, body)
    if "errors" in res:
        raise RuntimeError(res["errors"])
    user = res["data"]["user"]
    days = {}
    for w in user["contributionsCollection"]["contributionCalendar"]["weeks"]:
        for d in w["contributionDays"]:
            if d["contributionCount"]:
                days[d["date"]] = d["contributionCount"]
    return days, int(user["createdAt"][:4])


def github_all_days(login):
    days, created = github_days(login, dt.date(TODAY.year, 1, 1), TODAY)
    for y in range(max(FIRST_YEAR, created), TODAY.year):
        d, _ = github_days(login, dt.date(y, 1, 1), dt.date(y, 12, 31))
        days.update(d)
    return days


# ---------------------------------------------------------------- GitLab
# Every project in the owner's own GitLab namespace was migrated to GitHub on
# 2026-09-05 with full history, so GitHub counts those commits. GitLab keeps
# counting only projects owned by others that he contributes to (Automax and
# client work), which avoids counting the same commit twice.
GITLAB_SKIP_NAMESPACE = "rabiee-nasri/"


def gitlab_skipped_project_ids(headers):
    ids = set()
    page = 1
    while True:
        try:
            batch = http_json(f"https://gitlab.com/api/v4/projects?membership=true&simple=true&per_page=100&page={page}", headers)
        except urllib.error.HTTPError:
            break
        for pr in batch:
            if pr.get("path_with_namespace", "").startswith(GITLAB_SKIP_NAMESPACE):
                ids.add(pr["id"])
        if len(batch) < 100:
            break
        page += 1
    return ids


def gitlab_all_days(user_id):
    token = os.environ.get("GITLAB_TOKEN")
    headers = {"PRIVATE-TOKEN": token} if token else {}
    skip = gitlab_skipped_project_ids(headers)
    days = {}
    for y in range(FIRST_YEAR, TODAY.year + 1):
        page = 1
        while True:
            url = (f"https://gitlab.com/api/v4/users/{user_id}/events?after={y - 1}-12-31"
                   f"&before={y + 1}-01-01&per_page=100&page={page}")
            try:
                batch = http_json(url, headers)
            except urllib.error.HTTPError as e:
                print(f"gitlab events {y} page {page}: HTTP {e.code}", file=sys.stderr)
                batch = []
            for ev in batch:
                if ev.get("project_id") in skip:
                    continue
                k = ev["created_at"][:10]
                # A push is one event however many commits it carries. GitHub
                # counts commits, so count them here too for a like-for-like bar.
                pd = ev.get("push_data") or {}
                n = pd.get("commit_count") or 1 if pd else 1
                days[k] = days.get(k, 0) + n
            if len(batch) < 100:
                break
            page += 1
    return days, bool(token)


# ---------------------------------------------------------------- shape
def month_key(iso):
    return iso[:7]


def months_since(first_year):
    out, y, m = [], first_year, 1
    while (y, m) <= (TODAY.year, TODAY.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


HISTORY = os.path.join(OUT_DIR, "history.json")


def load_history():
    try:
        with open(HISTORY, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def collect():
    """Fetch every account, then merge with the committed history so a day never
    loses count: if a former employer revokes access, the events GitLab stops
    returning stay in history.json and keep rendering."""
    history = load_history()
    rows = []
    gitlab_authed = True
    for acc in ACCOUNTS:
        if acc["kind"] == "github":
            days = github_all_days(acc["login"])
        else:
            days, gitlab_authed = gitlab_all_days(acc["id"])
        key = f'{acc["kind"]}:{acc["login"]}'
        merged = dict(history.get(key, {}))
        for k, v in days.items():
            merged[k] = max(merged.get(k, 0), v)
        history[key] = dict(sorted(merged.items()))
        days = merged
        by_month, by_year = {}, {}
        for k, v in days.items():
            if k < f"{FIRST_YEAR}-01-01":
                continue
            by_month[month_key(k)] = by_month.get(month_key(k), 0) + v
            by_year[int(k[:4])] = by_year.get(int(k[:4]), 0) + v
        rows.append({**acc, "days": days, "by_month": by_month, "by_year": by_year})
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(HISTORY, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=0, sort_keys=True)
    return rows, gitlab_authed


# ---------------------------------------------------------------- render
LEFT, WIDTH = 34, 782
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(theme, rows, gitlab_authed):
    t = THEMES[theme]
    out = []
    y = 0

    def text(x, yy, s, size=12, weight=400, fill=None, anchor="start"):
        out.append(f'<text x="{x}" y="{yy}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" '
                   f'fill="{fill or t["text"]}">{s}</text>')

    # ---- header
    text(LEFT, 22, "Contributions since 2020, four accounts", 15, 600)
    text(LEFT, 40, f"Monthly since {FIRST_YEAR}, square-root scale so early years stay visible. Counts only, no repository details. Updated {TODAY.isoformat()}.", 12, 400, t["muted"])
    y = 62

    # ---- block 1: stacked monthly timeline
    months = months_since(FIRST_YEAR)
    chart_h, base_y = 170, y + 20 + 170
    plot_left, plot_right = LEFT, WIDTH - 16
    slot = (plot_right - plot_left) / len(months)
    bar_w = max(4, slot - 2)
    stacks = [sum(r["by_month"].get(m, 0) for r in rows) for m in months]
    mx = max(stacks) or 1
    scale = lambda v: chart_h * (v / mx) ** 0.5  # square root keeps 2020 to 2024 legible next to 2026
    for ref in (10, 50, 200):
        if ref < mx:
            gy = base_y - scale(ref)
            out.append(f'<line x1="{plot_left}" y1="{gy:.1f}" x2="{plot_right}" y2="{gy:.1f}" stroke="{t["rule"]}" stroke-dasharray="2 3"/>')
            text(plot_left - 4, gy + 3, str(ref), 9, 400, t["muted"], "end")
    for i, m in enumerate(months):
        x = plot_left + i * slot
        total = stacks[i]
        if not total:
            continue
        top = base_y - scale(total)
        cur = base_y
        for r in rows:
            v = r["by_month"].get(m, 0)
            if not v:
                continue
            h = (base_y - top) * v / total  # share of the stack, in the scaled height
            cur -= h
            out.append(f'<rect x="{x:.1f}" y="{cur:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{r["color"][theme]}"/>')
    out.append(f'<line x1="{plot_left}" y1="{base_y}" x2="{plot_right}" y2="{base_y}" stroke="{t["rule"]}"/>')
    for i, m in enumerate(months):
        if m.endswith("-01"):
            x = plot_left + i * slot
            out.append(f'<line x1="{x:.1f}" y1="{base_y}" x2="{x:.1f}" y2="{base_y + 5}" stroke="{t["rule"]}"/>')
            text(x + 3, base_y + 16, m[:4], 11, 600, t["muted"])
    # legend
    ly = base_y + 40
    for i, r in enumerate(reversed(rows)):
        lx = LEFT + (i % 2) * 380
        if i and i % 2 == 0:
            ly += 18
        out.append(f'<rect x="{lx}" y="{ly - 9}" width="10" height="10" rx="2" fill="{r["color"][theme]}"/>')
        text(lx + 15, ly, f'{esc(r["label"])} · {esc(r["login"])}<tspan fill="{t["muted"]}">  {esc(r["note"])}</tspan>', 11, 600)
    y = ly + 30

    # ---- block 2: heatmap for the current work account, last twelve months
    hm = next(r for r in rows if r.get("heatmap"))
    CELL, GAP = 11, 3
    step = CELL + GAP
    cols = 53
    end = TODAY
    start = end - dt.timedelta(days=(end.weekday() + 1) % 7) - dt.timedelta(weeks=52)
    last_year = sum(v for k, v in hm["days"].items() if start.isoformat() <= k <= end.isoformat())
    text(LEFT, y + 14, f'{esc(hm["label"])} · {esc(hm["login"])}<tspan fill="{t["muted"]}" font-weight="400">  {esc(hm["note"])} work account, last twelve months, day by day</tspan>', 12, 600)
    text(WIDTH - 16, y + 14, f"{last_year:,} in the last year", 12, 400, t["muted"], "end")
    gy = y + 44
    prev = None
    d = start
    for c in range(cols):
        if d.month != prev and (c > 0 or (d + dt.timedelta(days=7)).month == d.month):
            text(LEFT + c * step, gy - 4, MONTHS[d.month - 1], 10, 400, t["muted"])
        prev = d.month
        d += dt.timedelta(weeks=1)
    window = {k: v for k, v in hm["days"].items() if start.isoformat() <= k <= end.isoformat()}
    hmx = max(window.values()) if window else 0
    d = start
    for c in range(cols):
        for r in range(7):
            if d > end:
                break
            v = window.get(d.isoformat(), 0)
            if v <= 0 or hmx == 0:
                fill = t["empty"]
            else:
                q = v / hmx
                fill = t["scale"][0 if q <= 0.25 else 1 if q <= 0.5 else 2 if q <= 0.75 else 3]
            out.append(f'<rect x="{LEFT + c * step}" y="{gy + r * step}" width="{CELL}" height="{CELL}" rx="2" fill="{fill}"/>')
            d += dt.timedelta(days=1)
    y = gy + 7 * step + 30

    # ---- block 3: by-year table
    years = list(range(FIRST_YEAR, TODAY.year + 1))
    text(LEFT, y + 14, "By year", 14, 600)
    text(LEFT + 74, y + 14, "contributions per account", 12, 400, t["muted"])
    ty = y + 40
    label_w = 360
    col_w = (WIDTH - 16 - LEFT - label_w - 70) / len(years)
    out.append(f'<line x1="{LEFT}" y1="{ty + 6}" x2="{WIDTH - 16}" y2="{ty + 6}" stroke="{t["rule"]}"/>')
    for i, yr in enumerate(years):
        text(f"{LEFT + label_w + i * col_w + col_w / 2:.0f}", ty, str(yr), 12, 600, t["muted"], "middle")
    text(WIDTH - 16, ty, "Total", 12, 600, t["muted"], "end")
    grand = 0
    for r in reversed(rows):
        ty += 22
        out.append(f'<rect x="{LEFT}" y="{ty - 10}" width="10" height="10" rx="2" fill="{r["color"][theme]}"/>')
        text(LEFT + 15, ty, f'<tspan font-weight="600">{esc(r["label"])} · {esc(r["login"])}</tspan><tspan fill="{t["muted"]}">  {esc(r["note"])}</tspan>')
        for i, yr in enumerate(years):
            v = r["by_year"].get(yr, 0)
            text(f"{LEFT + label_w + i * col_w + col_w / 2:.0f}", ty, f"{v:,}" if v else "·", 12, 400,
                 t["text"] if v else t["muted"], "middle")
        total = sum(r["by_year"].values())
        grand += total
        text(WIDTH - 16, ty, f"{total:,}", 12, 600, None, "end")
        out.append(f'<line x1="{LEFT}" y1="{ty + 7}" x2="{WIDTH - 16}" y2="{ty + 7}" stroke="{t["rule"]}"/>')
    ty += 22
    text(LEFT + 15, ty, "All accounts", 12, 600)
    for i, yr in enumerate(years):
        v = sum(r["by_year"].get(yr, 0) for r in rows)
        text(f"{LEFT + label_w + i * col_w + col_w / 2:.0f}", ty, f"{v:,}" if v else "·", 12, 600, None, "middle")
    text(WIDTH - 16, ty, f"{grand:,}", 12, 700, None, "end")
    ty += 20
    text(LEFT, ty, "GitLab counts commits in pushes plus issues, merge requests and comments, the same basis GitHub uses."
         + ("" if gitlab_authed else " Public projects only in this render."), 11, 400, t["muted"])
    ty += 16
    text(LEFT, ty, "2020: commits in repositories moved from an earlier GitHub account. "
         "Personal GitLab projects now live on GitHub and count there.", 11, 400, t["muted"])
    height = ty + 20
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" '
           f'font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif" font-size="12">',
           '<title>Contributions since 2020 across four accounts: monthly timeline, the current work account day by day, and totals by year</title>']
    return "\n".join(svg + out + ["</svg>"])


def main():
    rows, gitlab_authed = collect()
    os.makedirs(OUT_DIR, exist_ok=True)
    for name in THEMES:
        with open(os.path.join(OUT_DIR, f"contributions-{name}.svg"), "w", encoding="utf-8") as f:
            f.write(render(name, rows, gitlab_authed))
    snapshot = {"updated": TODAY.isoformat(), "gitlab_private_included": gitlab_authed,
                "accounts": [{"label": r["label"], "login": r["login"], "by_year": r["by_year"]} for r in rows]}
    with open(os.path.join(OUT_DIR, "contributions.json"), "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)
    for r in rows:
        print(f'{r["label"]:<6} {r["login"]:<26} {r["by_year"]}')
    print("gitlab private included:", gitlab_authed)


if __name__ == "__main__":
    main()
