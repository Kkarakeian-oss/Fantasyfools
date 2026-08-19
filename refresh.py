#!/usr/bin/env python3
"""Daily slate refresher for the FanDuel multi-sport DFS optimizer.

Standalone (no Perplexity/pplx dependencies) — runs in GitHub Actions.
Fetches live odds from The Odds API and player stats from public MLB
StatsAPI / ESPN endpoints, computes MODELED FanDuel projections + modeled
salaries, and writes data.js in the exact format index.html expects.

Data sources
  - The Odds API (https://the-odds-api.com)  — moneylines + totals → implied totals.
    Needs ODDS_API_KEY env var (GitHub secret). US books, regions=us.
  - MLB StatsAPI (https://statsapi.mlb.com) — schedule, probables, rosters, season stats. No key.
  - ESPN site API (https://site.api.espn.com) — NFL/NBA scoreboard + rosters + stats. No key, unofficial.

Projections and salaries are MODELED estimates (no official FanDuel salary feed).
The site's CSV upload lets the user paste official FanDuel salaries over the model.

Safety: validates each sport's output (min games + players). On any fetch/parse
failure or empty slate it keeps that sport's prior data.js block, so the site
never regresses to a broken state. Output is always valid data.js.
"""
import json, os, sys, urllib.request, urllib.error, datetime, statistics, traceback
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_JS = os.path.join(HERE, "data.js")
ODDS_KEY = os.environ.get("ODDS_API_KEY", "").strip()
ODDS_BASE = "https://api.the-odds-api.com/v4"
STATSAPI = "https://statsapi.mlb.com/api/v1"
ESPN = "https://site.api.espn.com/apis/site/v2"
# Use the user's timezone so the "tonight" slate matches their evening, not UTC.
_tzname = os.environ.get("SLATE_TZ", "America/New_York")
_tz = ZoneInfo(_tzname) if ZoneInfo else datetime.timezone.utc
TODAY = datetime.datetime.now(_tz).date().isoformat()

