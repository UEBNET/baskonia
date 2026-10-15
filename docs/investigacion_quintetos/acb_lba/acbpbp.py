import json, sys, collections
d=json.load(open(sys.argv[1]))
print("top keys", list(d.keys()))
pl=d["plays"]; print("n plays", len(pl)); print("play keys", sorted(set(k for p in pl for k in p)))
c=collections.Counter((p["playType"]) for p in pl)
print(c.most_common())
# print first 40 plays compact
for p in pl[:int(sys.argv[2]) if len(sys.argv)>2 else 40]:
    print(p["order"],p["playType"],p.get("playTag"),p["quarter"],f'{p["minute"]}:{p["second"]:02d}',"L" if p["local"] else "V",p["scoreHome"],p["scoreAway"],p.get("playerName"),p.get("playerLicenseId"),p.get("licenseType"))
