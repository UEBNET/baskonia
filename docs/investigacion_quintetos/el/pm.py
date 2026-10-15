import json, sys
QS=('FirstQuarter','SecondQuarter','ThirdQuarter','ForthQuarter','ExtraTime')
def run(tag, base):
    d=json.load(open(f"{base}/live_PlayByPlay_{tag}.json")); b=json.load(open(f"{base}/live_Boxscore_{tag}.json"))
    A,Bt=d['CodeTeamA'].strip(), d['CodeTeamB'].strip()
    st=[]; boxpm={}
    for t in b['Stats']:
        s=set()
        for ps in t['PlayersStats']:
            pid=ps['Player_ID'].strip(); boxpm[pid]=ps['Plusminus']
            if ps['IsStarter']: s.add(pid)
        st.append(s)
    on={A:set(st[0]),Bt:set(st[1])}; pm={}
    sa=sb=0
    ev=[e for q in QS for e in (d.get(q) or [])]
    for e in ev:
        pt=e['PLAYTYPE']; tm=(e['CODETEAM'] or '').strip(); pid=(e['PLAYER_ID'] or '').strip()
        if pt=='IN': on[tm].add(pid); continue
        if pt=='OUT': on[tm].discard(pid); continue
        pts={'2FGM':2,'3FGM':3,'FTM':1}.get(pt)
        if pts:
            sign=1 if tm==A else -1
            for p in on[A]: pm[p]=pm.get(p,0)+sign*pts
            for p in on[Bt]: pm[p]=pm.get(p,0)-sign*pts
            if tm==A: sa+=pts
            else: sb+=pts
    mism=[(p,pm.get(p,0),boxpm[p]) for p in boxpm if pm.get(p,0)!=boxpm[p]]
    print(tag,'score',sa,sb,'pm mismatches',len(mism),mism[:4])
for t in sys.argv[2:]: run(t, sys.argv[1])
