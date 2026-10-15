import json,sys
for f in sys.argv[1:]:
    try: d=json.load(open(f))
    except Exception as e: print(f,"ERR",e, open(f,'rb').read(200)); continue
    rs=d.get("resultSets",d.get("resultSet"))
    if isinstance(rs,dict): rs=[rs]
    for r in rs or []:
        h=r.get("headers"); rows=r.get("rowSet") or []
        print(f, r.get("name"), "rows=",len(rows), "hdr=",h if len(str(h))<900 else str(h)[:900])
        if rows: print("   ex:", str(rows[0])[:400])
