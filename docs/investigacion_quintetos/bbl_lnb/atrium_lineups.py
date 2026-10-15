import json,sys,re,collections
def iso(s):
    m=re.match(r'PT(?:(\d+)M)?(?:([\d.]+)S)?',s or 'PT0S'); return int(m.group(1) or 0)*60+float(m.group(2) or 0)
def run(box_path,pbp_path):
    B=json.load(open(box_path))['data']; P=json.load(open(pbp_path))['data']
    fx=B['fixture']; comp={c['entityId'] if 'entityId' in c else None:c for c in fx['competitors']}
    box={}; on=collections.defaultdict(set); team={}
    for side in ('home','away'):
        for grp in B['statistics']['data']['base'][side]['persons']:
            for r in grp['rows']:
                s=r.get('statistics') or {}
                box[r['personId']]=(iso(s.get('minutes')) if isinstance(s.get('minutes'),str) else s.get('minutes'), s.get('plusMinus'), s.get('assists'), r.get('starter'), s.get('points'))
                team[r['personId']]=r['entityId']
                if r.get('starter'): on[r['entityId']].add(r['personId'])
    tids=list(on)
    sec=collections.Counter(); pm=collections.Counter(); ast=collections.Counter(); lineups=collections.Counter()
    last_t=0; prev_scores={t:0 for t in tids}; bad=0; n5=0; nn=0; ast_unlinked=0
    E=[e for p in P['periodData'] for e in p['events']]
    import os
    if os.environ.get('SORT'): E=sorted(E,key=lambda e:(e['periodId'],-iso(e['clock'])))
    plen={p['periodId']:p['durationMinutes']*60 for p in P['periodData']}
    before={}; acc=0
    for p in sorted(plen): before[p]=acc; acc+=plen[p]
    prev=None
    for e in E:
        t=before[e['periodId']]+plen[e['periodId']]-iso(e['clock'])
        dt=t-last_t
        if dt>0:
            for tid in tids:
                for pid in on[tid]: sec[pid]+=dt
                lineups[(tid,frozenset(on[tid]))]+=dt
                n5+= dt if len(on[tid])==5 else 0; nn+=dt
        last_t=max(t,last_t)
        sc=e.get('scores') or {}
        if sc and all(k in sc for k in tids):
            d={k:sc[k]-prev_scores[k] for k in tids}
            if any(d.values()):
                for tid in tids:
                    o=[x for x in tids if x!=tid][0]
                    for pid in on[tid]: pm[pid]+=d[tid]-d[o]
                prev_scores={k:sc[k] for k in tids}
        if e['eventType']=='assist':
            ast[e['personId']]+=1
            if not (prev and prev['eventType'] in('2pt','3pt','freeThrow') and prev.get('success') and prev['entityId']==e['entityId']): ast_unlinked+=1
        if e['eventType']=='substitution':
            if e['eventSubType']=='out':
                if e['personId'] in on[e['entityId']]: on[e['entityId']].discard(e['personId'])
                else: bad+=1
            else: on[e['entityId']].add(e['personId'])
        prev=e
    dsec=[abs(sec[p]-(box[p][0] or 0)) for p in box]
    dpm=[p for p in box if box[p][1] is not None and box[p][1]!=pm[p]]
    dast=[p for p in box if (box[p][2] or 0)!=ast[p]]
    shots=[e for e in E if e['eventType'] in('2pt','3pt')]
    res=dict(fixture=fx['name'],date=fx['startTimeLocal'][:10],events=len(E),starters=[len(on[t]) for t in tids] if False else None,
        bad_subs=bad,final=prev_scores,max_sec_diff=round(max(dsec),1),n_sec_diff_gt10=sum(x>10 for x in dsec),pm_mismatch=len(dpm),ast_mismatch=len(dast),ast_unlinked=ast_unlinked,
        lineups=len(lineups),pct_5man=round(n5/max(nn,1),3),shots=len(shots),shots_xy=sum(1 for e in shots if e['x'] is not None))
    print(json.dumps(res,ensure_ascii=False))
run(sys.argv[1],sys.argv[2])
