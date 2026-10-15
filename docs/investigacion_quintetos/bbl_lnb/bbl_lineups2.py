import json,re,sys,collections
def load(path):
    h=open(path,encoding='utf-8',errors='replace').read()
    m=re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',h,re.S)
    return json.loads(m.group(1))['props']['pageProps']
def secs(t):
    h,m,s=map(int,t.split(':')); return h*3600+m*60+s
plen=lambda p: 600 if p<=4 else 300
def period_starters(A,period,tid,prev_on):
    """players whose first appearance in the period is not being subbed IN"""
    first={}; 
    for a in A:
        if a['period']!=period or str(a['seasonTeamId'])!=tid: continue
        if a['type']=='SUBSTITUTION':
            o,i=a.get('seasonPlayerId'),a.get('assistingSeasonPlayerId')
            first.setdefault(o,'act'); first.setdefault(i,'in')
        elif a['type'].startswith('JUMP_BALL'):
            if a.get('seasonPlayerId'): first.setdefault(a['seasonPlayerId'],'act')
        else:
            if a.get('seasonPlayerId'): first.setdefault(a['seasonPlayerId'],'act')
            if a.get('assistingSeasonPlayerId'): first.setdefault(a['assistingSeasonPlayerId'],'act')
    s={p for p,v in first.items() if v=='act'}
    if len(s)<5:  # fill with previous on-court players not subbed in first
        for p in prev_on:
            if len(s)>=5: break
            if first.get(p)!='in': s.add(p)
    return s
OTHER=collections.Counter()
import os
DEBUG=os.environ.get('DBG')
def run(path,verbose=True):
    pp=load(path)
    if 'initialGameData' not in pp: return None
    gd=pp['initialGameData']; gs=pp['initialGameStats']; A=sorted(gs.get('actions') or [],key=lambda a:a['orderId'])
    if not A: print(gd['id'],'NO ACTIONS'); return None
    box={}; on={}
    for side in ('homeTeam','guestTeam'):
        t=gs[side]; tid=str(t['id']); on[tid]=set()
        for p in t['playerStats']:
            pid=str(p['seasonPlayer']['id'])
            box[pid]=(p['secondsPlayed'] or 0, p['plusMinus'], p['assists'], p['isStartingFive'])
            if p['isStartingFive']: on[tid].add(pid)
    tids=list(on); hid=str(gs['homeTeam']['id'])
    st_ok=[len(on[t]) for t in tids]
    for tid in tids:
        if len(on[tid])!=5: on[tid]=period_starters(A,1,tid,set())
    sec=collections.Counter(); pm=collections.Counter(); ast=collections.Counter()
    score={'h':0,'g':0}; lineups=collections.Counter(); bad=0; cur_period=1; last_t=0; n5=0;nn=0
    def elapsed(a): return sum(plen(p) for p in range(1,a['period']))+plen(a['period'])-secs(a['gameTime'])
    for a in A:
        if a['period']!=cur_period:
            cur_period=a['period']
            for tid in tids: on[tid]=period_starters(A,cur_period,tid,on[tid])
        t=elapsed(a); dt=t-last_t
        if dt>0:
            for tid in tids:
                for pid in on[tid]: sec[pid]+=dt
                lineups[(tid,frozenset(on[tid]))]+=dt
                if len(on[tid])==5: n5+=dt
                nn+=dt
        last_t=max(last_t,t)
        if a.get('homeTeamPoints') is not None:
            dh=a['homeTeamPoints']-score['h']; dg=a['guestTeamPoints']-score['g']
            score['h'],score['g']=a['homeTeamPoints'],a['guestTeamPoints']
            for tid in tids:
                d=(dh-dg) if tid==hid else (dg-dh)
                for pid in on[tid]: pm[pid]+=d
        if a['type'] in('TWO_POINT_THROW','THREE_POINT_THROW') and a['isSuccessful'] and a.get('assistingSeasonPlayerId'):
            ast[a['assistingSeasonPlayerId']]+=1
        if a.get('assistingSeasonPlayerId') and a['type'] not in('TWO_POINT_THROW','THREE_POINT_THROW','SUBSTITUTION') and not a['type'].startswith('JUMP'): OTHER[a['type'],a['isSuccessful']]+=1
        if a['type']=='SUBSTITUTION':
            tid=str(a['seasonTeamId']); o=a.get('seasonPlayerId'); i=a.get('assistingSeasonPlayerId')
            if o in on[tid]: on[tid].discard(o)
            else: bad+=1
            on[tid].add(i)
    dsec=[abs(sec[p]-box[p][0]) for p in box]
    if DEBUG: print([(p,sec[p],box[p]) for p in box if abs(sec[p]-box[p][0])>10]); print('extra ids', [p for p in sec if p not in box])
    dpm=[p for p in box if str(box[p][1]) not in ('','None') and int(box[p][1])!=pm[p]]
    dast=[p for p in box if ast[p]!=box[p][2]]
    adiff=sum(ast[p]-box[p][2] for p in box)
    fs=(gd['result']['homeTeamFinalScore'],gd['result']['guestTeamFinalScore'])
    res=dict(id=gd['id'],season=gd['seasonId'],stage=gd['stage'],n_actions=len(A),starters=st_ok,subs=sum(a['type']=='SUBSTITUTION' for a in A),
             bad_subs=bad,score_ok=(score['h'],score['g'])==fs,max_sec_diff=max(dsec),n_sec_diff_gt10=sum(d>10 for d in dsec),
             pm_mismatch=len(dpm),ast_mismatch=len(dast),ast_sum_diff=adiff,box_sec_null=sum(1 for p in box if not box[p][0]),n_players=len(box),lineups=len(lineups),pct_time_5man=round(n5/max(nn,1),3),
             shots_with_xy=sum(1 for a in A if a['type'] in('TWO_POINT_THROW','THREE_POINT_THROW') and (a['coordinates']['x'] or a['coordinates']['y'])),
             shots=sum(1 for a in A if a['type'] in('TWO_POINT_THROW','THREE_POINT_THROW')))
    print(json.dumps(res)); return res
for p in sys.argv[1:]: run(p)
print('assist on other types',OTHER)
