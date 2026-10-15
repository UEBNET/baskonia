import json, sys, collections
d=json.load(open(sys.argv[1])); pl=sorted(d["plays"], key=lambda p:p["order"])
# assist increments
inc=collections.Counter(); prev={}
for p in pl:
    pid=p.get("playerLicenseId"); st=p.get("playerStats") or {}
    if pid and "assists" in st:
        a=st["assists"]; 
        if a!=prev.get(pid,0): inc[(p["playType"], a-prev.get(pid,0))]+=1
        prev[pid]=a
print("assist-increment by playType", inc)
# assist attribution: preceding made FG by same team
made={93,94,100}; ok=bad=0; examples=[]
for i,p in enumerate(pl):
    if p["playType"]==107:
        q=pl[i-1]
        if q["playType"] in (93,94,100,96,95) and q["local"]==p["local"]: ok+=1
        else:
            bad+=1; examples.append((q["playType"],q["local"],p["local"],q.get("playerName"),p.get("playerName")))
print("assist after made FG same team",ok,"other",bad,examples[:5])
# lineups
on={True:set(),False:set()}; sizes=collections.Counter(); secs=collections.Counter()
def t(p):
    q=p["quarter"]; L=600 if q<=4 else 300
    return (min(q,4)-1)*600+(q-5)*300*(q>4)+ (2400 if q>4 else 0) + L-(p["minute"]*60+p["second"]) if False else None
for p in pl:
    pt=p["playType"]; side=p["local"]; pid=p.get("playerLicenseId")
    if pt==599: on[side].add(pid)
    elif pt==112: on[side].add(pid)
    elif pt==115: on[side].discard(pid)
    elif pt in (93,94,92,98,97,101,104,110,106):
        sizes[(len(on[True]),len(on[False]))]+=1
print("on-court sizes at events", sizes.most_common(5))
print("quarters", sorted(set(p['quarter'] for p in pl)), "clock sample", [(p['quarter'],p['minute'],p['second']) for p in pl[-3:]])
print("starters flagged:", sum(1 for p in pl if p['playType']==599))
for code,prevs in ((108,(94,)),(107,(93,100,96,95))):
    c=collections.Counter(pl[i-1]["playType"] for i,p in enumerate(pl) if p["playType"]==code); print(code,"preceded by",c)
c=collections.Counter(pl[i+1]["playType"] for i,p in enumerate(pl) if p["playType"]==119 and i+1<len(pl)); print(119,"followed by",c)
