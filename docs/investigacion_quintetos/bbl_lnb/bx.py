import json,re,sys
h=open(sys.argv[1],encoding='utf-8',errors='replace').read()
m=re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',h,re.S)
pp=json.loads(m.group(1))['props']['pageProps']
gs=pp['initialGameStats']
for side in ('homeTeam','guestTeam'):
    t=gs[side]; print(side, list(t.keys()))
    ps=t['playerStats']; print(json.dumps(ps[0],ensure_ascii=False)[:1500])
    break
gd=pp['initialGameData']; print(json.dumps(gd['homeTeam'],ensure_ascii=False)[:600])
print({k:v for k,v in gd['result'].items()})
