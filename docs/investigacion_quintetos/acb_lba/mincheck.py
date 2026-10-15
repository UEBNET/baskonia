import json, sys, gzip, glob, collections
lg, pbpf, season, mid = sys.argv[1:5]
f=sorted(glob.glob(f"/home/user/baskonia/data/raw/{lg}/{season}/*.json.gz"))[-1]
P=json.load(gzip.open(f))["payload"]
def plen(q): return 600 if q<=4 else 300
def tabs(q, rem):  # absolute elapsed seconds
    base = 600*min(q-1,4) + 300*max(q-5,0)
    return base + plen(q) - rem
secs=collections.Counter(); box={}
if lg=="acb":
    pl=sorted(json.load(open(pbpf))["plays"], key=lambda p:p["order"])
    on={True:{},False:{}}
    for p in pl:
        t=tabs(p["quarter"], p["minute"]*60+p["second"]); pid=p.get("playerLicenseId"); s=p["local"]
        if p["playType"] in (599,112): on[s][pid]=t
        elif p["playType"]==115 and pid in on[s]: secs[pid]+=t-on[s].pop(pid)
    end=max(tabs(p["quarter"],p["minute"]*60+p["second"]) for p in pl)
    for s in on:
        for pid,t0 in on[s].items(): secs[pid]+=end-t0
    doc=P["boxscores"][mid]
    for tb in doc["teamBoxscores"]:
        q0=[x for x in tb["statsByPeriods"] if x["quarter"]==0][0]
        for x in q0["stats"]["players"]:
            m=x.get("playTime") or "0:0"; 
            box[x["player"]["id"]]=x["playTime"]
    def tosec(v):
        if v is None: return 0
        if isinstance(v,(int,float)): return v
        parts=[int(float(z)) for z in str(v).split(":")]; return parts[-2]*60+parts[-1] + (parts[0]*3600 if len(parts)==3 else 0)
    box={k:tosec(v) for k,v in box.items()}
else:
    d=json.load(open(pbpf)); acts=sorted(d["pbp"]["actions"], key=lambda a:(a["period"], a["order"], a["action_id"]))
    sc=P["scores"][mid]["scores"]
    on={}
    for side,tid in (("ht",d["pbp"]["ht_id"]),("vt",d["pbp"]["vt_id"])):
        on[tid]={str(r["player_id"]):0 for r in sc[side]["rows"] if str(r.get("sf"))=="1"}
        for r in sc[side]["rows"]: box[str(r["player_id"])]=float(r.get("sec") or 0)
    def te(a): return 600*min(a["period"]-1,4)+300*max(a["period"]-5,0)+a["minute"]*60+a["seconds"]
    for a in acts:
        pid=str(a["player_id"]); t=te(a)
        if a["description"]=="Ingresso": on[a["team_id"]][pid]=t
        elif a["description"]=="Uscita" and pid in on[a["team_id"]]: secs[pid]+=t-on[a["team_id"]].pop(pid)
    end=max(te(a) for a in acts); end=max(end, 600*min(max(a["period"] for a in acts),4)+300*max(max(a["period"] for a in acts)-4,0))
    for tid in on:
        for pid,t0 in on[tid].items(): secs[pid]+=end-t0
diffs=[(k, secs.get(k,0), v) for k,v in box.items()]
err=[abs(a-b) for _,a,b in diffs]
tot=sum(box.values()); tot2=sum(secs.get(k,0) for k in box)
print("box total",tot,"pbp total",tot2, "end", end if lg=="lba" else "")
print(lg, mid, "players",len(diffs),"max |diff| s",max(err),"mean",round(sum(err)/len(err),1), "exact",sum(1 for e in err if e<=1))
