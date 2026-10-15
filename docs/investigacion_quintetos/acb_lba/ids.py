import gzip, json, sys, glob
for lg in ("acb","lba"):
    for s in ("2020-21","2023-24","2025-26","2026-27"):
        f=sorted(glob.glob(f"/home/user/baskonia/data/raw/{lg}/{s}/*.json.gz"))[-1]
        d=json.load(gzip.open(f))
        p=d.get("payload",d)
        if lg=="acb":
            ids=list(p["boxscores"].keys()); extra=p.get("edition_id")
        else:
            ids=list(p["scores"].keys()); extra=[ (c["id"],c.get("ctype_code")) for c in p["championships"]]
        print(lg,s,len(ids),ids[:3],ids[-2:],extra, list(d.keys())[:5])
