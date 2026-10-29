/* =====================================================================================================
   Cerno Analytics · Lectura de fichaje (informe A4) · v3.0 · 29-10-2026
   Sustituye la composición de páginas del informe v2 (ifPaginas) y su pintado (pintarInforme). Reutiliza los datos,
   el rasterizado a PDF, la descarga y el HTML imprimible de la página del Atlas.

   Estructura (bloques, no páginas): 0 portada · 1 Cerno Analytics y método · 2 el jugador · 3 conclusiones (con
   «Por qué lo proponemos», redactado en tono Cerno a partir de la nota del analista) · 4 ataque y tiro · 5 defensa y
   rebote · 6 contexto y conexiones · 7 glosario · contraportada.

   Arreglos de datos:
   - Los ficheros informe/<temporada>.json usan otra numeración de persona_id que el fichero de jugadores del Atlas
     (solo coincidía el 0,2 % de las claves → «Sin datos detallados…»). Resolución: clave exacta si existe; si no,
     emparejamiento dentro del mismo club-temporada por minutos jugados (asignación voraz por |Δminutos|).
   - Simulación del destino: motor v2.1 con el ROL QUE ASIGNA EL USUARIO (selector «Rol en el club de destino»).
   Nada de metodología interna en el documento: solo lectura, cifras con su margen y lenguaje de baloncesto.
   ===================================================================================================== */
