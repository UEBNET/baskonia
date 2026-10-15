import json,re,sys,collections
for f in sys.argv[1:]:
    h=open(f).read()
    pp=json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',h,re.S).group(1))['props']['pageProps']
    gd=pp['initialGameData']; A=pp['initialGameStats']['actions'] or []
    ids={p['seasonPlayer']['id'] for s in('homeTeam','guestTeam') for p in pp['initialGameStats'][s]['playerStats']}
    c=collections.Counter(); t=collections.Counter()
    for a in A:
        t[a['type']]+=1
        if a.get('seasonPlayerId'): c[a['type']]+=1
    unk=sum(1 for a in A if a.get('seasonPlayerId') and a['seasonPlayerId'] not in ids)
    print(gd['id'],gd['seasonId'],gd['stage'],'withPlayer/total by type:',{k:f"{c[k]}/{t[k]}" for k in ('SUBSTITUTION','TWO_POINT_THROW','REBOUND','FOUL','FREE_THROW','TURN_OVER')},'unknown ids',unk)
