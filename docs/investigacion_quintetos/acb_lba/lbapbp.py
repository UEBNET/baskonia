import json, sys, collections
d=json.load(open(sys.argv[1])); print("top", list(d.keys()), "pbp keys", list(d["pbp"].keys()) if isinstance(d.get("pbp"),dict) else type(d.get("pbp")))
acts=d["pbp"]["actions"]; print("n", len(acts))
c=collections.Counter(a["description"] for a in acts); print(c.most_common())
acts=sorted(acts, key=lambda a:(a["period"], a["order"], a["action_id"]))
for a in acts[:int(sys.argv[2]) if len(sys.argv)>2 else 25]:
    print(a["action_id"],a["order"],a["period"],a["minute"],a["seconds"],a["print_time"],a["description"],a["team_id"],a["player_id"],a.get("player_surname"),a["linked_action_id"],a["x"],a["y"],a["score"],a["action_1_qualifier_description"])
byid={a["action_id"]:a for a in acts}
ast=[a for a in acts if a["description"]=="Assist"]
lk=collections.Counter(byid.get(a["linked_action_id"],{}).get("description") for a in ast)
print("assist linked to:", lk, "same team", sum(1 for a in ast if byid.get(a["linked_action_id"],{}).get("team_id")==a["team_id"]), "/", len(ast))
xy=sum(1 for a in acts if a["x"] is not None); print("actions with x,y", xy)
