# Genera quintetos/datos/estilos_unificados.gz.txt: estilo unificado (taxonomía nueva) de cada jugador de Equipos y quintetos,
# enlazado con el Atlas por club-temporada y player_id (o nombre normalizado). Derivado de datos ya publicados; no toca el pipeline.
import json,base64,gzip,glob,os,unicodedata,re,sys
ORIG=sys.argv[1]; OUT=sys.argv[2]
def dec(p):
    t=open(p).read().strip(); return json.loads(gzip.decompress(base64.b64decode(t)) if t.startswith('H4sI') else t)
def nn(s):
    s=unicodedata.normalize('NFKD',str(s)).encode('ascii','ignore').decode().lower()
    if ',' in s: a,b=s.split(',',1); s=b+' '+a
    return ' '.join(sorted(re.findall(r'[a-z]+',s)))
d=dec(f'{ORIG}/atlas/estilos/jugadores.json.gz.txt'); C=d['columnas']; I={c:i for i,c in enumerate(C)}
meta=json.load(open(f'{ORIG}/atlas/estilos/meta.json'))
byc={}
for f in d['filas']: byc.setdefault(f[I['clave']],[]).append(f)
mapa={}; n=0
for p in sorted(glob.glob(f'{ORIG}/quintetos/datos/20*/*.gz.txt')):
    t,l=p.split('/')[-2],os.path.basename(p).split('.')[0]
    q=dec(p); J={x:i for i,x in enumerate(q['jugadores']['c'])}
    for r in q['jugadores']['f']:
        cl=f"{l}:{r[J['team_id']]}:{t}"; rows=byc.get(cl) or []
        m=[f for f in rows if str(f[I['pid']])==str(r[J['player_id']])] or [f for f in rows if nn(f[I['nombre']])==nn(r[J['nombre']])]
        if not m or m[0][I['eu']] is None: continue
        f=max(m,key=lambda x:x[I['min']]); n+=1
        mapa[f"{l}|{t}|{r[J['team_id']]}|{r[J['player_id']]}"]=[f[I['eu']], f[I['eu_p']], f[I['eu_etiqueta']]]
eus=[{k:e[k] for k in ('id','nombre','definicion','jugador','rol_jugador')} for e in meta['estilos_unificados']['estilos']]
out={'generado':'2026-10-29','nota':'Estilo unificado (Pistons, Isolation, Old-School, Spacing, Circulación, Pintura) por liga|temporada|team_id|player_id, enlazado con el Atlas.','estilos':eus,'j':mapa}
raw=gzip.compress(json.dumps(out,ensure_ascii=False,separators=(',',':')).encode(),9)
open(OUT,'w').write(base64.b64encode(raw).decode()); print(n,'jugadores',len(raw),'bytes')