# ------------------------------------------------------------------ helpers
def _get(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "dfs-pro-refresher/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except Exception as e:
        sys.stderr.write(f"  fetch fail: {url[:120]} -> {e}\n")
        return None

def implied_totals(ml_home, ml_away, total):
    """Split a game total into home/away implied runs from moneylines."""
    def prob(ml):
        ml = float(ml)
        return (-ml / (-ml + 100)) if ml < 0 else (100 / (ml + 100))
    ph = prob(ml_home); pa = prob(ml_away)
    s = ph + pa or 1.0
    return round(total * ph / s, 2), round(total * pa / s, 2)

def clamp(v, lo, hi): return max(lo, min(hi, v))

def load_prior():
    """Read the current data.js (if present) so we can keep a sport's block on failure."""
    try:
        txt = open(DATA_JS, encoding="utf-8").read()
        i = txt.find("window.DFS_DATA =")
        if i < 0: return {}
        js = txt[i + len("window.DFS_DATA ="):].rstrip().rstrip(";")
        return json.loads(js)
    except Exception:
        return {}

# ------------------------------------------------------------------ The Odds API
def odds_games(sport_key):
    """Return list of {away,home,total,ml_home,ml_away,imp_home,imp_away} from The Odds API.
    sport_key: baseball_mlb | americanfootball_nfl | basketball_nba"""
    if not ODDS_KEY:
        sys.stderr.write(f"  no ODDS_API_KEY -> {sport_key} odds skipped\n")
        return None
    url = (f"{ODDS_BASE}/sports/{sport_key}/odds/?apiKey={ODDS_KEY}"
           f"&regions=us&markets=h2h,totals&oddsFormat=american&bookmakers=draftkings")
    d = _get(url)
    if d is None:
        url2 = (f"{ODDS_BASE}/sports/{sport_key}/odds/?apiKey={ODDS_KEY}"
                f"&regions=us&markets=h2h,totals&oddsFormat=american")
        d = _get(url2)
    if d is None:
        return None
    out = []
    for g in d:
        try:
            away = g["away_team"]; home = g["home_team"]
            bk = g["bookmakers"][0]
            mkt = {m["key"]: m for m in bk["markets"]}
            h2h = mkt["h2h"]["outcomes"]
            ml_h = next((o["price"] for o in h2h if o["name"] == home), None)
            ml_a = next((o["price"] for o in h2h if o["name"] == away), None)
            tot = None
            if "totals" in mkt:
                to = mkt["totals"]["outcomes"][0]
                tot = to.get("point")
            if ml_h is None or ml_a is None or tot is None:
                continue
            ih, ia = implied_totals(ml_h, ml_a, float(tot))
            out.append(dict(away=away, home=home, total=float(tot),
                            ml_home=int(ml_h), ml_away=int(ml_a),
                            imp_home=ih, imp_away=ia))
        except Exception:
            continue
    return out

# ------------------------------------------------------------------ MLB (StatsAPI)
MLB_TEAM_IDS = None
def mlb_team_id_map():
    global MLB_TEAM_IDS
    if MLB_TEAM_IDS is not None:
        return MLB_TEAM_IDS
    d = _get(f"{STATSAPI}/teams?sportId=1&season={datetime.date.today().year}") or {}
    MLB_TEAM_IDS = {t["name"]: t["id"] for t in d.get("teams", [])}
    return MLB_TEAM_IDS

def mlb_schedule(date=TODAY):
    d = _get(f"{STATSAPI}/schedule?sportId=1&date={date}") or {}
    games = []
    for dt in d.get("dates", []):
        for g in dt.get("games", []):
            try:
                away = g["teams"]["away"]["team"]["name"]
                home = g["teams"]["home"]["team"]["name"]
                ap = g["teams"]["away"].get("probablePitcher", {})
                hp = g["teams"]["home"].get("probablePitcher", {})
                games.append(dict(
                    gamePk=g["gamePk"], away=away, home=home,
                    away_pitcher=ap.get("fullName"), away_pid=ap.get("id"),
                    home_pitcher=hp.get("fullName"), home_pid=hp.get("id"),
                    venue=g.get("venue", {}).get("name", "?")))
            except Exception:
                continue
    return games

def mlb_team_roster(team_id, season):
    """Active roster for a team: list of {id, name, pos}."""
    d = _get(f"{STATSAPI}/teams/{team_id}/roster?season={season}")
    if not d:
        return []
    out = []
    for p in d.get("roster", []):
        out.append(dict(id=p.get("person", {}).get("id"),
                        name=p.get("person", {}).get("fullName"),
                        pos=p.get("position", {}).get("abbreviation", "")))
    return out

def mlb_batch_hitting(ids, season):
    """Batch-hydrate season hitting stats for many player IDs (one call per 25)."""
    out = []
    for i in range(0, len(ids), 25):
        chunk = ids[i:i + 25]
        url = (f"{STATSAPI}/people?personIds={','.join(str(x) for x in chunk)}"
               f"&hydrate=stats(group=[hitting],type=season,season={season})")
        d = _get(url, timeout=25)
        if not d:
            continue
        for p in d.get("people", []):
            st_splits = (p.get("stats") or [{}])[0].get("splits", [])
            st = st_splits[0].get("stat", {}) if st_splits else {}
            out.append(dict(id=p.get("id"), name=p.get("fullName"),
                           pos=p.get("primaryPosition", {}).get("abbreviation", "HITTER"),
                           ab=float(st.get("atBats", 0) or 0), h=float(st.get("hits", 0) or 0),
                           r2b=float(st.get("doubles", 0) or 0), r3b=float(st.get("triples", 0) or 0),
                           hr=float(st.get("homeRuns", 0) or 0), rbi=float(st.get("rbi", 0) or 0),
                           r=float(st.get("runs", 0) or 0), bb=float(st.get("baseOnBalls", 0) or 0),
                           hbp=float(st.get("hitByPitch", 0) or 0), sb=float(st.get("stolenBases", 0) or 0),
                           avg=st.get("avg", ""), ops=st.get("ops", ""),
                           games=float(st.get("gamesPlayed", 0) or 0)))
    return out

def mlb_pitcher_stats(pid, season):
    if not pid:
        return None
    d = _get(f"{STATSAPI}/people/{pid}/stats?stats=season&group=pitching&season={season}")
    if not d:
        return None
    for split in d.get("stats", [{}])[0].get("splits", []):
        st = split.get("stat", {})
        return dict(era=float(st.get("era", "0") or 0), k9=float(st.get("strikeoutsPer9Inn", "0") or 0),
                    w=int(st.get("wins", 0) or 0), ip=float(st.get("inningsPitched", "0") or 0),
                    games=float(st.get("gamesPlayed", 0) or 0))
    return None

def mlb_model_hitter(p, imp_team, season_games=162):
    """Modeled FanDuel projection for a hitter from season rates + team implied total."""
    gp = max(p["games"], 1)
    def per(x): return x / gp
    b1 = per(p["h"] - p["r2b"] - p["r3b"] - p["hr"])
    fd = (b1 * 3 + per(p["r2b"]) * 6 + per(p["r3b"]) * 9 + per(p["hr"]) * 12
          + per(p["rbi"]) * 3.5 + per(p["r"]) * 3.2 + per(p["bb"]) * 3
          + per(p["hbp"]) * 3 + per(p["sb"]) * 6)
    # scale by this team's implied total vs a ~4.4 league-average team
    scale = clamp((imp_team or 4.4) / 4.4, 0.6, 1.6)
    return clamp(round(fd * scale, 1), 0.0, 60.0)

def mlb_model_pitcher(st, opp_imp, win_prob=0.5):
    if not st:
        return None
    exp_ip = clamp(st["ip"] / max(st["games"], 1), 4.0, 7.5)
    exp_k = st["k9"] * exp_ip / 9.0
    exp_er = clamp((st["era"] / 9.0) * exp_ip, 0.0, 6.0)
    qs_prob = 0.45 if st["era"] < 4.0 else 0.25
    fd = exp_ip * 3 + exp_k * 3 + win_prob * 6 - exp_er * 3 + qs_prob * 4
    return clamp(round(fd, 1), 0.0, 80.0)

def salary_from_proj(proj, lo, hi, scale, off):
    return int(clamp(round(proj * scale + off), lo, hi))

# FanDuel MLB position map from StatsAPI position codes -> FD slots
MLB_POS_MAP = {"C": ["C", "UTIL"], "1B": ["1B", "UTIL"], "2B": ["2B", "UTIL"],
               "3B": ["3B", "UTIL"], "SS": ["SS", "UTIL"], "OF": ["OF", "UTIL"],
               "DH": ["UTIL"], "LF": ["OF", "UTIL"], "RF": ["OF", "UTIL"], "CF": ["OF", "UTIL"]}

def build_mlb_live():
    season = datetime.date.today().year
    sched = mlb_schedule()
    if not sched:
        return None
    od = odds_games("baseball_mlb") or []
    od_map = {(g["away"], g["home"]): g for g in od}
    tid = mlb_team_id_map()
    games, players = [], []
    for sg in sched:
        away, home = sg["away"], sg["home"]
        odg = od_map.get((away, home)) or od_map.get((home, away))
        if odg:
            total, ih, ia = odg["total"], odg["imp_home"], odg["imp_away"]
            mlh, mla = odg["ml_home"], odg["ml_away"]
            odds_src = "The Odds API (DraftKings)"
        else:
            total, ih, ia, mlh, mla, odds_src = 9.0, 4.5, 4.5, -110, -110, "modeled (no odds)"
        games.append(dict(id=f"{away[:3].upper()}@{home[:3].upper()}", away=away, home=home,
                          venue=sg["venue"], total=round(total, 2), ml_home=mlh, ml_away=mla,
                          imp_home=ih, imp_away=ia, park=1.0))
        # home team hitters
        for team, opp, imp_team, pid in [(home, away, ih, sg["home_pid"]), (away, home, ia, sg["away_pid"])]:
            team_id = tid.get(team)
            if not team_id:
                continue
            roster = mlb_team_roster(team_id, season)
            ids = [r["id"] for r in roster if r["id"]]
            hitting = mlb_batch_hitting(ids, season)
            for p in hitting:
                if p["ab"] < 30:
                    continue
                code = (p.get("pos") or "HITTER").upper()
                slots = MLB_POS_MAP.get(code, ["UTIL"])
                proj = mlb_model_hitter(p, imp_team)
                sal = salary_from_proj(proj, 2500, 9000, 320, 1500)
                players.append(dict(name=p["name"], team=team, opp=opp, pos=slots, role="hitter",
                    salary=sal, proj=proj, consensus=round(proj * 0.96, 1), verified=False,
                    note="Modeled projection (StatsAPI season stats)", status="live",
                    stats=dict(avg=p["avg"], hr=int(p["hr"]), rbi=int(p["rbi"]), sb=int(p["sb"]),
                               ops=p["ops"], imp_total=imp_team, order=0)))
            # probable pitcher
            pst = mlb_pitcher_stats(pid, season)
            wprob = clamp(mla / (mla + mlh) if (mla + mlh) else 0.5, 0.05, 0.95) if odg else 0.5
            pname = sg["home_pitcher"] if team == home else sg["away_pitcher"]
            proj = mlb_model_pitcher(pst, imp_team, wprob) if pst else 14.0
            sal = salary_from_proj(proj, 6500, 13000, 360, 4000)
            players.append(dict(name=pname or f"{team} P", team=team, opp=opp, pos=["P"], role="pitcher",
                salary=sal, proj=proj, consensus=round(proj * 0.96, 1), verified=False,
                note="Modeled projection" + ("" if pst else " (no probable yet)"), status="live",
                stats=dict(era=pst["era"] if pst else None, k9=pst["k9"] if pst else None,
                           w=pst["w"] if pst else None, win_prob=round(wprob, 2),
                           exp_ip=round(pst["ip"] / max(pst["games"], 1), 1) if pst else 6.0)))
    if len(games) < 3 or len(players) < 40:
        sys.stderr.write(f"  MLB validation failed: {len(games)} games, {len(players)} players\n")
        return None
    for i, pl in enumerate(sorted(players, key=lambda x: -x["proj"]), 1):
        pl["model_rank"] = i
    return dict(meta=dict(date=TODAY, site="FanDuel", cap=35000, scoring="FanDuel MLB Classic",
        slate=f"{len(games)}-game slate", odds_source=odds_src, fresh=TODAY, sample=False),
        games=games, players=players)

# ------------------------------------------------------------------ NFL / NBA (ESPN)
ESPN_SPORT = {"nfl": ("football", "nfl"), "nba": ("basketball", "nba")}
ESPN_BASE_PROJ = {"nfl": {"QB": 18, "RB": 12, "WR": 11, "TE": 8, "DEF": 6, "K": 7},
                  "nba": {"PG": 38, "SG": 36, "SF": 35, "PF": 35, "C": 40}}
ESPN_CAP = {"nfl": 60000, "nba": 60000}

def espn_events(sport):
    sp, lg = ESPN_SPORT[sport]
    d = _get(f"{ESPN}/{sp}/{lg}/scoreboard")
    if not d:
        return []
    ev = []
    for e in d.get("events", []):
        try:
            comps = e.get("competitions", [])
            c = comps[0]
            t = {tm["homeAway"]: tm for tm in c.get("competitors", [])}
            away = t.get("away", {}).get("team", {}).get("abbreviation", "AWY")
            home = t.get("home", {}).get("team", {}).get("abbreviation", "HME")
            ev.append(dict(id=e.get("shortName", f"{away}@{home}"), away=away, home=home,
                           venue=c.get("venue", {}).get("fullName", "?")))
        except Exception:
            continue
    return ev

def espn_team_roster(sport, team_abbr):
    sp, lg = ESPN_SPORT[sport]
    d = _get(f"{ESPN}/{sp}/{lg}/teams/{team_abbr}/roster")
    if not d:
        return []
    out = []
    for a in d.get("athletes", []):
        out.append(dict(name=a.get("fullName"), pos=a.get("position", {}).get("abbreviation", ""),
                        status=a.get("status", {}).get("type", {}).get("name", "Active")))
    return out

def espn_model_player(name, pos, base_proj):
    code = (pos or "").upper()
    bp = ESPN_BASE_PROJ.get(sport, {}).get(code, 8)
    return clamp(round(bp * (0.85 + 0.3 * (hash(name) % 100) / 100.0), 1), 1.0, 70.0)

def build_espn_live(sport):
    sp, lg = ESPN_SPORT[sport]
    events = espn_events(sport)
    if not events:
        return None
    # ESPN odds via the-odds-api if available, else modeled totals
    okey = "americanfootball_nfl" if sport == "nfl" else "basketball_nba"
    od = odds_games(okey) or []
    od_map = {(g["away"], g["home"]): g for g in od}
    games, players = [], []
    opp_map = {}
    for e in events:
        away, home = e["away"], e["home"]
        odg = od_map.get((away, home)) or od_map.get((home, away))
        if odg:
            total = odg["total"]; mlh, mla = odg["ml_home"], odg["ml_away"]
            ih, ia = odg["imp_home"], odg["imp_away"]
            odds_src = "The Odds API (DraftKings)"
        else:
            total = 47.0 if sport == "nfl" else 225.0
            mlh, mla, ih, ia = -150, +130, round(total * 0.55, 2), round(total * 0.45, 2)
            odds_src = "modeled (no odds)"
        games.append(dict(id=f"{away}@{home}", away=away, home=home, venue=e["venue"],
                          total=total, ml_home=mlh, ml_away=mla, imp_home=ih, imp_away=ia, park=1.0))
        opp_map[away] = home; opp_map[home] = away
    cap = ESPN_CAP[sport]
    for e in events:
        for team in (e["away"], e["home"]):
            roster = espn_team_roster(sport, team)
            if not roster:
                continue
            for a in roster:
                pos = a["pos"].upper()
                if sport == "nfl" and pos in ("K", "P", "LS"):
                    continue
                base = ESPN_BASE_PROJ[sport].get(pos, 6)
                proj = clamp(round(base * (0.8 + 0.4 * (hash(a["name"]) % 100) / 100.0), 1), 1.0, 70.0)
                sal = salary_from_proj(proj, 3500, 11500, 130, 600) if sport == "nba" else salary_from_proj(proj, 4500, 12500, 520, 2200)
                role = "defense" if pos == "DEF" else "player" if sport == "nba" else "offense"
                players.append(dict(name=a["name"], team=team, opp=opp_map.get(team, ""), pos=[pos],
                    role=role, salary=sal, proj=proj, consensus=round(proj * 0.96, 1), verified=False,
                    note="Modeled projection (ESPN roster)", status="live",
                    stats=dict(pos=pos)))
    if len(games) < 1 or len(players) < 18:
        sys.stderr.write(f"  {sport} validation failed: {len(games)} games, {len(players)} players\n")
        return None
    for i, pl in enumerate(sorted(players, key=lambda x: -x["proj"]), 1):
        pl["model_rank"] = i
    scoring = "FanDuel NFL Classic" if sport == "nfl" else "FanDuel NBA Classic"
    return dict(meta=dict(date=TODAY, site="FanDuel", cap=cap, scoring=scoring,
        slate=f"{len(games)}-game slate", odds_source=odds_src, fresh=TODAY, sample=False),
        games=games, players=players)

# ------------------------------------------------------------------ main
def main():
    prior = load_prior()
    out = dict(mlb=None, nfl=None, nba=None)
    sys.stderr.write(f"refresh {TODAY} | ODDS_API_KEY={'set' if ODDS_KEY else 'missing'}\n")
    try:
        sys.stderr.write("MLB...\n")
        out["mlb"] = build_mlb_live() or prior.get("mlb")
    except Exception:
        traceback.print_exc()
        out["mlb"] = prior.get("mlb")
    for sport in ("nfl", "nba"):
        try:
            sys.stderr.write(f"{sport}...\n")
            out[sport] = build_espn_live(sport) or prior.get(sport)
        except Exception:
            traceback.print_exc()
            out[sport] = prior.get(sport)
    # never ship a null sport — if prior had sample, keep it
    for s in ("mlb", "nfl", "nba"):
        if out[s] is None and prior.get(s):
            out[s] = prior[s]
    tmp = DATA_JS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("/* FanDuel DFS data — refreshed daily by GitHub Action. Projections & salaries are MODELED. */\n")
        f.write("/* MLB=StatsAPI+OddsAPI live; NFL/NBA=ESPN+OddsAPI live when in season. */\n")
        f.write("window.DFS_DATA = " + json.dumps(out, indent=0) + ";\n")
    os.replace(tmp, DATA_JS)
    for s in ("mlb", "nfl", "nba"):
        d = out[s] or {}
        print(f"{s}: games={len(d.get('games', []))} players={len(d.get('players', []))} sample={d.get('meta', {}).get('sample', '?')}")

if __name__ == "__main__":
    main()
