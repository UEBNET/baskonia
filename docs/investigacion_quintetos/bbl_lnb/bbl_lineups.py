import json,re,sys,collections
def load(path):
    h=open(path,encoding='utf-8',errors='replace').read()
    m=re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',h,re.S)
    return json.loads(m.group(1))['props']['pageProps']
def secs(t):
    h,m,s=map(int,t.split(':')); return h*3600+m*60+s
def run(path):
    pp=load(path); gd=pp['initialGameData']; gs=pp['initialGameStats']; A=sorted(gs['actions'] or [],key=lambda a:a['orderId'])
    home=gd['homeTeam']['seasonTeamId'] if gd['homeTeam'].get('seasonTeamId') else gd['homeTeam']['teamId']
    box={}; team_of={}; on={}
    for side in ('homeTeam','guestTeam'):
        t=gs[side]; tid=str(t['id']); on[tid]=set()
        for p in t['playerStats']:
            pid=str(p['seasonPlayer']['id']); team_of[pid]=tid
            box[pid]=(p['secondsPlayed'] or 0, p['plusMinus'], p['assists'], p['isStartingFive'], p['points'])
            if p['isStartingFive']: on[tid].add(pid)
    tids=list(on); print(gd['id'],gd['seasonId'],gd['stage'],'actions',len(A),'starters',[len(on[t]) for t in tids],'home id',home, 'tids',tids)
    sec=collections.Counter(); pm=collections.Counter(); ast=collections.Counter()
    plen=lambda p: 600 if p<=4 else 300
    prev_clock=None; prev_period=None; score={'h':0,'g':0}
    hid=str(gs['homeTeam']['id'])
    lineups=collections.Counter(); sub_dir=collections.Counter(); bad=0
    def elapsed(a): return sum(plen(p) for p in range(1,a['period']))+plen(a['period'])-secs(a['gameTime'])
    last_t=0
    for a in A:
        t=elapsed(a)
        dt=t-last_t
        if dt>0:
            for tid in tids:
                for pid in on[tid]: sec[pid]+=dt
                lineups[(tid,frozenset(on[tid]))]+=dt
        last_t=max(last_t,t)
        if a.get('homeTeamPoints') is not None:
            dh=a['homeTeamPoints']-score['h']; dg=a['guestTeamPoints']-score['g']
            score['h'],score['g']=a['homeTeamPoints'],a['guestTeamPoints']
            for tid in tids:
                d=(dh-dg) if tid==hid else (dg-dh)
                for pid in on[tid]: pm[pid]+=d
        if a['type'] in('TWO_POINT_THROW','THREE_POINT_THROW') and a['isSuccessful'] and a.get('assistingSeasonPlayerId'):
            ast[a['assistingSeasonPlayerId']]+=1
        if a['type']=='SUBSTITUTION':
            tid=str(a['seasonTeamId']); x=a.get('seasonPlayerId'); y=a.get('assistingSeasonPlayerId')
            if x in on[tid] and y not in on[tid]: on[tid].discard(x); on[tid].add(y); sub_dir['player=OUT,assist=IN']+=1
            elif y in on[tid] and x not in on[tid]: on[tid].discard(y); on[tid].add(x); sub_dir['player=IN,assist=OUT']+=1
            else: bad+=1
    print(' sub direction',dict(sub_dir),'unresolved',bad,'final score',score, gd['result']['homeTeamFinalScore'],gd['result']['guestTeamFinalScore'])
    dsec=[abs(sec[p]-box[p][0]) for p in box]; 
    dpm=[ (p,pm[p],box[p][1]) for p in box if str(box[p][1]) not in ('',) and int(box[p][1] or 0)!=pm[p]]
    dast=[(p,ast[p],box[p][2]) for p in box if ast[p]!=box[p][2]]
    print(' max |sec diff|',max(dsec),'players with sec diff>5:',sum(d>5 for d in dsec),'/',len(box))
    print(' +/- mismatches',dpm[:5],len(dpm))
    print(' assist mismatches',dast[:5],len(dast))
    print(' lineups seen',len(lineups),'all 5-man:',all(len(k[1])==5 for k in lineups))
for p in sys.argv[1:]: run(p)
