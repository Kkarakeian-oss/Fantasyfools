#!/usr/bin/env python3
"""Generate unified multi-sport FanDuel DFS data (MLB + NFL + NBA).

MLB uses the real Aug 18 2026 slate (imported from gen_data.build()).
NFL & NBA are modeled SAMPLE slates (no regular season in August) — the daily
GitHub Action updater refreshes them with live in-season data.
Output: dfs-pro/data.js  ->  window.DFS_DATA = { mlb:{...}, nfl:{...}, nba:{...} }
Unified player: {name, team, opp, pos:[], salary, proj, consensus, verified, note, status, role, stats{}}
"""
import json, math, random, sys, os
sys.path.insert(0, "/home/user/workspace/mlb-dfs")
import gen_data as M

def clamp(v,lo,hi): return max(lo,min(hi,v))

# ---------------------------------------------------------------- MLB (real)
def build_mlb():
    d = M.build()
    players=[]
    for p in d["pitchers"]:
        players.append(dict(
            name=p["name"], team=p["team"], opp=p["opp"], pos=["P"], role="pitcher",
            salary=p["salary"], proj=p["proj"], consensus=p["consensus"], verified=p["verified"],
            note=p.get("note"), status="live",
            stats=dict(era=p["era"],k9=p["k9"],w=p["w"],win_prob=p["win_prob"],exp_ip=p["exp_ip"])))
    for h in d["hitters"]:
        pos=list(h["pos"])+["UTIL"]
        players.append(dict(
            name=h["name"], team=h["team"], opp=None, pos=pos, role="hitter",
            salary=h["salary"], proj=h["proj"], consensus=h["consensus"], verified=h["verified"],
            note=h.get("note"), status="live",
            stats=dict(avg=h["avg"],hr=h.get("hr"),rbi=h.get("rbi"),sb=h.get("sb"),ops=h.get("ops"),
                       imp_total=h["imp_total"],order=h["order"])))
    for i,pl in enumerate(sorted(players,key=lambda x:-x["proj"]),1): pl["model_rank"]=i
    return dict(meta=dict(date=d["meta"]["date"], site="FanDuel", cap=35000,
        scoring="FanDuel MLB Classic", slate=d["meta"]["slate"],
        odds_source=d["meta"]["odds_source"], fresh=d["meta"]["fresh"], sample=False),
        games=d["games"], players=players)

# ------------------------------------------------ NFL / NBA sample rosters
# (name, team, pos[], tier 1-5)  — tier drives modeled projection
NFL_ROSTERS = {
 "KC":[("Patrick Mahomes",["QB"],1),("Isiah Pacheco",["RB"],2),("Kareem Hunt",["RB"],3),
   ("Rashee Rice",["WR"],2),("Xavier Worthy",["WR"],3),("JuJu Smith-Schuster",["WR"],4),
   ("Skyy Moore",["WR"],5),("Travis Kelce",["TE"],2),("Noah Gray",["TE"],5),("Harrison Butker",["K"],3),
   ("Kansas City Chiefs",["DEF"],3)],
 "LAR":[("Matthew Stafford",["QB"],2),("Kyren Williams",["RB"],2),("Jarquez Jones",["RB"],4),
   ("Puka Nacua",["WR"],2),("Davante Adams",["WR"],2),("Cooper Kupp",["WR"],3),
   ("Demarcus Robinson",["WR"],5),("Tyler Higbee",["TE"],3),("Colin Parkinson",["TE"],5),("Joshua Karty",["K"],4),
   ("Los Angeles Rams",["DEF"],4)],
 "BUF":[("Josh Allen",["QB"],1),("James Cook",["RB"],2),("Ray Davis",["RB"],4),
   ("Khalil Shakir",["WR"],3),("Keon Coleman",["WR"],3),("Amari Cooper",["WR"],4),
   ("Curtis Samuel",["WR"],5),("Dalton Kincaid",["TE"],2),("Dawson Knox",["TE"],4),("Tyler Bass",["K"],3),
   ("Buffalo Bills",["DEF"],2)],
 "PHI":[("Jalen Hurts",["QB"],1),("Saquon Barkley",["RB"],1),("Kenneth Gainwell",["RB"],4),
   ("A.J. Brown",["WR"],1),("DeVonta Smith",["WR"],2),("Jahan Dotson",["WR"],4),
   ("Britain Covey",["WR"],5),("Dallas Goedert",["TE"],2),("Grant Calcaterra",["TE"],5),("Jake Elliott",["K"],2),
   ("Philadelphia Eagles",["DEF"],2)],
}
NFL_BASE={"QB":18,"RB":12,"WR":11,"TE":8,"K":7,"DEF":6}
NFL_GAMES=[("Chiefs @ Rams","KC@LAR","KC","LAR",48.5,-150,+130),
           ("Bills @ Eagles","BUF@PHI","BUF","PHI",47.0,-145,+125)]

