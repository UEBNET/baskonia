// Paridad del motor del navegador v3.3 (artifact/atlas/simulador.js) con Python (bbfit.simulador, CERNO_SIMULADOR=v33).
//   CERNO_SIMULADOR=v33 python -c "from bbfit import sim_exportar as E; E.paridad('<carpeta>')"   # casos → <carpeta>/paridad.json
//   node tests/js/paridad_simulador.js [<carpeta de exportar-simulador>] [<simulador.js>]
// (por defecto experimentos/v33_artifact/simulador y artifact/atlas/simulador.js)
// Los números aleatorios no son los de numpy: se compara en distribución (tolerancias del error Monte Carlo).
const fs = require("fs"), path = require("path");
const R = path.join(__dirname, "..", "..");
const dir = process.argv[2] || path.join(R, "experimentos", "v33_artifact", "simulador");
const S = require(path.resolve(process.argv[3] || path.join(R, "artifact", "atlas", "simulador.js")));
const L = (f) => JSON.parse(fs.readFileSync(path.join(dir, f), "utf8"));
const D = S.cargar(L("meta.json"), L("jugadores.json"), L("clubes.json"));
const ref = L("paridad.json");
let mal = 0;
const tol = { minutos: 1.5, pts: 1.2, ts: 1.2, usg: 1.0 };
for (const c of ref) {
  const [liga, team, temp] = c.club.split("|");
  const club = [...D.porClub.values()].find((x) => x.liga === liga && String(x.team) === team && x.temporada === temp);
  const rec = D.jug.get(c.rec);
  if (!club || !rec) { console.log("sin club/registro", c.club, c.rec); mal++; continue; }
  const r = S.simular({ rec, club, rol: c.rol || undefined, nSim: 4000 });
  const pp = r.produccion_p100;
  const d = { minutos: r.minutos.mediana - c.minutos_mediana, pts: pp.pts_p100.media - c.pts_p100, ts: pp.ts_pct.media - c.ts_pct, usg: pp.usg_pct.media - c.usg_pct };
  const ok = Object.entries(d).every(([k, v]) => Math.abs(v) <= tol[k]);
  if (!ok) mal++;
  console.log(`${ok ? "OK " : "MAL"} ${String(c.nombre).padEnd(26)} ${c.club.padEnd(30)} rol=${String(c.rol).padEnd(9)} v=${r.version_motor}`,
    `min ${r.minutos.mediana.toFixed(1)}/${c.minutos_mediana.toFixed(1)} pts ${pp.pts_p100.media.toFixed(2)}/${c.pts_p100.toFixed(2)}`,
    `ts ${pp.ts_pct.media.toFixed(2)}/${c.ts_pct.toFixed(2)} usg ${pp.usg_pct.media.toFixed(2)}/${c.usg_pct.toFixed(2)}`,
    `pts80 [${fmt(pp.pts_p100.lo80)}, ${fmt(pp.pts_p100.hi80)}]/[${fmt(c.pts_lo80)}, ${fmt(c.pts_hi80)}]`,
    c.b9 ? `b9 Δmin ${r.b9 ? r.b9.d_min.toFixed(1) : "–"}/${c.b9.d_min.toFixed(1)} Δrol ${r.b9 ? r.b9.d_rol.toFixed(2) : "–"}/${c.b9.d_rol.toFixed(2)}` : "");
}
function fmt(x) { return x == null ? "–" : x.toFixed(1); }
console.log(mal ? `${mal} casos fuera de tolerancia` : "paridad v3.3: todos los casos dentro de tolerancia");
process.exit(mal ? 1 : 0);
