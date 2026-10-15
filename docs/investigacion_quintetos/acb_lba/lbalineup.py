import json, sys, gzip, glob, collections
pbpf, season, mid = sys.argv[1], sys.argv[2], sys.argv[3]
f=sorted(glob.glob(f"/home/user/baskonia/data/raw/lba/{season}/*.json.gz"))[-1]
p=json.load(gzip.open(f))["payload"]; sc=p["scores"][mid]["scores"]
d=json.load(open(pbpf)); acts=sorted(d["pbp"]["actions"], key=lambda a:(a["period"], a["order"], a["action_id"]))
ht,vt=d["pbp"]["ht_id"],d["pbp"]["vt_id"]; print("ht vt",ht,vt, "legend", str(d.get("legend"))[:300])
starters={}
for side in ("ht","vt"):
    rows=sc[side]["rows"]; starters[side]={str(r["player_id"]) for r in rows if str(r.get("sf"))=="1"}
    print(side,"starters",len(starters[side]), "team ids in rows?", set(r.get("team_id") for r in rows))
team_of={}
for a in acts:
    if a["player_id"]: team_of[str(a["player_id"])]=a["team_id"]
on={}
for side,tid in (("ht",ht),("vt",vt)):
    on[tid]=set(starters[side])
sizes=collections.Counter(); bad=[]
for a in acts:
    pid=str(a["player_id"]) if a["player_id"] else None; t=a["team_id"]
    if a["description"]=="Ingresso": on[t].add(pid)
    elif a["description"]=="Uscita": on[t].discard(pid)
    elif t in on and pid:
        s=(len(on[ht]),len(on[vt])); sizes[s]+=1
        if pid not in on[t]: bad.append((a["period"],a["print_time"],a["description"],a["player_surname"]))
print("sizes", sizes.most_common(4), "actor-not-on-court", len(bad), bad[:5])
# minutes check
