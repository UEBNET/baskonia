import json,re,sys
h=open(sys.argv[1],encoding='utf-8',errors='replace').read()
pp=json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',h,re.S).group(1))['props']['pageProps']
gs=pp['initialGameStats']; A=sorted(gs['actions'],key=lambda a:a['orderId'])
name={}; on={}
for side in ('homeTeam','guestTeam'):
    t=gs[side]; on[str(t['id'])]=set()
    for p in t['playerStats']:
        pid=p['seasonPlayer']['id']; name[pid]=p['seasonPlayer']['lastName']
        if p['isStartingFive']: on[str(t['id'])].add(pid)
print({k:[name[x] for x in v] for k,v in on.items()})
for a in A[:int(sys.argv[2])]:
    if a['type']=='SUBSTITUTION' or a['period']>1 and a['type'] in('START',):
        print(a['orderId'],a['period'],a['gameTime'],a['seasonTeamId'],'P:',name.get(a.get('seasonPlayerId')),'A:',name.get(a.get('assistingSeasonPlayerId')),a['qualifiers'],a['actionIdentifier'])
