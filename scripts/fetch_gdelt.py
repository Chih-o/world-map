"""Fetch the last few hours of GDELT 2.0 events and summarise them by country.

Writes data/latest.json (used by the map) and data/history.json (hourly totals).
Only uses the Python standard library, so it runs anywhere without pip install.
"""
import csv
import io
import json
import re
import sys
import urllib.request
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

BASE = "http://data.gdeltproject.org/gdeltv2/"
HOURS = 6                 # rolling window size
HISTORY_LEN = 72          # hourly snapshots kept (3 days)
MIN_EVENTS = 5            # ignore countries with fewer events than this
DATA = Path(__file__).resolve().parent.parent / "data"

# CAMEO root event codes
ROOT_CODES = {
    "01": "公開聲明", "02": "呼籲", "03": "表達合作意向", "04": "協商",
    "05": "外交合作", "06": "實質合作", "07": "提供援助", "08": "讓步",
    "09": "調查", "10": "要求", "11": "不滿", "12": "拒絕", "13": "威脅",
    "14": "抗議", "15": "展示武力", "16": "降低關係", "17": "脅迫",
    "18": "攻擊", "19": "戰鬥", "20": "大規模暴力",
}

csv.field_size_limit(10**7)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "world-map/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def latest_stamp():
    text = fetch(BASE + "lastupdate.txt").decode()
    m = re.search(r"(\d{14})\.export", text)
    return datetime.strptime(m.group(1), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def read_export(stamp):
    url = f"{BASE}{stamp:%Y%m%d%H%M%S}.export.CSV.zip"
    try:
        raw = fetch(url)
    except Exception as e:  # GDELT occasionally skips a 15-minute file
        print(f"skip {url}: {e}", file=sys.stderr)
        return []
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        text = z.read(z.namelist()[0]).decode("utf-8", "replace")
    return list(csv.reader(io.StringIO(text), delimiter="\t", quoting=csv.QUOTE_NONE))


def title_from_url(url):
    """GDELT events carry no headline, so derive a readable one from the URL slug."""
    parsed = urlparse(url)
    domain = parsed.netloc.removeprefix("www.")
    best = ""
    for seg in parsed.path.split("/"):
        seg = re.sub(r"\.(html?|php|aspx?|cms|ece)$", "", seg)
        if seg.count("-") >= 3 and len(seg) > len(best):
            best = seg
    words = [w for w in re.split(r"[-_]+", best) if w and not re.fullmatch(r"[0-9a-f]{6,}|\d+", w)]
    title = " ".join(words).strip()
    return (title[:1].upper() + title[1:]) if title else domain, domain


def status(conflict, goldstein, tone):
    if conflict >= 0.45 or goldstein <= -3:
        return 3, "緊張"
    if conflict >= 0.30 or tone <= -4:
        return 2, "關注"
    return 1, "平穩"


def num(s, default=0.0):
    try:
        return float(s)
    except ValueError:
        return default


def main():
    end = latest_stamp()
    stamps = [end - timedelta(minutes=15 * i) for i in range(HOURS * 4)]

    countries = defaultdict(lambda: {
        "events": 0, "mentions": 0, "conflict": 0, "tone": 0.0, "gold": 0.0,
        "lat": 0.0, "lon": 0.0, "n_pos": 0, "centroid": None,
        "names": Counter(), "roots": Counter(), "urls": Counter(),
    })
    heat = Counter()
    roots_global = Counter()
    files = 0

    for stamp in stamps:
        rows = read_export(stamp)
        if rows:
            files += 1
        for r in rows:
            if len(r) < 61:
                continue
            code, lat, lon = r[53], r[56], r[57]
            if not code or not lat or not lon:
                continue
            lat, lon = num(lat), num(lon)
            m = max(int(num(r[31], 1)), 1)
            c = countries[code]
            c["events"] += 1
            c["mentions"] += m
            if r[29] in ("3", "4"):
                c["conflict"] += m
            c["tone"] += num(r[34]) * m
            c["gold"] += num(r[30]) * m
            c["lat"] += lat
            c["lon"] += lon
            c["n_pos"] += 1
            if r[51] == "1":  # location resolved to the country itself
                c["centroid"] = (lat, lon)
            c["names"][r[52].split(",")[-1].strip()] += 1
            if r[28] in ROOT_CODES:
                c["roots"][r[28]] += m
                roots_global[r[28]] += m
            if r[60].startswith("http"):
                c["urls"][r[60]] += m
            heat[(round(lat, 1), round(lon, 1))] += m

    if not files:
        sys.exit("no GDELT files could be downloaded")

    history_path = DATA / "history.json"
    history = json.loads(history_path.read_text("utf-8")) if history_path.exists() else []

    # Compare against the snapshot from one full window ago (non-overlapping)
    target = end - timedelta(hours=HOURS)
    prev = None
    for h in history:
        t = datetime.fromisoformat(h["t"])
        if t <= target + timedelta(minutes=30):
            prev = h

    out = []
    for code, c in countries.items():
        if c["events"] < MIN_EVENTS:
            continue
        mentions = c["mentions"]
        conflict = c["conflict"] / mentions
        tone = c["tone"] / mentions
        gold = c["gold"] / mentions
        level, label = status(conflict, gold, tone)
        lat, lon = c["centroid"] or (c["lat"] / c["n_pos"], c["lon"] / c["n_pos"])
        headlines = []
        for url, _ in c["urls"].most_common(6):
            title, domain = title_from_url(url)
            headlines.append({"title": title, "domain": domain, "url": url})
        out.append({
            "code": code,
            "name": c["names"].most_common(1)[0][0],
            "lat": round(lat, 3), "lon": round(lon, 3),
            "events": c["events"], "mentions": mentions,
            "conflict": round(conflict, 3), "tone": round(tone, 2),
            "goldstein": round(gold, 2), "level": level, "status": label,
            "prev_mentions": prev["c"].get(code) if prev else None,
            "top_types": [{"code": k, "label": ROOT_CODES[k], "mentions": v}
                          for k, v in c["roots"].most_common(5)],
            "headlines": headlines,
        })
    out.sort(key=lambda x: x["mentions"], reverse=True)

    total_m = sum(x["mentions"] for x in out)
    conflict_m = sum(x["conflict"] * x["mentions"] for x in out)
    tone_m = sum(x["tone"] * x["mentions"] for x in out)
    now = datetime.now(timezone.utc)

    latest = {
        "generated": now.isoformat(timespec="seconds"),
        "window_start": (end - timedelta(hours=HOURS) + timedelta(minutes=15)).isoformat(),
        "window_end": end.isoformat(),
        "window_hours": HOURS,
        "files": files,
        "global": {
            "events": sum(x["events"] for x in out),
            "mentions": total_m,
            "countries": len(out),
            "conflict": round(conflict_m / total_m, 3) if total_m else 0,
            "tone": round(tone_m / total_m, 2) if total_m else 0,
            "tense": sum(1 for x in out if x["level"] == 3),
            "top_types": [{"code": k, "label": ROOT_CODES[k], "mentions": v}
                          for k, v in roots_global.most_common(8)],
        },
        "countries": out,
        "heat": [[lat, lon, w] for (lat, lon), w in heat.most_common(5000)],
    }

    history = [h for h in history if h["t"] != end.isoformat()]
    history.append({
        "t": end.isoformat(),
        "mentions": total_m,
        "conflict": latest["global"]["conflict"],
        "c": {x["code"]: x["mentions"] for x in out[:80]},
    })
    history = history[-HISTORY_LEN:]
    latest["history"] = [{"t": h["t"], "mentions": h["mentions"], "conflict": h["conflict"]}
                         for h in history]

    DATA.mkdir(exist_ok=True)
    (DATA / "latest.json").write_text(json.dumps(latest, ensure_ascii=False, separators=(",", ":")), "utf-8")
    history_path.write_text(json.dumps(history, ensure_ascii=False, separators=(",", ":")), "utf-8")
    print(f"{files} files, {len(out)} countries, {total_m} mentions, window ends {end:%Y-%m-%d %H:%M} UTC")


if __name__ == "__main__":
    main()
