import json,sys,collections
f=sys.argv[1]; d=json.load(open(f))
if "game" in d:  # v3
    acts=d["game"]["actions"]; print("v3 keys", list(acts[0].keys()))
    c=collections.Counter(a.get("actionType") for a in acts); print(len(acts), c.most_common(20))
    subs=[a for a in acts if a.get("actionType")=="Substitution"][:2]; print("sub ex", subs)
    mk=[a for a in acts if a.get("actionType")=="Made Shot"][:2]; print("made ex", mk)
else:
    rs=d["resultSets"][0]; h=rs["headers"]; rows=[dict(zip(h,r)) for r in rs["rowSet"]]
    c=collections.Counter(r["EVENTMSGTYPE"] for r in rows); print(len(rows), sorted(c.items()))
    print("sub ex", [r for r in rows if r["EVENTMSGTYPE"]==8][:1])
    print("made ex", [r for r in rows if r["EVENTMSGTYPE"]==1 and r["PLAYER2_ID"]][:1])
    for s in d["resultSets"][1:]: print(s["name"], len(s["rowSet"]))
