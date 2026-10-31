# Estilo unificado de cada club-temporada, de cada etapa de entrenador y de cada jugador de la plantilla
# (para «Evaluación» de Equipos y quintetos). Derivado de atlas/estilos (clubes y jugadores) y quintetos/datos/equipos.
import json,base64,gzip,unicodedata,re,sys
ORIG=sys.argv[1]; OUT=sys.argv[2]
def dec(p):
    t=open(p).read().strip(); return json.loads(gzip.decompress(base64.b64decode(t)) if t.startswith('H4sI') else t)
def nn(s):
    s=unicodedata.normalize('NFKD',str(s)).encode('ascii','ignore').decode().lower()
    if ',' in s: a,b=s.split(',',1); s=b+' '+a
    return ' '.join(sorted(re.findall(r'[a-z]+',s)))
cl=dec(f'{ORIG}/atlas/estilos/clubes.json.gz.txt'); C={c:i for i,c in enumerate(cl['columnas'])}
ju=dec(f'{ORIG}/atlas/estilos/jugadores.json.gz.txt'); I={c:i for i,c in enumerate(ju['columnas'])}
eq=dec(f'{ORIG}/quintetos/datos/equipos.gz.txt')
byj={}
for f in ju['filas']: byj.setdefault(f[I['clave']],[]).append(f)
r3=lambda x: None if x is None else round(x,3)
out={}; nc=nj=nt=ne=0
for f in cl['filas']:
    k=f[C['clave']]
    if f[C['eu']] is None: continue
    o={'u':[f[C['eu']],r3(f[C['eu_p']]),f[C['eu_etiqueta']]],'pr':[r3(x) for x in (f[C['eu_probs']] or [])]}
    ent={}
    for e in f[C['entrenadores']] or []:
        if e.get('eu') is not None: ent[e.get('entrenador_id')]=[e['eu'],r3(e.get('eu_p')),e.get('eu_etiqueta'),[r3(x) for x in (e.get('eu_probs') or [])]]; ne+=1
    if ent: o['ent']=ent
    out[k]=o; nc+=1
for k,p in (eq.get('plantillas') or {}).items():
    rows=byj.get(k) or []
    if not rows or not p.get('j'): continue
    lst=[]
    for j in p['j']:
        nt+=1; m=[f for f in rows if nn(f[I['nombre']])==nn(j[0]) and f[I['eu']] is not None]
        if not m: lst.append(None); continue
        f=min(m,key=lambda x: abs((x[I['min']] or 0)-(j[3] or 0))); lst.append([f[I['eu']],r3(f[I['eu_p']]),f[I['eu_etiqueta']]]); nj+=1
    out.setdefault(k,{})['pl']=lst
meta=json.load(open(f'{ORIG}/atlas/estilos/meta.json'))
VIEJO=re.compile(r'^(Creación individual|Exterior y presión|Lejos del aro|Pausado y seguro|Pintura física|Circulación y triple|Exterior y riesgo|Ritmo y juego limpio|Ataque al aro|Perímetro y presión)\s*:\s*')
limpio=lambda v: (lambda x: x[:1].upper()+x[1:])(VIEJO.sub('',v)) if isinstance(v,str) else v
res={'estilos':[{k:limpio(e.get(k)) for k in ('id','nombre','definicion','equipo')} for e in meta['estilos_unificados']['estilos']],'generado':'2026-10-29','nota':'Estilo unificado por club-temporada (clave liga:club:temporada), por entrenador (id) y por jugador de la plantilla (mismo orden que plantillas[k].j de equipos.gz.txt). Derivado del Atlas de Estilos.','c':out}
raw=gzip.compress(json.dumps(res,ensure_ascii=False,separators=(',',':')).encode(),9)
open(OUT,'w').write(base64.b64encode(raw).decode()); print(nc,'clubes',ne,'etapas',nj,'/',nt,'jugadores de plantilla',len(raw),'bytes')