NBA_ROSTERS = {
 "DEN":[("Nikola Jokic",["C"],1),("Jamal Murray",["PG"],2),("Michael Porter Jr.",["SF"],3),
   ("Aaron Gordon",["PF"],2),("Russell Westbrook",["PG","SG"],4),("Christian Braun",["SG"],4),
   ("Peyton Watson",["SF"],5),("DeAndre Jordan",["C"],5),("Julian Strawther",["SF"],5),
   ("Dario Saric",["PF"],5)],
 "BOS":[("Jayson Tatum",["SF"],1),("Jaylen Brown",["SG"],1),("Kristaps Porzingis",["C"],2),
   ("Jrue Holiday",["PG"],2),("Derrick White",["PG","SG"],3),("Drew Peterson",["SF"],4),
   ("Sam Hauser",["PF"],4),("Al Horford",["C"],5),("Luke Kornet",["C"],5),
   ("Payton Pritchard",["PG"],3)],
 "LAL":[("LeBron James",["PF","SF"],1),("Luka Doncic",["PG"],1),("Austin Reaves",["SG"],2),
   ("Rui Hachimura",["PF"],3),("Jaxson Hayes",["C"],4),("Gabe Vincent",["PG"],4),
   ("Dalton Knecht",["SG"],3),("Dorian Finney-Smith",["SF"],4),("Trey Jemison",["C"],5),
   ("Maxi Kleber",["PF"],5)],
 "GSW":[("Stephen Curry",["PG"],1),("Jimmy Butler",["SF"],2),("Draymond Green",["PF"],3),
   ("Brandin Podziemski",["SG"],3),("Buddy Hield",["SG","SF"],3),("Jonathan Kuminga",["PF"],3),
   ("Quinten Post",["C"],4),("Trayce Jackson-Davis",["C"],4),("Gary Payton II",["PG","SG"],5),
   ("Moses Moody",["SF"],4)],
}
NBA_BASE={"PG":38,"SG":36,"SF":35,"PF":35,"C":40}
NBA_GAMES=[("Nuggets @ Celtics","DEN@BOS","DEN","BOS",227.5,-130,+110),
           ("Lakers @ Warriors","LAL@GSW","LAL","GSW",225.0,+120,-110)]

def _proj_from_tier(base, tier, noise=0.10, lo=4.0, hi=70.0):
    mul = {1:1.30, 2:1.05, 3:0.85, 4:0.65, 5:0.50}[tier]
    return clamp(round(base*mul*(1+random.uniform(-noise,noise)),1), lo, hi)

def _salary(proj, lo, hi, scale, off):
    return int(clamp(round(proj*scale+off), lo, hi))

