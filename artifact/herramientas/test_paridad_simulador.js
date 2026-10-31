const fs=require('fs'),zlib=require('zlib');
const L=(p)=>JSON.parse(zlib.gunzipSync(Buffer.from(fs.readFileSync(p,'utf8').trim(),'base64')));
// Uso: node test_paridad_simulador.js <carpeta publicada anterior> <simulador_v2.js nuevo>
// Comprueba que sin rol asignado el motor v2.1 da lo mismo que el anterior y que con rol cambia la salida.
const ANT=process.argv[2], NUEVO=process.argv[3];
const dir=ANT+'/atlas/simulador/';
const m=L(dir+'meta.json.gz.txt'),j=L(dir+'jugadores.json.gz.txt'),c=L(dir+'clubes.json.gz.txt');
const A=require(require('path').resolve(ANT+'/atlas/simulador_v2.js')); delete require.cache;
const Bpath=require('path').resolve(NUEVO);
const B=require(Bpath);
console.log('version', B.VERSION);
const DA=A.cargar(m,j,c); const DB=B.cargar(m,j,c);
const club=[...DB.porClub.values()].find(x=>x.liga==='euroleague'&&x.temporada==='2025-26'&&/Baskonia|BAS/i.test(x.nombre+x.team));
const rec=[...DB.jug.values()].find(r=>r.temporada==='2025-26'&&r.liga==='acb'&&r.min_total>800&&r.team!==club.team);
console.log(club.nombre, rec.nombre, rec.rol);
const ra=A.simular({rec:DA.jug.get(rec.id),club:[...DA.porClub.values()].find(x=>x.team===club.team&&x.temporada===club.temporada&&x.liga===club.liga)});
const rb=B.simular({rec,club});
console.log('sin rol: igual fit', ra.fit.total===rb.fit.total, ra.minutos.media===rb.minutos.media, rb.version_motor);
for(const r of B.ROLES){const x=B.simular({rec,club,rol:r});console.log(r.padEnd(12),'min',x.minutos.media.toFixed(1),'['+x.minutos.lo90.toFixed(1)+'-'+x.minutos.hi90.toFixed(1)+']','tit',x.p_titular.toFixed(2),'fit',x.fit.total.toFixed(3),'pts/pp',x.por_partido.pts.media.toFixed(1),'adapt',x.adaptacion.adapt_pct_temporada.media.toFixed(1),'dnet',x.equipo.d_net.toFixed(2),'rolEsp',x.rol_esperado);}
