import json, sys, collections
QS=('FirstQuarter','SecondQuarter','ThirdQuarter','ForthQuarter','ExtraTime')
def secs(mt): m,s=mt.split(':'); return int(m)*60+int(s)
def run(tag, base):
    d=json.load(open(f"{base}/live_PlayByPlay_{tag}.json")); b=json.load(open(f"{base}/live_Boxscore_{tag}.json"))
    teams=[d['CodeTeamA'].strip(), d['CodeTeamB'].strip()]
    box_min={}; st=[]
    for t in b['Stats']:
        s=set()
        for ps in t['PlayersStats']:
            pid=ps['Player_ID'].strip()
            if ps['IsStarter']: s.add(pid)
            m=ps['Minutes']
            box_min[pid]=secs(m) if ':' in str(m) else 0
        st.append(s)
    on={teams[0]:set(st[0]), teams[1]:set(st[1])}
    played=collections.Counter(); notfive=0
    # elapsed game clock
    period=0; last_el=0; periods_seen=0
    lineup_secs=collections.Counter(); ast_pairs=collections.Counter(); ast_unlinked=0
    ev=[]
    for qi,q in enumerate(QS):
        for e in (d.get(q) or []): ev.append((qi,e))
    cur_per=None; cur_q=0
    for k,(qi,e) in enumerate(ev):
        pt=e['PLAYTYPE']
        if pt=='BP':
            cur_per=(cur_per or 0)+1; plen=600 if cur_per<=4 else 300
            pstart=(cur_per-1)*600 if cur_per<=4 else 2400+(cur_per-5)*300
            last_el=pstart; cur_q=qi; continue
        mt=e.get('MARKERTIME') or ''
        if pt in('EP','EG') or not mt:
            if pt=='EP' or pt=='EG':
                el=pstart+plen
            else: continue
        else:
            el=pstart+plen-secs(mt)
        dt=el-last_el
        if qi!=cur_q: dt=0; el=last_el
        if dt<0: dt=0
        for t,s in on.items():
            for p in s: played[p]+=dt
            lineup_secs[(t,frozenset(s))]+=dt
        last_el=max(last_el,el)
        tm=(e['CODETEAM'] or '').strip(); pid=(e['PLAYER_ID'] or '').strip()
        if pt=='IN': on[tm].add(pid)
        elif pt=='OUT': on[tm].discard(pid)
        elif pt=='AS':
            j=k-1
            while j>=0 and ev[j][1]['PLAYTYPE'] in ('IN','OUT','CM','RV'): j-=1
            pe=ev[j][1]
            if pe['PLAYTYPE'] in ('2FGM','3FGM','FTM') and (pe['CODETEAM'] or '').strip()==tm: ast_pairs[(pid,pe['PLAYER_ID'].strip())]+=1
            else: ast_unlinked+=1
        if pt in('IN','OUT'):
            nxt=ev[k+1][1]['PLAYTYPE'] if k+1<len(ev) else ''
            if nxt not in('IN','OUT') and any(len(s)!=5 for s in on.values()): notfive+=1
    bigs=[(p,played[p],box_min[p]) for p in box_min if abs(played[p]-box_min[p])>5]; print(bigs)
    diffs=[abs(played[p]-box_min[p]) for p in box_min if box_min[p]>0 or played[p]>0]
    print(f"{tag}: periods={cur_per} notfive={notfive} lineups={len(lineup_secs)} max|min diff|={max(diffs)}s mean={sum(diffs)/len(diffs):.1f}s ast_linked={sum(ast_pairs.values())} unlinked={ast_unlinked} total_secs={sum(lineup_secs.values())//2}")
for tag in sys.argv[2:]:
    try: run(tag, sys.argv[1])
    except Exception as ex: print(tag,'ERR',repr(ex))