def build_nfl():
    random.seed(2026)
    games=[]; players=[]
    for label,gid,away,home,total,mlh,mla in NFL_GAMES:
        games.append(dict(id=gid,away=away,home=home,venue=label,total=total,
            ml_home=mlh,ml_away=mla,imp_home=round(total*mla/(mlh+mla),2) if False else 24.5,
            imp_away=23.5,park=1.0))
    # fix implied splits simply
    for g in games:
        t=g["total"]; h=int(-g["ml_home"]) if g["ml_home"]<0 else 100
        a=int(g["ml_away"]) if g["ml_away"]<0 else 100
        ph=a/(h+a); g["imp_home"]=round(t*ph,2); g["imp_away"]=round(t*(1-ph),2)
    opp_map={}
    for label,gid,away,home,total,mlh,mla in NFL_GAMES:
        opp_map[away]=home; opp_map[home]=away
    for team,ros in NFL_ROSTERS.items():
        for name,pos,tier in ros:
            base=NFL_BASE[pos[0]]
            proj=_proj_from_tier(base,tier,hi=34 if pos[0]=="DEF" else 40)
            sal=_salary(proj, 4500, 12500, 520, 2200) if pos[0]!="DEF" else _salary(proj,4500,9500,400,1800)
            players.append(dict(name=name,team=team,opp=opp_map[team],pos=pos,role="offense" if pos[0]!="DEF" else "defense",
                salary=sal,proj=proj,consensus=round(proj*0.97+random.uniform(-1,1),1),verified=False,
                note="Sample slate — refreshes in-season",status="sample",
                stats=dict(tier=tier,pos=pos[0])))
    for i,pl in enumerate(sorted(players,key=lambda x:-x["proj"]),1): pl["model_rank"]=i
    return dict(meta=dict(date="Aug 2026 (preseason sample)", site="FanDuel", cap=60000,
        scoring="FanDuel NFL Classic", slate="2-game sample slate",
        odds_source="modeled", fresh="sample — not live", sample=True),
        games=games, players=players)

def build_nba():
    random.seed(7)
    games=[]; players=[]
    for label,gid,away,home,total,mlh,mla in NBA_GAMES:
        games.append(dict(id=gid,away=away,home=home,venue=label,total=total,
            ml_home=mlh,ml_away=mla,park=1.0))
        games[-1]["imp_home"]=round(total*0.5,2); games[-1]["imp_away"]=round(total*0.5,2)
    opp_map={}
    for label,gid,away,home,total,mlh,mla in NBA_GAMES:
        opp_map[away]=home; opp_map[home]=away
    for team,ros in NBA_ROSTERS.items():
        for name,pos,tier in ros:
            base=NBA_BASE[pos[0]]
            proj=_proj_from_tier(base,tier,hi=72)
            sal=_salary(proj, 3500, 11500, 130, 600)
            players.append(dict(name=name,team=team,opp=opp_map[team],pos=pos,role="player",
                salary=sal,proj=proj,consensus=round(proj*0.96+random.uniform(-1.5,1.5),1),verified=False,
                note="Sample slate — refreshes in-season",status="sample",
                stats=dict(tier=tier,pos=pos[0])))
    for i,pl in enumerate(sorted(players,key=lambda x:-x["proj"]),1): pl["model_rank"]=i
    return dict(meta=dict(date="Aug 2026 (offseason sample)", site="FanDuel", cap=60000,
        scoring="FanDuel NBA Classic", slate="2-game sample slate",
        odds_source="modeled", fresh="sample — not live", sample=True),
        games=games, players=players)

def main():
    out=dict(mlb=build_mlb(), nfl=build_nfl(), nba=build_nba())
    os.makedirs("/home/user/workspace/dfs-pro", exist_ok=True)
    with open("/home/user/workspace/dfs-pro/data.js","w") as f:
        f.write("/* FanDuel DFS data. MLB=live Aug 18 2026; NFL/NBA=modeled samples (refresh in-season). */\n")
        f.write("window.DFS_DATA = "+json.dumps(out,indent=0)+";")
    for s in ["mlb","nfl","nba"]:
        d=out[s]; print(s, "games",len(d["games"]),"players",len(d["players"]),
              "cap",d["meta"]["cap"],"sample",d["meta"]["sample"])
    # spot check
    for nm in ["Shohei Ohtani","Kyle Harrison"]:
        p=[x for x in out["mlb"]["players"] if x["name"]==nm][0]; print("MLB",nm,p["team"],p["pos"],"proj",p["proj"],"sal",p["salary"])
    for nm in ["Josh Allen","Saquon Barkley"]:
        p=[x for x in out["nfl"]["players"] if x["name"]==nm][0]; print("NFL",nm,p["team"],p["pos"],"proj",p["proj"],"sal",p["salary"])
    for nm in ["Nikola Jokic","Stephen Curry"]:
        p=[x for x in out["nba"]["players"] if x["name"]==nm][0]; print("NBA",nm,p["team"],p["pos"],"proj",p["proj"],"sal",p["salary"])

if __name__=="__main__": main()