"use strict";
(function () {
  if (typeof ifPaginas !== "function" || typeof pintarInforme !== "function") return;

  // ------------------------------------------------------------------------------------------- utilidades
  const $1 = (s) => document.querySelector(s);
  const N = (v, d = 1) => ifN(v, d), SG = (v, d = 1) => ifSg(v, d), E = esc;
  const ROLN = { RESIDUAL: "Residual", PROFUNDIDAD: "Profundidad", ROTACION: "Rotación", TITULAR: "Titular", GO_TO_GUY: "Go-to-guy" };
  const ROLD = { RESIDUAL: "minutos de cierre de partido, menos de 5 por noche", PROFUNDIDAD: "fondo de banquillo, entre 5 y 15 minutos", ROTACION: "rotación habitual desde el banquillo, entre 15 y 22 minutos", TITULAR: "titular, más de 22 minutos y sale de inicio", GO_TO_GUY: "referencia ofensiva: titular con muchos minutos y el balón en los momentos clave" };
  const ROLES = ["RESIDUAL", "PROFUNDIDAD", "ROTACION", "TITULAR", "GO_TO_GUY"];
  const LS = "cerno.informe.v3";
  const lsGet = () => { try { return JSON.parse(localStorage.getItem(LS) || "{}") || {}; } catch (e) { return {}; } };
  const lsSet = (o) => { try { localStorage.setItem(LS, JSON.stringify(o)); } catch (e) { /* sin almacenamiento */ } };
  const ape = (n) => ifApe(n), nom = (n) => ifNom(n);
  const pct = (v, d = 0) => v == null || !isFinite(v) ? "–" : N(v, d) + " %";
  const rng = (o, k = 90, d = 1) => o && o["lo" + k] != null ? `${N(o["lo" + k], d)}–${N(o["hi" + k], d)}` : "–";
  const euOf = (x) => (x && x.eu != null && EUS()[x.eu]) ? EUS()[x.eu] : null;
  const euLab = (x) => x ? (x.eu_etiqueta || (euOf(x) || {}).nombre || "–") : "–";
  const euSw = (x) => { const e = euOf(x); return e ? `<i class="r3sw" style="background:${e.color}"></i>` : ""; };
  const euDeVec = (p) => { if (!Array.isArray(p) || !p.length || !p.every((v) => isFinite(v))) return null; const k = p.indexOf(Math.max(...p)); return { eu: k, eu_p: p[k], eu_etiqueta: (EUS()[k] || {}).nombre }; };
  const simEu = (id) => { const k = EUS().findIndex((e) => e.id === id); return k >= 0 ? { eu: k, eu_etiqueta: EUS()[k].nombre } : null; };
  const rolDeRec = (rec) => (rec && ROLES.includes(rec.rol)) ? rec.rol : null;
  function rolEstimado(j, b) { // por minutos y titularidades (mismos umbrales que el simulador)
    const gm = (j.liga === "nba" || j.liga === "gleague") ? 48 : 40;
    const mp = b && b.min_pg != null ? b.min_pg / gm : (() => { const c = BY.get(j.clave); return c && c.min_total ? 5 * j.min / c.min_total : null; })();
    if (mp == null) return null; const gs = b && b.gp ? (b.gs || 0) / b.gp : 0;
    return mp < 0.125 ? "RESIDUAL" : mp < 0.375 ? "PROFUNDIDAD" : mp < 0.55 ? "ROTACION" : (mp >= 0.625 || gs >= 0.5) ? "TITULAR" : "ROTACION";
  }
  const SG0 = (v, d = 1) => v == null || !isFinite(v) ? "–" : Math.abs(v) < 0.5 * Math.pow(10, -d) ? "±" + N(0, d) : SG(v, d);
  let DN = null; try { DN = new Intl.DisplayNames(["es"], { type: "region" }); } catch (e) { DN = null; }
  const pais = (c) => { const s = String(c || "").trim(); if (!s) return null; return s.split("/").filter(Boolean).map((x) => { try { return DN && /^[A-Z]{2}$/.test(x) ? DN.of(x) : x; } catch (e) { return x; } }).join(" / "); };
  const rolChip = (r, est) => r ? `<span class="r3rol r-${r.toLowerCase()}">${est ? "≈ " : ""}${ROLN[r]}</span>` : "–";

  // ------------------------------------------------------------------------------------------- 1. resolver de claves
  const R3IDX = new Map();
  function indice(D, t) {
    if (R3IDX.has(t)) return R3IDX.get(t);
    const porClave = new Map();
    Object.entries(D.j).forEach(([k, e]) => { const cl = k.slice(k.indexOf("|") + 1); if (!porClave.has(cl)) porClave.set(cl, []); porClave.get(cl).push({ k, e, m: e && e.b ? e.b.min : null }); });
    const out = new Map();
    porClave.forEach((cand, cl) => {
      const js = (ROSTER.get(cl) || []).filter((x) => x.temporada === t), libreJ = new Set(js), libreC = new Set(cand);
      js.forEach((j) => { const c = cand.find((x) => x.k === `${j.persona_id}|${j.clave}`); if (c && libreC.has(c)) { out.set(jKey(j), c.e); libreJ.delete(j); libreC.delete(c); } });
      const pares = []; libreJ.forEach((j) => libreC.forEach((c) => pares.push([c.m == null ? 1e9 : Math.abs(c.m - j.min), j, c])));
      pares.sort((a, b) => a[0] - b[0]).forEach(([d, j, c]) => { if (!libreJ.has(j) || !libreC.has(c)) return; out.set(jKey(j), c.e); libreJ.delete(j); libreC.delete(c); });
    });
    R3IDX.set(t, out); return out;
  }
  async function entrada(j) { const D = await ifCargar(j.temporada); return { D, R0: indice(D, j.temporada).get(jKey(j)) || null }; }

  // ------------------------------------------------------------------------------------------- 2. controles nuevos
  function claveNota() { const { s } = ifEstado(); return `${s.jug || ""}→${s.sim ? `${s.dClub}:${s.dTemp}` : "-"}`; }
  function controles() {
    if ($1("#ifRolBox")) return;
    const dest = $1("#ifDest"); if (!dest) return;
    dest.insertAdjacentHTML("beforeend", `<div id="ifRolBox"><span class="label">Rol en el club de destino</span>
      <select id="ifRol" aria-label="Rol en el club de destino">${ROLES.map((r) => `<option value="${r}">${ROLN[r]}</option>`).join("")}</select>
      <p class="note">Lo eliges tú: el informe calcula minutos, rendimiento, adaptación, sinergias e Índice Fit con ese rol.</p></div>`);
    const hr = $1("#ifPdf") && $1("#ifPdf").previousElementSibling;
    const html = `<div id="ifPorqueBox"><span class="label">Por qué este jugador · nota del analista</span>
      <textarea id="ifPorque" rows="5" placeholder="En tus palabras: qué necesita el club, qué viste en él, por qué ahora. Se reescribe en tono Cerno para el bloque de conclusiones."></textarea>
      <div class="ifpq-acc"><button class="btn ghost sm" id="ifRedactar" type="button">Redactar en tono Cerno</button><button class="btn ghost sm" id="ifPorqueLimpiar" type="button">Borrar</button></div>
      <p class="note" id="ifPorqueMsg" aria-live="polite"></p>
      <label class="label" for="ifPorqueFinal">Texto que irá en el informe (puedes retocarlo)</label>
      <textarea id="ifPorqueFinal" rows="6" placeholder="Aparecerá aquí tras «Redactar en tono Cerno». Si lo dejas vacío, el informe usa tu nota tal cual."></textarea></div>`;
    if (hr && hr.tagName === "HR") hr.insertAdjacentHTML("beforebegin", "<hr>" + html); else $1("#ifPdf").insertAdjacentHTML("beforebegin", html);
    const nota = () => lsGet()[claveNota()] || {};
    const cargarNota = () => { const n = nota(); $1("#ifPorque").value = n.raw || ""; $1("#ifPorqueFinal").value = n.fin || ""; $1("#ifPorqueMsg").textContent = n.fin ? "Texto en tono Cerno guardado para este jugador y destino." : ""; };
    const guardarNota = () => { const o = lsGet(); o[claveNota()] = { raw: $1("#ifPorque").value, fin: $1("#ifPorqueFinal").value }; lsSet(o); };
    let tmr = null; const repintar = () => { clearTimeout(tmr); tmr = setTimeout(() => pintarInforme(), 600); };
    $1("#ifPorque").addEventListener("input", () => { guardarNota(); repintar(); });
    $1("#ifPorqueFinal").addEventListener("input", () => { guardarNota(); repintar(); });
    $1("#ifPorqueLimpiar").addEventListener("click", () => { $1("#ifPorque").value = ""; $1("#ifPorqueFinal").value = ""; guardarNota(); $1("#ifPorqueMsg").textContent = ""; pintarInforme(); });
    $1("#ifRedactar").addEventListener("click", redactar);
    $1("#ifRol").addEventListener("change", (e) => { st.inf.rol = e.target.value; st.inf.rolDe = claveNota(); guardar(); pintarInforme(); });
    controles.cargarNota = cargarNota;
    // «Abrir en pestaña nueva»: genera el PDF si aún no existe y lo abre (si no se puede, cae al HTML imprimible)
    const ab = $1("#ifAbrir"); if (ab) ab.onclick = async () => { const msg = $1("#ifMsg"); ab.disabled = true;
      try { if (!IFPDF) { msg.textContent = "Preparando el PDF…"; const blob = await ifGenerarPdf(msg); IFPDF = await blob.arrayBuffer(); window.__ifUltimoPdf = blob; }
        const r = await ifShell("abrir", ifNombre("pdf"), IFPDF.slice(0), "application/pdf", 20000);
        msg.textContent = r.ok ? "Abierto en una pestaña nueva: guárdalo o imprímelo desde el visor de PDF." : `No se pudo abrir la pestaña (${ifErr(r.error)}). Usa «Descargar PDF» o «HTML imprimible».`;
      } catch (e) { msg.textContent = `No se pudo preparar el PDF (${e && e.message ? e.message : e}).`; } finally { ab.disabled = false; } };
    ["#ifTemp", "#ifLiga", "#ifClub", "#ifJug", "#ifSim", "#ifDTemp", "#ifDLiga", "#ifDClub"].forEach((s) => { const el = $1(s); if (el) el.addEventListener("change", () => setTimeout(cargarNota, 0)); });
    const sb = $1("#ifBusS"); if (sb) sb.addEventListener("click", () => setTimeout(cargarNota, 0));
    cargarNota();
    const viejo = [...document.querySelectorAll("#p-informe .ifg .ctl > p.note")].find((p) => /La simulación es opcional/.test(p.textContent));
    if (viejo) viejo.textContent = "La simulación es opcional: sin ella, la lectura describe al jugador en su contexto actual. Con ella, mide su encaje en el club elegido con el rol que le asignes.";
  }
  // nota del analista → texto en tono Cerno (Claude, vía la página principal que tiene el permiso «sample»)
  let SREQ = 0; const SPEND = new Map();
  addEventListener("message", (e) => { const r = e.data && e.data.cernoSampleRes; if (!r || !SPEND.has(r.id)) return; SPEND.get(r.id)(r); SPEND.delete(r.id); });
  function pedirClaude(prompt) {
    if (window.parent === window) return (async () => { try { const s = window.claude && window.claude.use ? await window.claude.use("sample") : null; if (!s) return { error: "unavailable" }; const r = await s(prompt, { modelTier: "default" }); return { text: r.text }; } catch (e) { return { error: (e && e.code) || String(e) }; } })();
    return new Promise((ok) => { const id = ++SREQ; SPEND.set(id, ok); setTimeout(() => { if (SPEND.has(id)) { SPEND.delete(id); ok({ error: "sin_respuesta" }); } }, 240000);
      try { window.parent.postMessage({ cernoSample: { id, prompt } }, "*"); } catch (er) { SPEND.delete(id); ok({ error: String(er.message || er) }); } });
  }
  const SERR = { unavailable: "este visor no permite usar Claude desde la página", not_granted: "no se ha dado permiso para usar Claude", rate_limited: "demasiadas peticiones; inténtalo en un momento", sin_respuesta: "la página principal no respondió", refused: "Claude no pudo reescribir este texto; ajusta la nota" };
  async function redactar() {
    const raw = $1("#ifPorque").value.trim(), msg = $1("#ifPorqueMsg"), btn = $1("#ifRedactar");
    if (!raw) { msg.textContent = "Escribe primero tu nota."; return; }
    const c = ULT && ULT.ctx ? ULT.ctx : "";
    const prompt = `Eres redactor de Cerno Analytics, socio independiente de inteligencia de talento para direcciones deportivas de baloncesto. Reescribe la nota del analista para el apartado «Por qué lo proponemos» de una lectura de fichaje que leerá un director deportivo.

Voz de marca: exacta, franca, tranquila; como un analista senior que ha visto mucho baloncesto. Empieza por la conclusión. Lenguaje de baloncesto, sin jerga de modelos. Sin superlativos (nada de «el mejor», «élite», «revolucionario», «mágico», «garantizado», «desbloquear»). Respeto por el jugador. Si la nota expresa dudas, mantenlas con franqueza.

Reglas estrictas:
- Español de España. Tercera persona («proponemos», «en Cerno vemos»…).
- No inventes datos, cifras, lesiones, rasgos ni hechos que no estén en la nota o en el contexto. Puedes usar solo las cifras del contexto, tal cual.
- Entre 70 y 130 palabras, en 2 párrafos breves. Sin títulos, sin viñetas, sin comillas, sin firma.
- Devuelve solo el texto final.

Contexto del jugador (datos del informe):
${c}

Nota del analista:
${raw}`;
    btn.disabled = true; msg.textContent = "Redactando en tono Cerno… (la primera vez Claude pide permiso)";
    const r = await pedirClaude(prompt); btn.disabled = false;
    if (r && r.text) { $1("#ifPorqueFinal").value = r.text.trim(); const o = lsGet(); o[claveNota()] = { raw, fin: r.text.trim() }; lsSet(o); msg.textContent = "Listo. Revisa el texto: es el que entra en el informe."; pintarInforme(); }
    else msg.textContent = `No se pudo redactar (${SERR[r && r.error] || (r && r.error) || "error"}). El informe usará tu nota tal cual.`;
  }

  // ------------------------------------------------------------------------------------------- 3. piezas gráficas
  // punto + rango sobre una escala 0–100 (percentil) o una escala propia
  function barraPR(v, lo, hi, o = {}) {
    const W = o.w || 150, H = 14, min = o.min ?? 0, max = o.max ?? 100, X = (x) => 2 + (W - 4) * Math.max(0, Math.min(1, (x - min) / (max - min)));
    const ref = o.ref != null ? `<line x1="${X(o.ref)}" x2="${X(o.ref)}" y1="1" y2="${H - 1}" class="rf"/>` : "";
    const band = lo != null && hi != null ? `<rect x="${Math.min(X(lo), X(hi))}" y="4" width="${Math.max(2, Math.abs(X(hi) - X(lo)))}" height="${H - 8}" class="bd"/>` : "";
    return v == null || !isFinite(v) ? `<span class="r3na">sin dato</span>` : `<svg class="r3pr" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" aria-hidden="true"><line x1="2" x2="${W - 2}" y1="${H / 2}" y2="${H / 2}" class="tr"/>${ref}${band}<circle cx="${X(v)}" cy="${H / 2}" r="3.6" class="pt${o.cls ? " " + o.cls : ""}"/></svg>`;
  }
  // fila de métrica: nombre + qué mide, valor (vara Euroliga), percentil por posición con su franja
  function fila(k, R, pos) {
    const s = IFM[k], m = R.m[k]; if (!s || !m) return "";
    const op = ifOp(k, m[2]); let lo = m[3] != null ? ifOp(k, m[3]) : null, hi = m[4] != null ? ifOp(k, m[4]) : null; if (lo != null && hi != null && lo > hi) [lo, hi] = [hi, lo];
    const val = s.raw ? m[1] : m[0], neu = (s.dir ?? 1) === 0;
    return `<tr><td><b>${E(s.n)}</b><small>${E(s.d || "")}</small></td><td class="num">${ifV(k, val)}${!s.raw && m[1] != null && R.liga !== "euroleague" ? `<small>en su liga ${ifV(k, m[1])}</small>` : s.raw ? `<small>sin traducir</small>` : ""}</td>
      <td>${barraPR(op, lo, hi, { ref: 50, cls: neu ? "neu" : op >= 65 ? "up" : op <= 35 ? "dn" : "" })}</td><td class="num"><b class="${neu ? "" : ifTono(op)}">${op == null ? "–" : Math.round(op)}</b>${lo != null && hi != null ? `<small>${Math.round(lo)}–${Math.round(hi)}</small>` : ""}</td></tr>`;
  }
  function tablaM(keys, R, pos, titulo) {
    const filas = keys.filter((k) => R.m[k]).map((k) => fila(k, R, pos)).join("");
    return filas ? `<table class="r3t"><thead><tr><th>${E(titulo)}</th><th class="num">Valor</th><th>Frente a los ${E(IF_POSN[pos] || "jugadores")} de la Euroliga</th><th class="num">Percentil</th></tr></thead><tbody>${filas}</tbody></table>` : "";
  }
  function curvaAdapt(a) {
    const c = (a && a.curva) || []; if (c.length < 2) return "";
    const W = 300, H = 92, ys = c.flatMap((x) => [x[2], x[3]]).map((v) => 100 * v), lo = Math.min(96, ...ys) - 1, hi = Math.max(104, ...ys) + 1, n = c.length - 1;
    const X = (g) => 30 + (W - 38) * g / n, Y = (v) => 8 + (H - 26) * (1 - (100 * v - lo) / (hi - lo));
    const banda = c.map((x) => `${X(x[0])},${Y(x[3])}`).join(" ") + " " + c.slice().reverse().map((x) => `${X(x[0])},${Y(x[2])}`).join(" ");
    return `<svg class="r3cv" viewBox="0 0 ${W} ${H}" role="img" aria-label="Curva de adaptación"><line x1="30" x2="${W - 8}" y1="${Y(1)}" y2="${Y(1)}" class="rf"/><text x="24" y="${Y(1) + 3}" class="ax" text-anchor="end">100</text>
      <polygon points="${banda}" class="bd"/><path d="M ${c.map((x) => `${X(x[0])} ${Y(x[1])}`).join(" L ")}" class="ln"/>
      <text x="30" y="${H - 6}" class="ax">partido 1</text><text x="${W - 8}" y="${H - 6}" class="ax" text-anchor="end">partido ${c.length}</text></svg>`;
  }

  // ------------------------------------------------------------------------------------------- 4. textos de lectura
  const ART = { impacto: "el impacto en pista", anotacion: "la anotación", creacion: "la creación de juego", rebote: "el rebote", defensa: "la defensa" };
  function confianza(r, R) {
    if (!r) { const n = R && R.b ? R.b.min : null; return n == null ? "baja" : n >= 1200 ? "moderada" : n >= 500 ? "moderada" : "baja"; }
    const av = (r.avisos || []).map((x) => x.tipo), grave = av.filter((t) => ["incertidumbre_alta", "liga_lejana", "muestra_pequena"].includes(t)).length;
    return av.length === 0 ? "alta" : grave >= 2 || av.length >= 3 ? "baja" : "moderada";
  }
  const AVISO_TXT = { muestra_pequena: "Su muestra en origen es corta: pocas noches para fiarse del todo de sus cifras.", liga_lejana: "El salto de nivel entre ligas es grande: la traducción tiene más margen de lo habitual.", incertidumbre_alta: "Su nivel traducido tiene un margen amplio.", cambio_rol: "El rol que le das es muy distinto del que tiene ahora: es el supuesto que más mueve la lectura.", volatilidad_alta: "Es irregular partido a partido: noches muy buenas y otras discretas.", adaptacion_generica: "Hay poca historia de jugadores con este mismo cambio de liga y país." };
  function rasgos(R) { return ifRasgos(R); }
  const etiqueta = (p) => p == null ? "sin referencia en la Euroliga" : p >= 85 ? "en el 15 % alto de su puesto en la Euroliga" : p >= 60 ? "con nivel de titular en la Euroliga" : p >= 35 ? "con nivel de rotación en la Euroliga" : p >= 15 ? "con nivel de fondo de armario en la Euroliga" : "por debajo del nivel habitual de la Euroliga";

  // ------------------------------------------------------------------------------------------- 5. páginas
  const IDX_SEC = [];
  function hoja(cuerpo, o) {
    if (o.portada) return `<article class="ifsheet r3 cover${o.back ? " back" : ""}"><div class="ifbody">${cuerpo}</div></article>`;
    return `<article class="ifsheet r3"><header class="r3head"><span class="r3label">CERNO ANALYTICS — LECTURA DE FICHAJE · CONFIDENCIAL</span><span class="r3label">${E(o.extra || "")}</span><span class="r3hsec r3label">${String(o.num).padStart(2, "0")} · ${E(o.sec.toUpperCase())}</span></header>
      <div class="ifbody r3body">${cuerpo}</div><footer class="r3foot">${ifEscala(o.n, o.N)}<span>${E(o.fecha)}</span><span>${String(o.n).padStart(2, "0")} / ${String(o.N).padStart(2, "0")}</span></footer></article>`;
  }
  const ceja = (num, nombre, h2, lead) => `<div class="r3sec"><div><span class="r3ceja">Sección ${String(num).padStart(2, "0")} · ${E(nombre)}</span><h2>${h2}</h2>${lead ? `<p class="r3lead">${lead}</p>` : ""}</div><b class="r3num">${String(num).padStart(2, "0")}</b></div>`;

  function evolucion(tray, j) {
    const por = new Map(); tray.forEach((x) => { const o = por.get(x.temporada); if (!o || x.min > o.min) por.set(x.temporada, x); });
    const T = [...por.keys()].sort(); if (T.length < 2) return `<p class="r3n">Solo hay una temporada suya en los datos.</p>`;
    const W = 330, H = 150, l = 30, r = 12, t = 16, bb = 30, xs = (i) => l + (W - l - r) * i / (T.length - 1), ys = (v) => t + (H - t - bb) * (1 - (v + 100) / 200);
    const Nv = T.map((t_) => sNivJ(por.get(t_))), Rr = T.map((t_) => { const x = por.get(t_); return rapmOk(x) ? ESC.S("rapm", x.rapm_el, x.temporada) : null; });
    const lin = (v, cl) => { const p = v.map((y, i) => y == null ? null : [xs(i), ys(y)]).filter(Boolean); return p.length > 1 ? `<path d="M ${p.map((q) => q.join(" ")).join(" L ")}" class="${cl}"/>` : ""; };
    const grid = [-50, 0, 50].map((v) => `<line x1="${l}" x2="${W - r}" y1="${ys(v)}" y2="${ys(v)}" class="${v === 0 ? "z" : "g"}"/><text x="${l - 5}" y="${ys(v) + 3}" class="ax" text-anchor="end">${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v)}</text>`).join("");
    const pts = Nv.map((v, i) => v == null ? "" : `<circle cx="${xs(i)}" cy="${ys(v)}" r="${T[i] === j.temporada ? 3.6 : 2.4}" class="pn"/><text x="${xs(i)}" y="${ys(v) - 7}" class="pv" text-anchor="middle">${ESC.txt(v)}</text>`).join("");
    const lab = T.map((t_, i) => `<text x="${xs(i)}" y="${H - 14}" class="ax" text-anchor="middle">${t_.slice(2)}</text><text x="${xs(i)}" y="${H - 5}" class="ax" text-anchor="middle">${E(LC[por.get(t_).liga] || "")}</text>`).join("");
    return `<svg class="r3ev" viewBox="0 0 ${W} ${H}" role="img" aria-label="Evolución de su nivel">${grid}${lin(Rr, "lr")}${lin(Nv, "ln")}${pts}${lab}</svg><p class="r3n">Línea continua: nivel Cerno; discontinua: impacto en pista. Escala ±100, una temporada por punto (su equipo con más minutos).</p>`;
  }
  function ligasVara(j, d) {
    const t = META.temporadas_provisionales.includes(j.temporada) ? ultCompleta() : j.temporada;
    const L = ESC.ligasNivel(t).filter((o) => o.S != null).sort((a, b) => b.S - a.S); if (!L.length) return "";
    const m = Math.max(60, ...L.map((o) => Math.abs(o.S))), W = 160;
    return `<div class="r3blk"><h3>Normalización entre ligas: cuánto vale cada competición</h3><div class="r3lig">${L.map((o) => { const w = Math.abs(o.S) / m * (W / 2), x = o.S >= 0 ? W / 2 : W / 2 - w, sel = o.l === j.liga || (d && o.l === d.liga);
      return `<div class="${sel ? "sel" : ""}"><span>${E(ESC.ligaNom(o.l))}</span><svg viewBox="0 0 ${W} 10" width="${W}" height="10"><line x1="${W / 2}" x2="${W / 2}" y1="0" y2="10" class="z"/><rect x="${x}" y="2" width="${Math.max(1, w)}" height="6" class="${sel ? "on" : ""}"/></svg><b>${ESC.txt(o.S)}</b></div>`; }).join("")}</div>
      <p class="r3n">Nivel medio de los jugadores de cada liga en ${E(t)}, escala ±100 (0 = Euroliga). Es la regla con la que se traducen sus cifras: un 15 en una liga más exigente vale más que un 15 en una menos exigente. En negrita, su liga${d && d.liga !== j.liga ? " y la del club de destino" : ""}.</p></div>`;
  }
  function lecturaAtaque(R) {
    const p = (k) => R.m[k] && R.m[k][2] != null ? ifOp(k, R.m[k][2]) : null, u = p("usg_pct"), ts = p("ts_pct"), a = p("ast_pct"), tv = p("tov_pct"), t3 = p("fg3_pct"), r3 = p("fg3a_rate"), fr = p("fta_rate"), out = [];
    if (u != null && ts != null) out.push(u >= 65 ? (ts >= 55 ? "Asume mucho volumen de ataque y lo hace con eficiencia: el perfil de jugador al que se le puede dar el balón en los finales." : ts <= 35 ? "Asume mucho volumen, pero con poca eficiencia: necesita un sistema que le dé tiros mejores o menos responsabilidad." : "Asume mucho volumen con una eficiencia en la media de su puesto.") : u <= 35 ? (ts >= 55 ? "Toca poco el balón pero aprovecha lo que le llega: buen complemento junto a creadores." : "Tiene un papel secundario en el ataque.") : (ts >= 65 ? "Con un uso medio del balón, anota con eficiencia alta." : "Uso del balón y eficiencia en la zona media de su puesto."));
    if (a != null && a >= 70) out.push(tv != null && tv <= 35 ? "Genera juego para los demás, aunque con más pérdidas de las deseables." : "Genera juego para los demás y cuida el balón.");
    if (r3 != null && t3 != null) out.push(r3 >= 60 ? (t3 >= 55 ? "El triple es un arma real: tira mucho y con buen acierto." : "Tira muchos triples sin un acierto que lo respalde.") : t3 >= 70 ? "Acierta de tres por encima de su puesto aunque tire poco: hay margen para darle más tiros." : "");
    if (fr != null && fr >= 75) out.push("Pisa la línea de tiros libres con frecuencia: castiga los cierres tardíos y carga de faltas al rival.");
    return out.filter(Boolean).join(" ");
  }
  function paginas(c) {
    const { j, R, pos, sim, s2, nec, fecha, tray, medias, nota } = c, b = R.b || {}, club = BY.get(j.clave), d = sim && !sim.mismo ? sim.d : null;
    const P = R.ref[pos] || R.ref["*"], pL = R.m.L ? R.m.L[2] : null, Snv = sNivJ(j), sr = rapmOk(j) ? ESC.S("rapm", j.rapm_el, j.temporada) : null;
    const rolA = c.rol, rolO = rolDeRec(simRec(j)) || rolEstimado(j, b), rolOest = !rolDeRec(simRec(j));
    const bloques = IFB.map((bk) => ({ bk, sc: ifPuntBloque(bk, R) })).filter((o) => o.sc != null);
    const mejorB = bloques.slice().sort((a, x) => x.sc - a.sc)[0], peorB = bloques.slice().sort((a, x) => a.sc - x.sc)[0];
    const conf = confianza(s2, R), fitS = s2 && s2.fit && s2.fit.total != null ? ESC.dS("z", s2.fit.total) : null;
    const nomJ = nom(j.nombre), apeJ = ape(j.nombre), clubN = club ? club.nombre_club : j.nombre_club;
    const extra = `${apeJ.toUpperCase()}${d ? ` → ${d.nombre_club.toUpperCase()}` : ""}`.slice(0, 50);
    const pags = [];
    const nac = c.nac || pais((simRec(j) || {}).nac) || "–", posA = String(b.posicion || "").replace(/_/g, " ").toLowerCase(), posB = IF_POS1[j.pos3] || "";
    const ficha = [["Nacionalidad", nac], ["Edad", j.edad != null ? `${Math.round(j.edad)} años` : "–"], ["Altura", b.altura_cm ? `${N(b.altura_cm / 100, 2)} m` : "–"], ["Posición", `${posB ? posB.charAt(0).toUpperCase() + posB.slice(1) : "s/d"}${posA && posA !== posB ? ` · ${posA}` : ""}`]].filter(([, v]) => v !== "–");

    // 0 · portada
    const ref = `CN-${new Date().toISOString().slice(2, 10).replace(/-/g, "")}-${(nomJ.match(/\p{L}+/gu) || ["X"]).map((w) => w[0]).join("").slice(0, 3).toUpperCase()}`;
    pags.push({ portada: true, html: `<div class="cvtop"><img src="${INF_LOGO.hn}" alt="Cerno" class="cvlogo"><span class="cvk">Lectura de fichaje · ${new Date().getFullYear()} · Confidencial</span></div>
      <div class="cvmid"><h1><span class="hl">${E(nomJ)}</span></h1>
        <p class="cvdat">${E(clubN)} · ${E(LIGAS[j.liga] || j.liga)} · temporada ${E(j.temporada)}${d ? `<br>Encaje en ${E(d.nombre_club)} · ${E(LIGAS[d.liga] || d.liga)} ${E(d.temporada)} · rol ${E(ROLN[rolA] || "–")}` : ""}</p>
        <dl class="cvfacts">${ficha.map(([a, v]) => `<div><dt>${a}</dt><dd>${E(v)}</dd></div>`).join("")}</dl></div>
      <ol class="cvidx">@@INDICE@@</ol>
      <div class="cvbot"><div><span>Preparado para</span><b>Dirección deportiva${d ? ` · ${E(d.nombre_club)}` : ""}</b></div><div><span>Fecha</span><b>${E(fecha)}</b></div><div><span>Referencia</span><b>${ref}</b></div></div>
      <span class="cvscale" aria-hidden="true">${Array.from({ length: 17 }, (_, k) => `<i class="${k === 8 ? "on" : k % 5 === 0 ? "M" : ""}"></i>`).join("")}</span>` });

    // 1 · Cerno Analytics
    pags.push({ sec: "Cerno Analytics", html: `${ceja(1, "Cerno Analytics", "Una lectura en contexto, con su margen de error", "Sabrás qué jugador encaja, por qué y con cuánta seguridad.")}
      <div class="r3cols"><div><p class="r3p">Cerno es un socio independiente de inteligencia de talento para el baloncesto profesional. Combinamos modelos predictivos con conocimiento profundo del juego para mostrar a los clubes cómo encaja un jugador en su sistema, en qué es probable que se convierta y con cuánta seguridad lo afirmamos.</p>
        <p class="r3p">Trabajamos solo para el lado del club y con confidencialidad por defecto: esta lectura es suya. Un jugador no es bueno en abstracto; es bueno para un sistema, un rol y unos compañeros. Por eso no ordenamos por fama ni por estadística total, sino por encaje.</p></div>
        <div class="r3q"><span class="r3lab">Las preguntas de cada lectura</span>
          <dl><div><dt>Encaje</dt><dd>¿Cómo funciona en este sistema, con este rol y estos compañeros?</dd></div><div><dt>Trayectoria</dt><dd>¿De dónde viene y qué ha sostenido temporada a temporada?</dd></div><div><dt>Riesgo</dt><dd>¿Qué puede fallar y qué nos haría cambiar de opinión?</dd></div><div><dt>Valor</dt><dd>Relación entre lo que aporta y lo que cuesta. <em>Fuera de esta lectura: requiere los datos económicos del club.</em></dd></div></dl></div></div>
      <div class="r3steps"><span class="r3lab">Cómo hacemos la lectura</span><ol>
        <li><b>Vemos todos sus partidos</b><span>Actas oficiales y jugada a jugada de trece competiciones. Como el ojeador que no se queda con un solo partido: buscamos lo que se repite.</span></li>
        <li><b>Lo medimos en la misma pista</b><span>Una canasta en una liga no vale lo mismo que en otra. Traducimos sus cifras a la exigencia de la Euroliga para comparar a todos con la misma vara.</span></li>
        <li><b>Lo ponemos en tu vestuario</b><span>Un tirador rinde distinto con un base que penetra al lado. Simulamos su rol, sus minutos, sus compañeros y el estilo del club para leer cómo jugaría aquí.</span></li>
        <li><b>Decimos cuánto sabemos</b><span>Cada cifra va con su margen. Si un dato descansa en pocos minutos o en un salto de liga grande, lo decimos. Una recomendación sin su incertidumbre es solo una opinión con decimales.</span></li></ol></div>
      <div class="r3read"><span class="r3lab">Cómo leer las cifras de esta lectura</span><div>
        <div><b>Punto y rango</b>${barraPR(62, 48, 74, { ref: 50, w: 120 })}<span>El punto es lo más probable; la franja, entre dónde se moverá. Cuanto más ancha, menos seguros estamos.</span></div>
        <div><b>Percentil por puesto</b><p class="r3big">80</p><span>Mejor que el 80 % de los jugadores de su puesto en la Euroliga. 50 es el mediano.</span></div>
        <div><b>Escala ±100</b><p class="r3big">0</p><span>La media de la Euroliga. Positivo, por encima; negativo, por debajo. Se usa para nivel, impacto y química.</span></div>
        <div><b>Colores</b><p class="r3cols3"><i style="background:#2A6FA8"></i>mejor<i style="background:#C4552E"></i>peor<i style="background:#7A5BC8"></i>rasgo de estilo</p><span>El violeta no es bueno ni malo: describe cómo juega (cuánto tira de tres, cuánto usa el balón).</span></div></div></div>
      <div class="r3vals"><span class="r3lab">Lo que guía cada lectura</span><div>
        <div><b>Contexto antes que promedios</b><span>Un jugador no es bueno en abstracto. Es bueno para un sistema, un rol y un presupuesto.</span></div>
        <div><b>Franqueza calibrada</b><span>Decimos lo que sabemos y cuánto lo sabemos. Cada recomendación incluye su rango y lo que nos haría cambiar de opinión.</span></div>
        <div><b>Discreción por diseño</b><span>Las listas de un club son suyas. Confidencialidad por defecto en procesos, datos y comunicación.</span></div></div></div>
      <div class="r3call callout"><span class="r3tag">Basketball judgment, model rigor</span><p>Los modelos informan; la dirección deportiva decide. Esta lectura complementa el scouting en vídeo y en pista, no lo sustituye.</p></div>` });

    // 2 · el jugador
    const filasT = tray.slice(-6).map((x) => { const r = rolDeRec(simRec(x)), m = medias.get(jKey(x)), est = !r, rr = r || rolEstimado(x, m);
      return `<tr class="${x === j ? "yo" : ""}"><td>${E(x.temporada)}</td><td>${E(x.nombre_club)}<small>${E(LC[x.liga] || x.liga)}</small></td><td>${rolChip(rr, est)}</td><td>${euSw(x)}${E(euLab(x))}</td><td class="num">${m && m.min_pg != null ? N(m.min_pg, 1) : (() => { const c = BY.get(x.clave); return c && c.min_total ? N(x.min / (c.min_total / durPartido(x.liga)), 1) : "–"; })()}</td><td class="num">${m ? N(m.pts_pg, 1) : "–"}</td><td class="num">${m ? N(m.reb_pg, 1) : "–"}</td><td class="num">${m ? N(m.ast_pg, 1) : "–"}</td><td class="num">${m ? N(m.ts_pct, 1) : "–"}</td><td class="num ${ESC.cls(sNivJ(x))}">${ESC.txt(sNivJ(x))}</td></tr>`; }).join("");
    const eu = euOf(j);
    pags.push({ sec: "El jugador", html: `${ceja(2, "El jugador", `${E(nomJ)}: ${E(IF_POS1[pos] || "jugador")} ${rolO ? `de ${E(ROLN[rolO].toLowerCase())}` : ""} en ${E(clubN)}`, `${E(apeJ)} juega en ${E(LIGAS[j.liga] || j.liga)}. Sus cifras de ${E(j.temporada)}, traducidas a la Euroliga, lo sitúan <b>${E(etiqueta(pL))}</b>.`)}
      <dl class="r3id">${ficha.map(([a, v]) => `<div><dt>${a}</dt><dd>${E(v)}</dd></div>`).join("")}<div><dt>Club actual</dt><dd>${E(clubN)}</dd></div><div><dt>Rol actual</dt><dd>${rolChip(rolO, rolOest)}</dd></div></dl>
      <div class="r3blk"><h3>Trayectoria y rol en las últimas temporadas</h3><table class="r3t tray"><thead><tr><th>Temp.</th><th>Equipo</th><th>Rol</th><th>Estilo</th><th class="num">Min/p</th><th class="num">Pts</th><th class="num">Reb</th><th class="num">Ast</th><th class="num">TS%</th><th class="num">Nivel</th></tr></thead><tbody>${filasT}</tbody></table>
        <p class="r3n">Medias por partido de cada temporada (liga regular). Nivel Cerno en escala ±100: 0 es el jugador medio de la Euroliga de esa temporada. «≈»: rol estimado por minutos y titularidades.</p></div>
      ${eu ? `<div class="r3est"><div class="r3estN"><span class="r3lab">Estilo de juego</span><b>${euSw(j)}${E(euLab(j))}</b><small>${E(eu.rol_jugador || "")} · pertenencia ${afin(j.eu_p)} de 100</small></div><p>${E(eu.jugador || eu.definicion || "")}</p></div>` : ""}
      <div class="r3kp"><div><span>Nivel Cerno</span><b class="${ESC.cls(Snv)}">${ESC.txt(Snv)}</b><small>${pL != null ? `mejor que el ${Math.round(pL)} % de los ${E(IF_POSN[pos])} de la Euroliga` : "escala ±100"}</small></div>
        <div><span>Impacto en pista</span><b class="${ESC.cls(sr)}">${sr != null ? ESC.txt(sr) : "–"}</b><small>${sr != null ? `${SG(j.rapm_el, 1)} pts por 100 posesiones con él en pista` : "sin jugada a jugada"}</small></div>
        <div><span>Punto fuerte</span><b class="r3w">${mejorB ? E(mejorB.bk.n) : "–"}</b><small>${mejorB ? `nota ${Math.round(mejorB.sc)} de 100 frente a su puesto` : ""}</small></div>
        <div><span>A mejorar</span><b class="r3w">${peorB && peorB !== mejorB ? E(peorB.bk.n) : "–"}</b><small>${peorB && peorB !== mejorB ? `nota ${Math.round(peorB.sc)} de 100` : ""}</small></div></div>
      <div class="r3cols c2"><div class="r3blk"><h3>Perfil por bloques frente a su puesto</h3><table class="r3t bloq"><tbody>${bloques.map(({ bk, sc }) => `<tr><td><b>${E(bk.n)}</b><small>${E(bk.q)}</small></td><td>${barraPR(sc, null, null, { ref: 50, w: 150, cls: sc >= 65 ? "up" : sc <= 35 ? "dn" : "" })}</td><td class="num"><b class="${ifTono(sc)}">${Math.round(sc)}</b></td></tr>`).join("")}</tbody></table><p class="r3n">Nota de 0 a 100: media de sus percentiles en cada bloque frente a los ${E(IF_POSN[pos])} de la Euroliga. 50 es el ${E(IF_POS1[pos])} mediano.</p></div>
        <div class="r3blk"><h3>Evolución de su nivel</h3>${evolucion(tray, j)}</div></div>` });

    // 3 · conclusiones
    const ras = rasgos(R), s2ok = s2 && !s2.error, a = s2ok ? s2.adaptacion : null, eqv = s2ok ? s2.equipo : null;
    const headline = d ? `${E(ROLN[rolA])} para ${E(d.nombre_club)}${fitS != null ? `: Fit ${ESC.txt(fitS)}` : ""}, confianza ${conf}` : `${E(apeJ)} hoy: ${E(etiqueta(pL))}`;
    const cubre = nec ? nec.filter((x) => x.v[0] === "up").slice(0, 4) : [], noCubre = nec ? nec.filter((x) => x.v[0] === "dn").slice(0, 3) : [];
    const q1 = eqv && eqv.quintetos && eqv.quintetos.find((q) => q.con_fichaje);
    const lectura = d ? `${E(apeJ)} llegaría a ${E(d.nombre_club)} como <b>${E(ROLN[rolA].toLowerCase())}</b> (${E(ROLD[rolA])}).${s2ok ? ` Con ese papel le corresponderían unos <b>${N(s2.minutos.media, 0)} minutos por noche</b> (rango 90 %: ${rng(s2.minutos, 90, 0)}).` : ""}${a ? ` Su adaptación esperada a la liga es de <b>${N(a.adapt_pct_temporada.media, 0)} sobre 100</b> en la temporada (${rng(a.adapt_pct_temporada, 90, 0)}): ${a.adapt_pct_temporada.media >= 99 ? "rendiría prácticamente lo que dicen sus cifras traducidas" : a.adapt_pct_temporada.media >= 95 ? "perdería un poco al principio, como casi todos al cambiar de liga" : "necesitaría tiempo para rendir a su nivel"}.` : ""}${cubre.length ? ` Cubre lo que más necesita el equipo en ${cubre.map((x) => x.n.toLowerCase()).join(", ")}.` : ""}`
      : `Esta lectura describe a ${E(apeJ)} en su contexto actual, sin club de destino: qué aporta, qué vigilar y cómo encaja hoy en ${E(clubN)}.`;
    const notaHtml = nota ? nota.split(/\n{2,}|\r?\n/).filter((t) => t.trim()).map((t) => `<p>${E(t.trim())}</p>`).join("") : "";
    const gen = []; if (b.min != null && b.min < 500) gen.push(`Su muestra de ${j.temporada} es corta (${N(b.min, 0)} minutos): sus porcentajes pueden moverse mucho.`); if (j.liga !== "euroleague") gen.push(`Sus cifras vienen de ${LIGAS[j.liga] || j.liga}: la traducción a la Euroliga tiene su margen, mayor cuanto más lejos esté la liga.`); if (tray.length <= 1) gen.push("Solo hay una temporada suya en los datos: no sabemos aún si su rendimiento se sostiene.");
    const cambiar = (s2ok ? (s2.avisos || []).map((x) => AVISO_TXT[x.tipo] || x.texto).concat(ras.bot.slice(0, 2).map((o) => `${IFM[o.k].mal.charAt(0).toUpperCase() + IFM[o.k].mal.slice(1)} (${IFM[o.k].n}, percentil ${Math.round(o.op)}).`)) : gen).slice(0, 4);
    const kpis = d && s2ok ? `<div class="r3kp big"><div class="idx"><span>Índice Fit</span><b>${fitS != null ? ESC.txt(fitS) : "–"}</b><small>confianza ${conf} · 0 = fichaje medio</small></div>
        <div><span>Adaptación (ADAPT%)</span><b>${N(a.adapt_pct_temporada.media, 0)}</b><small>rango 90 %: ${rng(a.adapt_pct_temporada, 90, 0)} · 100 = rinde lo traducido</small></div>
        <div><span>Minutos con ese rol</span><b>${N(s2.minutos.media, 0)}'</b><small>rango 90 %: ${rng(s2.minutos, 90, 0)}'</small></div>
        <div><span>Net del equipo con él</span><b class="${eqv.d_net > 0.5 ? "up" : eqv.d_net < -0.5 ? "dn" : ""}">${SG0(eqv.d_net, 2)}</b><small>pts/100 · rango 90 %: ${SG0(eqv.d_net_lo90, 1)} a ${SG0(eqv.d_net_hi90, 1)}</small></div>
        <div><span>Lugar en la plantilla</span><b>${sim.orden.findIndex((o) => o.el) + 1}.º</b><small>de ${sim.orden.length} por nivel</small></div></div>`
      : `<div class="r3kp big"><div class="idx"><span>Nivel Cerno</span><b class="${ESC.cls(Snv)}">${ESC.txt(Snv)}</b><small>escala ±100 · 0 = media de la Euroliga</small></div><div><span>Percentil en su puesto</span><b>${pL != null ? Math.round(pL) : "–"}</b><small>frente a los ${E(IF_POSN[pos])} de la Euroliga</small></div><div><span>Impacto en pista</span><b class="${ESC.cls(sr)}">${sr != null ? ESC.txt(sr) : "–"}</b><small>RAPM-EL, escala ±100</small></div><div><span>Rol actual</span><b class="r3w">${rolO ? ROLN[rolO] : "–"}</b><small>${rolOest ? "estimado por minutos" : "en su temporada"}</small></div></div>`;
    pags.push({ sec: "Conclusiones", html: `${ceja(3, "Conclusiones", headline, lectura)}
      ${kpis}
      <div class="r3cols">
        <div class="r3blk"><h3>Lo que aporta</h3><ul class="r3l up">${ras.top.slice(0, 4).map((o) => `<li><b>${E(IFM[o.k].bien.charAt(0).toUpperCase() + IFM[o.k].bien.slice(1))}</b><span>${E(IFM[o.k].n)} · mejor que el ${Math.round(o.op)} % de su puesto en la Euroliga</span></li>`).join("") || `<li><span>Ningún registro destaca con claridad sobre su puesto en la Euroliga.</span></li>`}</ul></div>
        <div class="r3blk">${a ? `<h3>Cómo se adaptaría a ${E(d.nombre_club)}</h3>${curvaAdapt(a)}<p class="r3n">Rendimiento esperado partido a partido sobre su nivel traducido (100). Primeros ${a.primeros_partidos} partidos: ${N(a.adapt_pct_primeros.media, 0)}.${a.partidos_50 ? ` La mitad del ajuste se cierra en unos ${N(a.partidos_50, 0)} partidos.` : ""}</p>` : `<h3>A vigilar</h3><ul class="r3l dn">${ras.bot.slice(0, 4).map((o) => `<li><b>${E(IFM[o.k].mal.charAt(0).toUpperCase() + IFM[o.k].mal.slice(1))}</b><span>${E(IFM[o.k].n)} · peor que el ${Math.round(100 - o.op)} % de su puesto en la Euroliga</span></li>`).join("") || `<li><span>Ningún registro queda claramente por debajo de su puesto en la Euroliga.</span></li>`}</ul>`}
          ${q1 ? `<p class="r3n"><b>Quinteto más probable con él:</b> ${q1.nombres.map((x) => E(nom(String(x)).split(" ").slice(-1)[0])).join(", ")} (${Math.round(100 * q1.prob)} % de las temporadas simuladas).</p>` : ""}</div></div>
      ${!d ? (() => { const e = ifEsperado(R, c.ritmo || 72, 25); return `<div class="r3cols c2"><div class="r3blk"><h3>Su temporada por partido</h3><div class="r3mini"><div><b>${N(b.min_pg, 1)}</b><span>minutos</span></div><div><b>${N(b.pts_pg, 1)}</b><span>puntos</span></div><div><b>${N(b.reb_pg, 1)}</b><span>rebotes</span></div><div><b>${N(b.ast_pg, 1)}</b><span>asistencias</span></div></div><p class="r3n">${E(LIGAS[j.liga] || j.liga)} ${E(j.temporada)}, liga regular${b.gp ? ` · ${b.gp} partidos` : ""}.</p></div>
        <div class="r3blk"><h3>Qué produce por cada 25 minutos en la vara Euroliga</h3><div class="r3mini"><div><b>${N(e.pts, 1)}</b><span>puntos</span></div><div><b>${N(e.reb, 1)}</b><span>rebotes</span></div><div><b>${N(e.ast, 1)}</b><span>asistencias</span></div><div><b>${N(e.ts, 0)}<small>%</small></b><span>TS%</span></div></div><p class="r3n">Sus cifras traducidas a la exigencia de la Euroliga, al ritmo medio de la competición.</p></div></div>`; })() : ""}
      ${notaHtml ? `<div class="r3why callout"><span class="r3tag">Por qué lo proponemos</span>${notaHtml}</div>` : ""}
      ${d && c.esc && c.esc.length ? `<div class="r3blk"><h3>Si cambias su rol</h3><table class="r3t esc"><thead><tr><th>Rol en ${E(d.nombre_club)}</th><th class="num">Índice Fit</th><th class="num">Minutos</th><th class="num">Puntos / partido</th><th class="num">Net del equipo</th></tr></thead><tbody>${c.esc.map((o) => `<tr class="${o.rol === rolA ? "yo" : ""}"><td>${rolChip(o.rol)}${o.rol === rolA ? " <small style=\"display:inline\">asignado</small>" : ""}</td><td class="num"><b>${ESC.txt(ESC.dS("z", o.r.fit.total))}</b></td><td class="num">${N(o.r.minutos.media, 0)}' <small style="display:inline">${rng(o.r.minutos, 90, 0)}</small></td><td class="num">${o.r.por_partido.pts ? `${N(o.r.por_partido.pts.media, 1)} <small style="display:inline">${rng(o.r.por_partido.pts, 90, 1)}</small>` : "–"}</td><td class="num">${SG0(o.r.equipo.d_net, 2)}</td></tr>`).join("")}</tbody></table><p class="r3n">Misma simulación con cada rol. Rangos al 90 %. Sirve para decidir qué papel le das: más rol no siempre suma igual al equipo.</p></div>` : ""}
      ${cambiar.length ? `<div class="r3blk"><h3>Qué nos haría cambiar de opinión</h3><ul class="r3l">${cambiar.map((t) => `<li><span>${E(t)}</span></li>`).join("")}</ul></div>` : ""}` });

    // 4 · ataque y tiro
    const cp = ifCampo(R, pos, b), K4 = ["pts_p100", "usg_pct", "ts_pct", "fg3_pct", "ft_pct", "fg3a_rate", "fta_rate", "ast_pct", "tov_pct", "orapm"];
    const prod = s2ok ? s2.produccion_p100 : null, pp = s2ok ? s2.por_partido : null;
    const simAt = prod ? `<table class="r3t sim"><thead><tr><th>En ${E(d.nombre_club)} · ${E(ROLN[rolA])}</th><th class="num">Media</th><th class="num">Rango 90 %</th></tr></thead><tbody>
        ${[["Puntos por partido", pp && pp.pts], ["Puntos / 100 posesiones", prod.pts_p100], ["TS%", prod.ts_pct], ["USG%", prod.usg_pct], ["AST%", prod.ast_pct], ["TOV%", prod.tov_pct]].filter(([, o]) => o && o.media != null).map(([n, o]) => `<tr><td>${n}</td><td class="num"><b>${N(o.media, 1)}</b></td><td class="num">${rng(o, 90)}</td></tr>`).join("")}</tbody></table>` : "";
    const fAt = ["anotacion", "creacion"].map((k) => bloques.find((o) => o.bk.k === k)).filter(Boolean);
    pags.push({ sec: "Ataque y tiro", html: `${ceja(4, "Ataque y tiro", `${fAt.length ? `Anotación ${Math.round(fAt[0].sc)} y creación ${fAt[1] ? Math.round(fAt[1].sc) : "–"} sobre 100` : "Su ataque frente a su puesto"}`, `${E(cp.txt || "")} Las cifras están traducidas a la Euroliga; el percentil lo compara con los ${E(IF_POSN[pos])} de la Euroliga, como mirar su tarjeta de tiro junto a la de los titulares de la competición.`)}
      ${tablaM(K4, R, pos, "Métrica de ataque")}
      <p class="r3p r3lec">${E(lecturaAtaque(R))}</p>
      <div class="r3cols c2"><div class="r3blk"><h3>Desde dónde tira</h3>${cp.svg}<p class="r3n">Color violeta: tira más desde esa zona que el ${E(IF_POS1[pos])} mediano de la Euroliga; gris: menos.</p></div>
        <div class="r3blk">${(() => { const e = ifEsperado(R, c.ritmo || 72, 25); return `<h3>Qué produce hoy por cada 25 minutos</h3><div class="r3mini"><div><b>${N(e.pts, 1)}</b><span>puntos</span></div><div><b>${N(e.reb, 1)}</b><span>rebotes</span></div><div><b>${N(e.ast, 1)}</b><span>asistencias</span></div><div><b>${N(e.ts, 0)}<small>%</small></b><span>TS%</span></div></div>`; })()}${simAt ? `<h3 style="margin-top:10px!important">Su ataque con el rol asignado</h3>${simAt}<p class="r3n">Con mejores compañeros, un jugador suele tirar menos y con más acierto; con peores, al revés. Los rangos recogen lo que puede variar una temporada.</p>` : `<h3>Lectura</h3><p class="r3p">${fAt[0] && fAt[0].sc >= 60 ? "Anota por encima de lo habitual en su puesto." : fAt[0] && fAt[0].sc <= 40 ? "Su anotación queda por debajo de lo habitual en su puesto." : "Su anotación está en la zona media de su puesto."} ${fAt[1] && fAt[1].sc >= 60 ? "Además genera juego para los demás." : ""}</p>`}</div></div>` });

    // 5 · defensa y rebote
    const K5 = ["drtg", "drapm", "stl_pct", "blk_pct", "stop_pct", "pf_p100", "dreb_pct", "oreb_pct"];
    const fDf = ["defensa", "rebote"].map((k) => bloques.find((o) => o.bk.k === k)).filter(Boolean);
    const simDf = pp ? `<table class="r3t sim"><thead><tr><th>En ${E(d.nombre_club)} · por partido</th><th class="num">Media</th><th class="num">Rango 90 %</th></tr></thead><tbody>
        ${[["Rebotes", pp.reb], ["Robos", pp.stl], ["Tapones", pp.blk], ["Posesiones en pista", pp.posesiones]].filter(([, o]) => o && o.media != null).map(([n, o]) => `<tr><td>${n}</td><td class="num"><b>${N(o.media, 1)}</b></td><td class="num">${rng(o, 90)}</td></tr>`).join("")}</tbody></table>` : "";
    pags.push({ sec: "Defensa y rebote", html: `${ceja(5, "Defensa y rebote", fDf.length ? `Defensa ${Math.round(fDf[0].sc)} y rebote ${fDf[1] ? Math.round(fDf[1].sc) : "–"} sobre 100` : "Su defensa frente a su puesto", "La defensa es lo que peor recoge un acta: robos, tapones y rebotes cuentan lo que pasa con el balón, no las ayudas ni las rotaciones bien hechas. Por eso aquí pesa también el impacto en pista: cuántos puntos encaja su equipo con él y sin él.")}
      ${tablaM(K5, R, pos, "Métrica de defensa y rebote")}
      <div class="r3cols c2"><div class="r3blk"><h3>Lectura</h3><p class="r3p">${(() => { const dp = R.m.drapm ? ifOp("drapm", R.m.drapm[2]) : null, st = R.m.stl_pct ? R.m.stl_pct[2] : null, bk = R.m.blk_pct ? R.m.blk_pct[2] : null, dr = R.m.dreb_pct ? R.m.dreb_pct[2] : null; const t = [];
          if (dp != null) t.push(dp >= 65 ? "Su equipo defiende claramente mejor con él en pista." : dp <= 35 ? "Su equipo encaja más con él en pista: punto a vigilar en el sistema defensivo." : "Con él en pista, su equipo defiende en la línea de su media.");
          if (st != null && st >= 70) t.push("Lee líneas de pase: roba más que la mayoría de su puesto."); if (bk != null && bk >= 70) t.push("Protege el aro con tapones por encima de su puesto.");
          if (dr != null) t.push(dr >= 65 ? "Cierra bien el rebote defensivo, lo que acaba posesiones." : dr <= 35 ? "Rebotea poco en defensa: necesita compañeros que cierren." : ""); return E(t.filter(Boolean).join(" ")); })()}</p></div>
        <div class="r3blk">${simDf ? `<h3>Su producción defensiva con el rol asignado</h3>${simDf}` : ""}</div></div>
      <div class="r3blk"><h3>La confianza de su entrenador actual</h3><dl class="r3id r3rolid">${[["Titular", b.q_titular != null && b.gp ? `${b.q_titular} de ${b.gp} partidos` : b.gs != null && b.gp ? `${b.gs} de ${b.gp} partidos` : "–"], ["En pista en los finales", b.q_cierra != null && b.gp ? `${b.q_cierra} de ${b.gp} partidos` : "–"], ["Minutos en el último cuarto", b.q_pct_min_q4 != null ? `${N(b.q_pct_min_q4, 0)} % de los suyos` : "–"], ["Minutos decisivos", b.q_clutch_min != null ? `${N(b.q_clutch_min, 0)}'${b.q_clutch_net != null ? ` · Net ${SG0(b.q_clutch_net, 1)}` : ""}` : "–"], ["Faltas recibidas", b.pfd_pg != null ? `${N(b.pfd_pg, 1)} por partido` : "–"], ["+/− por partido", b.plus_minus_pg != null ? SG0(b.plus_minus_pg, 1) : "–"]].map(([a, v]) => `<div><dt>${a}</dt><dd>${E(v)}</dd></div>`).join("")}</dl><p class="r3n">Datos del jugada a jugada de su temporada actual. Que cierre partidos dice mucho de cómo lo ve su cuerpo técnico en defensa.</p></div>` });

    // 6 · contexto y conexiones
    const necT = nec ? `<table class="r3t nec"><thead><tr><th>Aspecto del juego</th><th>${E(d.nombre_club)} en su liga</th><th>${E(apeJ)}</th><th>Lectura</th></tr></thead><tbody>${nec.map((x) => `<tr><td><b>${E(x.n)}</b><small>${E(x.det)}</small></td><td>${barraPR(x.e, null, null, { ref: 50, w: 110, cls: x.estilo ? "neu" : x.e >= 65 ? "up" : x.e <= 35 ? "dn" : "" })}</td><td>${barraPR(x.p, null, null, { ref: 50, w: 110, cls: x.estilo ? "neu" : x.p >= 65 ? "up" : x.p <= 35 ? "dn" : "" })}</td><td class="ver ${x.v[0]}">${E(x.v[1])}</td></tr>`).join("")}</tbody></table>` : "";
    const ctxHtml = d ? (() => {
      const est = s2ok ? s2.estilo : null, hueco = est && est.hueco_cubierto ? simEu(est.hueco_cubierto) : null, peu = est ? euDeVec(est.jugador) : null, teu = est ? euDeVec(est.equipo) : null;
      const dU = est ? 100 * (est.d_entropia_uso || 0) : null, dPs = est ? 100 * (est.d_entropia_pases || 0) : null;
      const plant = s2ok ? (s2.plantilla || []).filter((p) => !p.fichaje && p.minutos_sin != null && Math.abs(p.minutos - p.minutos_sin) >= 1).sort((x, y) => (x.minutos - x.minutos_sin) - (y.minutos - y.minutos_sin)).slice(0, 4) : [];
      const qd = sim.qa != null && sim.qd != null ? Math.round(ESC.dS("sinergia_rapm", sim.qd)) - Math.round(ESC.dS("sinergia_rapm", sim.qa)) : null;
      return `<div class="r3cols c2"><div class="r3blk"><h3>Estilo y encaje en el sistema</h3><p class="r3p">${peu ? `${E(apeJ)} es un jugador de estilo <b>${E(peu.eu_etiqueta)}</b>` : `${E(apeJ)}`}${teu ? ` en un equipo de estilo <b>${E(teu.eu_etiqueta)}</b>` : ""}.${hueco ? ` Su perfil cubre sobre todo el hueco de <b>${E(hueco.eu_etiqueta)}</b> que deja la plantilla.` : ""}${dU != null ? ` Con él, el balón se reparte ${Math.abs(dU) < 0.5 ? "igual que ahora" : dU > 0 ? "entre más manos" : "en menos manos"} y la circulación de pase se vuelve ${Math.abs(dPs) < 0.5 ? "igual de variada" : dPs > 0 ? "más variada (menos previsible para el rival)" : "más concentrada"}.` : ""}</p>
          ${qd != null ? `<p class="r3n"><b>Química de la plantilla:</b> ${ESC.txt(ESC.dS("sinergia_rapm", sim.qa))} → ${ESC.txt(ESC.dS("sinergia_rapm", sim.qd))} (${Math.abs(qd) < 2 ? "apenas cambia: encaja sin alterar el equilibrio" : qd > 0 ? "mejora cómo se combinan los perfiles" : "resta química: habría que acompañarlo bien"}).</p>` : ""}</div>
        <div class="r3blk"><h3>Conexiones: con quién jugaría</h3>${eqv && eqv.quintetos ? `<table class="r3t q5"><tbody>${eqv.quintetos.map((q) => `<tr><td class="num">${Math.round(100 * q.prob)} %</td><td>${q.nombres.map((x) => { const n = E(nom(String(x)).split(" ").slice(-1)[0]); return String(x) === String(s2.nombre) ? `<b>${n}</b>` : n; }).join(" · ")}</td><td class="num">${SG(q.net, 1)}</td></tr>`).join("")}</tbody></table><p class="r3n">Quintetos más repetidos en las temporadas simuladas y su impacto conjunto (pts/100 frente a uno medio).</p>` : ""}
          ${plant.length ? `<p class="r3n"><b>A quién quitaría minutos:</b> ${plant.map((p) => `${E(nom(p.nombre || "").split(" ").slice(-1)[0])} (${N(p.minutos_sin, 0)}' → ${N(p.minutos, 0)}')`).join(", ")}.</p>` : ""}</div></div>
        <div class="r3blk"><h3>Lugar en la plantilla por nivel</h3><ol class="r3rank">${sim.orden.slice(0, 12).map((o, i) => { const S = sNivL(o.L, d.temporada) ?? 0; return `<li class="${o.el ? "yo" : o.j.pos3 === j.pos3 ? "pos" : ""}"><span>${i + 1}</span><span>${E(nom(o.j.nombre))}${o.el ? " · simulado" : ""}</span><b>${ESC.txt(S)}</b></li>`; }).join("")}</ol></div>`; })()
      : (() => { const A = c.actual || {}, sa = A.sim, nA = A.nec, cl = A.club;
        const tabla = nA ? `<table class="r3t nec"><thead><tr><th>Aspecto del juego</th><th>${E(cl ? cl.nombre_club : "Su equipo")} en su liga</th><th>${E(apeJ)}</th></tr></thead><tbody>${nA.map((x) => `<tr><td><b>${E(x.n)}</b><small>${E(x.det)}</small></td><td>${barraPR(x.e, null, null, { ref: 50, w: 150, cls: x.estilo ? "neu" : x.e >= 65 ? "up" : x.e <= 35 ? "dn" : "" })}</td><td>${barraPR(x.p, null, null, { ref: 50, w: 150, cls: x.estilo ? "neu" : x.p >= 65 ? "up" : x.p <= 35 ? "dn" : "" })}</td></tr>`).join("")}</tbody></table><p class="r3n">Equipo: percentil entre los clubes de su liga. Jugador: percentil frente a su puesto en la Euroliga. Muestra en qué se apoya hoy su equipo y qué pone él.</p>` : "";
        const rank = sa && sa.orden ? `<div class="r3blk"><h3>Su lugar en la plantilla actual por nivel</h3><ol class="r3rank">${sa.orden.filter((o) => !o.el || true).slice(0, 12).map((o, i) => { const S = sNivL(o.L, j.temporada) ?? 0; return `<li class="${o.j === j ? "yo" : ""}"><span>${i + 1}</span><span>${E(nom(o.j.nombre))}</span><b>${ESC.txt(S)}</b></li>`; }).join("")}</ol>${sa.qa != null ? `<p class="r3n"><b>Química de su plantilla actual:</b> ${ESC.txt(ESC.dS("sinergia_rapm", sa.qa))} en escala ±100.</p>` : ""}</div>` : "";
        return `${tabla}${rank}<p class="r3n">Esta lectura no incluye club de destino: describe su papel en ${E(clubN)}. Con un destino, se añade cómo cambiaría ese equipo con él dentro.</p>`; })();
    pags.push({ sec: "Contexto y conexiones", html: `${ceja(6, "Contexto y conexiones", d ? `Cómo cambia ${E(d.nombre_club)} con ${E(apeJ)} dentro` : `Su papel en ${E(clubN)}`, d ? "El baloncesto no es una suma de individualidades. Aquí se lee lo que cubre del equipo, con quién compartiría pista y cómo se reparte el balón con él." : "El baloncesto no es una suma de individualidades: un jugador se entiende junto a sus compañeros. Así encaja hoy en su equipo.")}${necT}${ctxHtml}` });

    // 7 · glosario
    const G = [["Lectura", "La conclusión de Cerno sobre un jugador para un club concreto, con su razonamiento y su margen de error."], ["Rango", "Entre qué valores es probable que esté una cifra. El rango del 90 % deja fuera solo los escenarios más extremos; el del 50 %, el tramo central."], ["Confianza", "Alta, moderada o baja según la muestra del jugador, el salto de liga y la regularidad de su rendimiento."],
      ["Vara Euroliga", "Las cifras de otras ligas se traducen a lo que valdrían en la Euroliga. Así se compara con la misma regla a jugadores de competiciones distintas."], ["Percentil por puesto", "Posición frente a los jugadores de su puesto en la Euroliga: 80 significa mejor que el 80 % de ellos; 50 es el mediano."], ["Escala ±100", "Nivel, impacto y química se expresan de −100 a +100; 0 es la media de la Euroliga."],
      ["Nivel Cerno", "Valoración global del jugador en la vara Euroliga, a partir de su eficiencia y producción."], ["Índice Fit", "Éxito esperado del fichaje en ese club con el rol asignado: minutos que sostendría y nivel que daría frente a un fichaje medio (0)."], ["ADAPT%", "Qué parte de su rendimiento traducido mantendría al cambiar de liga y país. 100 = todo; 95 = pierde un 5 %."],
      ["Rol", "Residual (menos de 5'), Profundidad (5–15'), Rotación (15–22'), Titular (más de 22' y de inicio) y Go-to-guy (referencia ofensiva). En la simulación lo asigna el club."], ["Química", "Cómo se combinan los perfiles de la plantilla por parejas, en escala ±100."], ["Reparto del balón", "Lo concentrado o repartido que está el uso del balón y el pase: más repartido es más difícil de defender."],
      ["RAPM-EL", "Puntos por 100 posesiones que suma su equipo con él en pista, descontando compañeros y rivales."], ["ORtg / DRtg", "Puntos que produce y que encaja su equipo por 100 posesiones."], ["TS% / eFG%", "Acierto real (cuenta triples y libres) y acierto de campo con el triple valiendo uno y medio."],
      ["USG%", "Parte de las jugadas del equipo que termina él: su peso en el ataque."], ["AST% / TOV%", "Canastas de compañeros que asiste y balones que pierde por cada 100 jugadas que usa."], ["OREB% / DREB%", "Rebotes de ataque y de defensa que captura de los disponibles."], ["STL% / BLK% / STOP%", "Robos, tapones y posesiones rivales que acaba con éxito."], ["3PAr / FTr", "Peso del triple en sus tiros y tiros libres que provoca por cada 100 tiros."]];
    const estG = EUS().map((e) => `<div><dt><i class="r3sw" style="background:${e.color}"></i>${E(e.nombre)}</dt><dd>${E(e.definicion || "")}</dd></div>`).join("");
    pags.push({ sec: "Glosario", html: `${ceja(7, "Glosario", "Lo imprescindible para leer cada cifra", "")}<dl class="r3glos">${G.map(([a, t]) => `<div><dt>${E(a)}</dt><dd>${E(t)}</dd></div>`).join("")}</dl>
      <div class="r3blk"><h3>Estilos de juego</h3><dl class="r3glos est">${estG}</dl></div>
      ${ligasVara(j, d)}
      <p class="r3n">Fuentes: actas oficiales y jugada a jugada de cada competición (liga regular), datos públicos a ${E(fecha)}. Modelos y simulación de Cerno Analytics. Una temporada es una muestra: con menos de 500 minutos las cifras oscilan mucho.</p>` });
    pags.push({ portada: true, back: true, html: `<img src="${INF_LOGO.vn}" alt="Cerno" class="cvback-logo"><p class="cvclaim">Make the right read.</p><p class="cvfine">Cerno Analytics · Documento confidencial</p>` });
    const Nn = pags.length; let num = 0;
    pags.forEach((p) => { if (!p.portada) p.num = ++num; });
    pags[0].html = pags[0].html.replace("@@INDICE@@", pags.map((p, i) => p.portada ? "" : `<li><span>${String(p.num).padStart(2, "0")}</span><span>${E(p.sec)}</span><b>${i + 1}</b></li>`).join(""));
    return pags.map((p, i) => hoja(p.html, { ...p, n: i + 1, N: Nn, fecha, extra }));
  }

  // ------------------------------------------------------------------------------------------- 6. pintado
  let ULT = null;
  async function medias(tray) {
    const out = new Map(), ts = [...new Set(tray.map((x) => x.temporada))].slice(-6);
    for (const t of ts) { try { const D = await ifCargar(t), ix = indice(D, t); tray.filter((x) => x.temporada === t).forEach((x) => { const e = ix.get(jKey(x)); if (e && e.b) out.set(jKey(x), e.b); }); } catch (e) { /* temporada sin informe */ } }
    return out;
  }
  async function pintarV3() {
    if (!META || !$1("#ifPages")) return;
    controles();
    const tok = ++IFTOK, { s } = ifEstado(), j = JK.get(s.jug), box = $1("#ifPages");
    if (!j) { box.innerHTML = `<p class="note">Elige un jugador.</p>`; return; }
    $1("#ifMsg").textContent = ""; IFPDF = null; ifAlternativas(false); box.classList.add("cargando");
    let D, R0; try { ({ D, R0 } = await entrada(j)); } catch (e) { if (tok === IFTOK) { box.classList.remove("cargando"); box.innerHTML = `<p class="note">No se pudieron cargar los datos del informe (${E(e.message || e)}).</p>`; } return; }
    let sim = null, nec = null, d = null, s2 = null;
    const recJ = (await (cargarSim().catch(() => null)), simRec(j));
    const rolBox = $1("#ifRolBox"); if (rolBox) rolBox.hidden = !s.sim;
    if (s.sim) { d = ifClub(s.dClub, s.dTemp); await ifCargarEq(); if (d) sim = ifSimular(j, d); }
    // rol asignado: el elegido para este jugador-destino; por defecto, su rol de partida
    const rol0 = rolDeRec(recJ) || rolEstimado(j, R0 && R0.b) || "ROTACION";
    const rol = (st.inf.rol && st.inf.rolDe === claveNota() && ROLES.includes(st.inf.rol)) ? st.inf.rol : rol0;
    if ($1("#ifRol")) $1("#ifRol").value = rol;
    if (sim && !sim.mismo && recJ && SIMD && !SIMD.error) { const club = simClub(d); if (club) { try { s2 = SIM2.simular({ rec: recJ, club, bajas: new Set(), rol }); } catch (e) { s2 = { error: e.message }; } } }
    if (tok !== IFTOK) return;
    if (!R0) { box.classList.remove("cargando"); box.innerHTML = `<p class="note">Sin datos detallados de ${E(nom(j.nombre))} en ${E(j.temporada)}.</p>`; return; }
    const R = { ...R0, ref: D.ref, pool_de: D.pool_de, min_pool: D.min_pool, pool_n: D.pool_n, liga: j.liga };
    const pos = ["E", "A", "I"].includes(j.pos3) ? j.pos3 : "A";
    if (sim && !sim.mismo) nec = ifNecesidades(d, R);
    const tray = JG.filter((x) => x.persona_id === j.persona_id).sort((a, x) => a.temporada.localeCompare(x.temporada) || x.min - a.min);
    const med = await medias(tray); if (tok !== IFTOK) return;
    const fecha = new Date().toLocaleDateString("es-ES", { day: "numeric", month: "long", year: "numeric" });
    const notaFin = ($1("#ifPorqueFinal") && $1("#ifPorqueFinal").value.trim()) || ($1("#ifPorque") && $1("#ifPorque").value.trim()) || "";
    const nacT = tray.map((x) => (simRec(x) || {}).nac).find(Boolean);
    let actual = null; if (!(sim && !sim.mismo)) { try { await ifCargarEq(); const cl = BY.get(j.clave); if (cl) { const sa = ifSimular(j, cl); actual = { club: cl, nec: ifNecesidades(cl, R), sim: sa }; } } catch (e) { actual = null; } }
    let esc = [];
    if (s2 && !s2.error) { const club = simClub(d); esc = ROLES.map((r) => { try { const x = r === rol ? s2 : SIM2.simular({ rec: recJ, club, bajas: new Set(), rol: r }); return x && !x.error ? { rol: r, r: x } : null; } catch (e) { return null; } }).filter(Boolean); }
    const hojas = paginas({ j, R, pos, sim, s2: s2 && !s2.error ? s2 : null, nec, fecha, tray, medias: med, nota: notaFin, rol, nac: pais(nacT), esc, ritmo: D.ritmo_el || 72, actual });
    box.innerHTML = hojas.map((h) => `<div class="ifwrap">${h}</div>`).join("");
    box.classList.remove("cargando"); ifEscalar();
    $1("#ifSimNota").innerHTML = s.sim ? (sim && sim.mismo ? `<span class="warn">Ya juega en ese club esa temporada: elige otro destino.</span>` : s2 && s2.error ? `<span class="warn">No se pudo simular (${E(s2.error)}).</span>` : !s2 && sim ? `<span class="warn">El simulador no tiene plantilla de ese club y temporada (hay de 2025-26 y 2026-27): se muestra la lectura sin simulación de rol.</span>` : "") : "";
    IFULT = { nom: nom(j.nombre), temp: j.temporada, dest: sim && !sim.mismo ? sim.d.nombre_club : null };
    $1("#ifResumen").textContent = `${hojas.length} páginas A4 · ${nom(j.nombre)}${IFULT.dest ? ` → ${IFULT.dest}` : ""}`;
    // contexto para la redacción en tono Cerno (solo datos del propio informe)
    const club = BY.get(j.clave), pL = R.m.L ? R.m.L[2] : null;
    ULT = { ctx: [`Jugador: ${nom(j.nombre)}, ${IF_POS1[pos] || "jugador"}, ${j.edad != null ? Math.round(j.edad) + " años" : "edad s/d"}, ${club ? club.nombre_club : j.nombre_club} (${LIGAS[j.liga] || j.liga} ${j.temporada}).`,
      `Estilo: ${euLab(j)}. Nivel: ${etiqueta(pL)}${pL != null ? ` (percentil ${Math.round(pL)} en su puesto)` : ""}.`,
      sim && !sim.mismo ? `Destino: ${sim.d.nombre_club} (${LIGAS[sim.d.liga] || sim.d.liga} ${sim.d.temporada}), rol asignado ${ROLN[rol]}.` : "Sin club de destino.",
      s2 && !s2.error ? `Simulación: ${N(s2.minutos.media, 0)} minutos por partido; adaptación ${N(s2.adaptacion.adapt_pct_temporada.media, 0)} sobre 100; Índice Fit ${ESC.txt(ESC.dS("z", s2.fit.total))}.` : "",
      nec ? `Cubre carencias del equipo en: ${nec.filter((x) => x.v[1] === "Cubre una carencia").map((x) => x.n.toLowerCase()).join(", ") || "ninguna clara"}.` : ""].filter(Boolean).join("\n") };
  }
  pintarInforme = pintarV3;            // el resto de la página (controles, PDF, HTML) llama a esta función por su nombre
  window.CernoInformeV3 = { version: "3.0", indice, paginas };

  // ------------------------------------------------------------------------------------------- 7. estilos (pantalla, PDF e HTML imprimible)
  const CSS3 = `
.ifsheet.r3{--i:#12161B;--i2:#3B434C;--mu:#545D67;--fa:#737B84;--ln:#DAD7CF;--l2:#C2C3BF;--s2:#E8E5DD;--up:#2A6FA8;--dn:#C4552E;--vi:#7A5BC8;font:400 10px/1.45 "Mona Sans",system-ui,sans-serif;color:var(--i)}
.ifsheet.r3 .r3head{display:flex;gap:10px;align-items:center;padding:30px 52px 9px;font:500 6.6px/1 "Geist Mono",ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--mu);border-bottom:1.2px solid var(--i)}
.ifsheet.r3 .r3head span:nth-child(2){margin-left:auto;color:var(--i2)}.ifsheet.r3 .r3head .r3hsec{color:var(--i);font-weight:600}
.ifsheet.r3 .r3body{padding:22px 52px 8px;gap:16px}
.ifsheet.r3 .r3foot{display:flex;align-items:center;gap:14px;padding:9px 52px 26px;border-top:.6px solid var(--l2);font:500 6.6px "Geist Mono",ui-monospace,monospace;letter-spacing:.08em;color:var(--mu);text-transform:uppercase}
.ifsheet.r3 .r3foot span:last-child{margin-left:auto;color:var(--i)}
.ifsheet.r3 .r3foot .ifscale{display:inline-flex;align-items:flex-end;height:9px}.ifsheet.r3 .r3foot .ifscale i{display:block;width:.6px;height:4px;margin-right:4.8px;background:#737B84}.ifsheet.r3 .r3foot .ifscale i.M{height:7px}.ifsheet.r3 .r3foot .ifscale i.on{width:1.8px;height:9px;background:#12161B}
.r3sec{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;border-top:1.6px solid var(--i);padding-top:9px}
.r3ceja{font:500 7.4px "Geist Mono",ui-monospace,monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--mu)}
.r3sec h2{font:620 24px/1.12 "Mona Sans",sans-serif!important;letter-spacing:-.02em!important;margin:5px 0 0!important;max-width:560px;text-transform:none!important}
.r3num{font:250 42px/1 "Mona Sans",sans-serif;color:var(--l2);letter-spacing:-.02em}
.r3lead{font:400 13.4px/1.45 "Newsreader",Georgia,serif;color:var(--i2);margin-top:7px!important;max-width:590px}
.r3p{font:400 11.8px/1.5 "Mona Sans",sans-serif;color:var(--i2);margin:0 0 7px!important}
.r3n{font:400 9.4px/1.45 "Mona Sans",sans-serif;color:var(--mu);margin-top:5px!important}
.r3lab,.r3tag{display:block;font:500 7.2px "Geist Mono",ui-monospace,monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--mu);margin-bottom:6px}
.r3cols{display:grid;grid-template-columns:1.15fr 1fr;gap:20px}.r3cols.c2{grid-template-columns:1fr 1fr}
.r3blk h3{font:620 12.4px/1.25 "Mona Sans",sans-serif!important;letter-spacing:-.005em!important;margin:0 0 6px!important;padding-top:7px;border-top:.9px solid var(--i);text-transform:none!important}
.r3q dl{display:grid;gap:7px;margin:0}.r3q dl div{display:grid;grid-template-columns:72px 1fr;gap:8px;border-top:.5px solid var(--l2);padding-top:6px}.r3q dt{font:620 11px "Mona Sans",sans-serif}.r3q dd{margin:0;font-size:10.6px;color:var(--i2)}.r3q em{color:var(--mu)}
.r3steps ol{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(4,1fr);gap:14px;counter-reset:p}.r3steps li{counter-increment:p;border-top:.9px solid var(--i);padding-top:7px}
.r3steps li::before{content:"0" counter(p);display:block;font:500 7.4px "Geist Mono",monospace;color:var(--mu);margin-bottom:4px}.r3steps b{display:block;font:620 11.6px/1.2 "Mona Sans",sans-serif;margin-bottom:4px}.r3steps span{font-size:10.4px;color:var(--i2);line-height:1.45}
.r3call{background:#12161B;color:#F3F0E8;padding:12px 16px}.r3call.callout .r3tag{color:#F2CC2F;border:1px solid #F2CC2F;display:inline-block;padding:2px 6px}.r3call p{font:400 13px/1.45 "Newsreader",Georgia,serif;margin:4px 0 0!important}
.r3id{display:grid;grid-template-columns:repeat(6,1fr);gap:0;margin:0;border-top:.9px solid var(--i)}.r3id div{padding:7px 8px 6px 0;border-right:.5px solid var(--l2)}.r3id div:last-child{border:0}
.r3id dt{font:500 7.4px "Geist Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--mu)}.r3id dd{margin:3px 0 0;font:620 12px/1.2 "Mona Sans",sans-serif}
.r3t{width:100%;border-collapse:collapse;font-size:10.4px}.r3t th{font:500 7.4px "Geist Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--mu);text-align:left;padding:0 6px 5px 0;border-bottom:.9px solid var(--i)}
.r3t td{padding:5px 6px 5px 0;border-bottom:.5px solid var(--l2);vertical-align:middle}.r3t td small{display:block;font-size:8.4px;color:var(--mu);line-height:1.25;margin-top:1px}.r3t .num{text-align:right;font-family:"Geist Mono",ui-monospace,monospace;white-space:nowrap}.r3t.sim{font-size:9.8px}
.r3t td.num small{font-family:"Geist Mono",monospace}.r3t tr.yo td{background:rgba(242,204,47,.28)}.r3t td b.up{color:var(--up)}.r3t td b.dn{color:var(--dn)}
.r3t.tray td{padding:5px 6px 5px 0}.r3t.tray td:nth-child(2) small{display:inline;margin-left:5px}
.r3t td.ver{font-weight:600;font-size:9.8px}.r3t td.ver.up{color:var(--up)}.r3t td.ver.dn{color:var(--dn)}
.r3pr{display:block}.r3pr .tr{stroke:#C2C3BF;stroke-width:1}.r3pr .rf{stroke:#737B84;stroke-width:.8;stroke-dasharray:1.5 1.5}.r3pr .bd{fill:rgba(42,111,168,.18)}.r3pr .pt{fill:#12161B}.r3pr .pt.up{fill:#2A6FA8}.r3pr .pt.dn{fill:#C4552E}.r3pr .pt.neu{fill:#7A5BC8}
.r3na{font-size:8px;color:var(--fa)}
.r3sw{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;vertical-align:0}
.r3rol{display:inline-block;font:500 7.6px "Geist Mono",monospace;letter-spacing:.04em;border:.6px solid #C2C3BF;padding:1px 5px;white-space:nowrap}.r3rol.r-titular,.r3rol.r-go_to_guy{border-color:#12161B;font-weight:600}
.r3est{display:grid;grid-template-columns:210px 1fr;gap:16px;align-items:start;border-top:.9px solid var(--i);padding-top:8px}.r3est b{display:block;font:620 16px "Mona Sans",sans-serif}.r3est small{display:block;font-size:9.4px;color:var(--mu);margin-top:2px}.r3est p{font:400 12.6px/1.45 "Newsreader",Georgia,serif;color:var(--i2);margin:0}
.r3kp{display:grid;grid-template-columns:repeat(4,1fr);border-top:.9px solid var(--i);border-bottom:.5px solid var(--l2)}.r3kp.big{grid-template-columns:1.2fr repeat(4,1fr)}
.r3kp>div{padding:8px 10px 8px 0;border-right:.5px solid var(--l2);margin-right:10px}.r3kp>div:last-child{border:0;margin:0}
.r3kp span{display:block;font:500 7.4px "Geist Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--mu)}.r3kp b{display:block;font:620 25px/1.1 "Mona Sans",sans-serif;letter-spacing:-.02em;margin:4px 0 2px}.r3kp b.r3w{font-size:13px;line-height:1.4}
.r3kp .idx{border-left:2pt solid #12161B;padding-left:10px}.r3kp .idx b{font-size:34px}.r3kp small{display:block;font-size:8.6px;color:var(--mu);line-height:1.3}.r3kp b.up{color:var(--up)}.r3kp b.dn{color:var(--dn)}
.r3l{list-style:none;padding:0;margin:0;display:grid;gap:5px}.r3l li{display:grid;gap:1px;padding-left:9px;border-left:2px solid #C2C3BF}.r3l.up li{border-left-color:#2A6FA8}.r3l.dn li{border-left-color:#C4552E}.r3l b{font:620 10.8px "Mona Sans",sans-serif}.r3l span{font-size:10px;color:var(--i2)}
.r3why{background:#262C33;color:#F3F0E8;padding:12px 16px 10px}.r3why.callout .r3tag{color:#F2CC2F;border:1px solid #F2CC2F;display:inline-block;padding:2px 6px}.r3why p{font:400 12.6px/1.5 "Newsreader",Georgia,serif;margin:3px 0 6px!important}.r3why .r3vacio{color:#9AA0A6;font-style:italic}
.r3cv{width:100%;height:auto;display:block}.r3cv .rf{stroke:#737B84;stroke-dasharray:2 2;stroke-width:.8}.r3cv .bd{fill:rgba(42,111,168,.18)}.r3cv .ln{fill:none;stroke:#12161B;stroke-width:1.4}.r3cv .ax{font:500 7px "Geist Mono",monospace;fill:#545D67}
.r3blk .ifcourt{width:100%;height:auto}.r3blk .ifcourt .zn{font:600 8px "Mona Sans",sans-serif;fill:#12161B;text-anchor:middle}.r3blk .ifcourt .zv{font:600 11px "Geist Mono",monospace;fill:#12161B;text-anchor:middle}.r3blk .ifcourt .zm,.r3blk .ifcourt .zf{font:500 7px "Geist Mono",monospace;fill:#545D67;text-anchor:middle}
.r3rank{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:1fr 1fr;column-gap:20px}.r3rank li{display:grid;grid-template-columns:20px 1fr auto;gap:6px;padding:3.5px 0;border-bottom:.5px solid #C2C3BF;font-size:10px}.r3rank li span:first-child{font-family:"Geist Mono",monospace;color:#545D67}.r3rank li b{font-family:"Geist Mono",monospace;font-weight:500}.r3rank li.yo{background:rgba(242,204,47,.28);font-weight:620}.r3rank li.pos span:nth-child(2){color:#12161B}
.r3t.q5 td{font-size:9.8px}
.r3glos{display:grid;grid-template-columns:1fr 1fr;column-gap:22px;row-gap:0;margin:0}.r3glos div{display:grid;grid-template-columns:96px 1fr;gap:8px;padding:5px 0;border-bottom:.5px solid #C2C3BF}.r3glos dt{font:620 10px "Mona Sans",sans-serif}.r3glos dd{margin:0;font-size:9.4px;color:var(--i2);line-height:1.4}.r3glos.est div{grid-template-columns:86px 1fr}
.ifsheet.r3.cover{background:#12161B;color:#F3F0E8}.ifsheet.r3.cover .ifbody{padding:58px 62px 46px;display:flex;flex-direction:column;justify-content:space-between;position:relative;height:100%}
.ifsheet.r3.cover .cvtop{display:flex;justify-content:space-between;align-items:center}.ifsheet.r3.cover .cvlogo{height:40px;width:auto;display:block}.ifsheet.r3.cover .cvk{font:500 7.6px "Geist Mono",monospace;letter-spacing:.12em;text-transform:uppercase;color:#C2C3BF}
.ifsheet.r3.cover h1{font:620 46px/1.04 "Mona Sans",sans-serif!important;letter-spacing:-.03em!important;color:#F3F0E8;margin:0!important;text-transform:none!important}
.ifsheet.r3.cover h1 .hl{color:#12161B;background:linear-gradient(transparent 10%,#F2CC2F 10%,#F2CC2F 92%,transparent 92%);padding:0 .1em;-webkit-box-decoration-break:clone;box-decoration-break:clone}
.ifsheet.r3.cover .cvdat{font:400 14px/1.45 "Newsreader",Georgia,serif;color:#C2C3BF;margin-top:14px!important}
.ifsheet.r3.cover .cvfacts{display:grid;grid-template-columns:repeat(4,1fr);margin-top:26px!important;border-top:1.2px solid #F3F0E8}.ifsheet.r3.cover .cvfacts div{padding:8px 10px 0 0}.ifsheet.r3.cover .cvfacts dt{font:500 6.8px "Geist Mono",monospace;letter-spacing:.1em;text-transform:uppercase;color:#9AA0A6}.ifsheet.r3.cover .cvfacts dd{margin:4px 0 0;font:500 11px "Geist Mono",monospace;color:#F3F0E8}
.ifsheet.r3.cover .cvidx{list-style:none;padding:0;margin:0;display:grid;gap:0;max-width:330px}.ifsheet.r3.cover .cvidx li{display:grid;grid-template-columns:24px 1fr auto;gap:8px;padding:5px 0;border-bottom:.5px solid #3B434C;font:500 9.4px "Mona Sans",sans-serif;color:#C2C3BF}.ifsheet.r3.cover .cvidx li span:first-child,.ifsheet.r3.cover .cvidx li b{font:500 8px "Geist Mono",monospace;color:#9AA0A6}
.ifsheet.r3.cover .cvbot{display:grid;grid-template-columns:1.4fr 1fr 1fr;gap:14px;border-top:.6px solid #3B434C;padding-top:10px}.ifsheet.r3.cover .cvbot span{display:block;font:500 6.6px "Geist Mono",monospace;letter-spacing:.1em;text-transform:uppercase;color:#9AA0A6}.ifsheet.r3.cover .cvbot b{display:block;font:500 9px "Geist Mono",monospace;color:#F3F0E8;margin-top:3px}
.ifsheet.r3.cover .cvscale{position:absolute;right:62px;top:120px;display:inline-flex;align-items:flex-end;height:14px}.ifsheet.r3.cover .cvscale i{width:.8px;height:6px;margin-right:6px;background:#737B84;display:block}.ifsheet.r3.cover .cvscale i.M{height:10px}.ifsheet.r3.cover .cvscale i.on{width:2.4px;height:14px;background:#F2CC2F}
.ifsheet.r3.cover.back .ifbody{align-items:center;justify-content:center;gap:18px}.ifsheet.r3.cover.back .cvback-logo{height:120px;width:auto}.ifsheet.r3.cover.back .cvclaim{font:620 20px "Mona Sans",sans-serif;color:#F3F0E8;margin:0}.ifsheet.r3.cover.back .cvfine{position:absolute;bottom:40px;font:500 7px "Geist Mono",monospace;letter-spacing:.1em;text-transform:uppercase;color:#9AA0A6}
#ifRolBox{display:grid;gap:6px;margin-top:4px}#ifPorqueBox{display:grid;gap:6px}#ifPorqueBox textarea{width:100%;font:400 13px/1.45 var(--f-body);color:var(--ink);background:var(--surface);border:1px solid var(--line-2);border-radius:2px;padding:8px 10px;resize:vertical}
.ifpq-acc{display:flex;gap:6px;flex-wrap:wrap}
.ifsheet.r3 .r3t th{background:none!important}.ifsheet.r3 .cvidx{grid-template-columns:1fr!important;column-gap:0!important}.ifsheet.r3.cover .cvidx li{grid-template-columns:24px 1fr auto!important}
.r3vals>div{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.r3vals>div>div{border-top:.9px solid var(--i);padding-top:7px;display:grid;gap:4px;align-content:start}.r3vals b{font:620 11px "Mona Sans",sans-serif}.r3vals span{font-size:9.8px;color:var(--i2);line-height:1.4}
.r3read>div{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.r3read>div>div{border-top:.9px solid var(--i);padding-top:7px;display:grid;gap:4px;align-content:start}.r3read b{font:620 11px "Mona Sans",sans-serif}.r3read span{font-size:9.8px;color:var(--i2);line-height:1.4}.r3big{font:620 22px/1 "Mona Sans",sans-serif;margin:0!important}
.r3cols3{display:flex;align-items:center;gap:5px;font-size:8.4px;color:var(--i2);margin:2px 0!important;flex-wrap:wrap}.r3cols3 i{width:8px;height:8px;border-radius:50%;display:inline-block}
.r3ev{width:100%;height:auto;display:block}.r3ev .g{stroke:#DAD7CF;stroke-width:.6}.r3ev .z{stroke:#737B84;stroke-width:.7;stroke-dasharray:2 2}.r3ev .ln{fill:none;stroke:#12161B;stroke-width:1.4}.r3ev .lr{fill:none;stroke:#9AA0A6;stroke-width:1.2;stroke-dasharray:3 2}.r3ev .pn{fill:#12161B}.r3ev .pv{font:600 7.4px "Geist Mono",monospace;fill:#12161B}.r3ev .ax{font:500 6.8px "Geist Mono",monospace;fill:#545D67}
.r3t.bloq td{padding:5px 6px 5px 0}.r3t.esc td small{color:#545D67}.r3lec{border-left:2pt solid #12161B;padding-left:10px}
.r3mini{display:grid;grid-template-columns:repeat(4,1fr);border-top:.5px solid #C2C3BF;border-bottom:.5px solid #C2C3BF}.r3mini div{padding:6px 0}.r3mini b{display:block;font:620 19px/1.1 "Mona Sans",sans-serif}.r3mini small{font-size:9px}.r3mini span{font:500 6.8px "Geist Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:#545D67}
.r3id.r3rolid{grid-template-columns:repeat(3,1fr);row-gap:0}.r3id.r3rolid div{border-bottom:.5px solid #C2C3BF}.r3id.r3rolid div:nth-child(3n){border-right:0}
.r3lig{display:grid;grid-template-columns:1fr 1fr;column-gap:22px}.r3lig div{display:grid;grid-template-columns:1fr 160px 30px;gap:8px;align-items:center;padding:2.5px 0;border-bottom:.5px solid #DAD7CF;font-size:9.2px}.r3lig div.sel{font-weight:620}.r3lig b{font:500 8px "Geist Mono",monospace;text-align:right}.r3lig rect{fill:#9AA0A6}.r3lig rect.on{fill:#12161B}.r3lig .z{stroke:#737B84;stroke-width:.6}`;
  const st3 = document.createElement("style"); st3.id = "cerno-informe-v3"; st3.textContent = CSS3; document.head.appendChild(st3);
  ifEstilos = () => INF_CSS + CSS3;      // rasterizado de respaldo (SVG foreignObject)
  const _imp = ifHtmlImprimible;
  ifHtmlImprimible = () => _imp().replace("</style>", CSS3 + "\n</style>");
})();
