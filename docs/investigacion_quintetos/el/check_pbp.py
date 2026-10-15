import json, sys, collections
QS=('FirstQuarter','SecondQuarter','ThirdQuarter','ForthQuarter','ExtraTime')
def run(pbp_path, box_path, pts_path):
    d=json.load(open(pbp_path)); b=json.load(open(box_path)); p=json.load(open(pts_path))
    ev=[e for q in QS for e in (d.get(q) or [])]
    teams=[d['CodeTeamA'].strip(), d['CodeTeamB'].strip()]
    starters={}
    for t in b['Stats']:
        for ps in t['PlayersStats']:
            if ps['IsStarter']: starters.setdefault(ps['Team'].strip(),set()).add(ps['Player_ID'].strip())
    # box team codes may differ from pbp CODETEAM? map by order
    st=list(starters.values())
    oncourt={teams[0]:set(st[0]), teams[1]:set(st[1])} if len(st)==2 else {}
    bad=0; nin=nout=0; ast_ok=ast_bad=0; ts_ok=0
    last_fgm=None
    for i,e in enumerate(ev):
        pt=e['PLAYTYPE']; tm=(e['CODETEAM'] or '').strip(); pid=(e['PLAYER_ID'] or '').strip()
        if e.get('MARKERTIME'): ts_ok+=1
        if pt=='IN': nin+=1; oncourt.setdefault(tm,set()).add(pid)
        elif pt=='OUT': nout+=1; oncourt.setdefault(tm,set()).discard(pid)
        elif pt in ('2FGM','3FGM'): last_fgm=(i,tm,pid)
        elif pt=='AS':
            # previous scoring event (skipping subs) same team
            j=i-1
            while j>=0 and ev[j]['PLAYTYPE'] in ('IN','OUT'): j-=1
            if j>=0 and ev[j]['PLAYTYPE'] in ('2FGM','3FGM','FTM') and (ev[j]['CODETEAM'] or '').strip()==tm: ast_ok+=1
            else: ast_bad+=1
        # check after a run of subs ends
        nxt=ev[i+1]['PLAYTYPE'] if i+1<len(ev) else ''
        if pt in ('IN','OUT') and nxt not in ('IN','OUT'):
            for t,s in oncourt.items():
                if len(s)!=5: bad+=1
    ptsrows=p.get('Rows') or []
    print(f"{pbp_path.split('/')[-1]}: events={len(ev)} IN={nin} OUT={nout} starters={[len(s) for s in st]} oncourt_not5_after_subs={bad} AS_after_FGM_same_team={ast_ok} AS_unlinked={ast_bad} markertime_filled={ts_ok}/{len(ev)} shots={len(ptsrows)} shot_keys={sorted(ptsrows[0].keys()) if ptsrows else None if 0 else ''}")
    # final oncourt
    print('   final oncourt sizes', {t:len(s) for t,s in oncourt.items()}, 'TYPE values', collections.Counter(e.get('TYPE') for e in ev))
for s in sys.argv[2:]:
    base=sys.argv[1]
    try: run(f"{base}/live_PlayByPlay_{s}.json" if 'E2024' not in s else f"{base}/v1_pbp_E2024_1.json", f"{base}/live_Boxscore_{s}.json", f"{base}/live_Points_{s}.json")
    except Exception as ex: print(s,'ERR',repr(ex))
