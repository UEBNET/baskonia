/* =====================================================================================================
   Kerno Analytics · Lectura de fichaje (informe A4) · v3.0 · 29-10-2026
   Sustituye la composición de páginas del informe v2 (ifPaginas) y su pintado (pintarInforme). Reutiliza los datos,
   el rasterizado a PDF, la descarga y el HTML imprimible de la página del Atlas.

   Estructura (bloques, no páginas): 0 portada · 1 Kerno Analytics y método · 2 el jugador · 3 conclusiones (con
   «Por qué lo proponemos», redactado en tono Kerno a partir de la nota del analista) · 4 ataque y tiro · 5 defensa y
   rebote · 6 contexto y conexiones · 7 glosario · contraportada.

   Arreglos de datos:
   - Los ficheros informe/<temporada>.json usan otra numeración de persona_id que el fichero de jugadores del Atlas
     (solo coincidía el 0,2 % de las claves → «Sin datos detallados…»). Resolución: clave exacta si existe; si no,
     emparejamiento dentro del mismo club-temporada por minutos jugados (asignación voraz por |Δminutos|).
   - Simulación del destino: motor del simulador (v3.3 desde el 04-11-2026) con el ROL QUE ASIGNA EL USUARIO (selector «Rol en el club de destino»).
   Nada de metodología interna en el documento: solo lectura, cifras con su margen y lenguaje de baloncesto.

   v3.1 · 29-10-2026 (decisión del CEO, cambios definitivos):
   - 01: nueva frase en «Basketball judgment, model rigor».
   - 02 en adelante: títulos cortos que nombran las facetas de la página; la conclusión pasa a la entradilla.
   - 02: «Estilo de juego», «Nivel Kerno», «RAPM proyectado», «Punto fuerte» y «A mejorar» en un panel Ink central.
   - 03: «Por qué lo proponemos» abre la sección; Landing del grupo de traspaso (v4.1; el ADAPT% individual se retira).
   - 04/05: sin cifras en el título; cifras clave (valor + percentil + rango) en la entradilla. 04: fuera «Qué produce
     hoy por cada 25 minutos», más métricas con el rol asignado y mapa de tiro más grande.
   - 06: tres páginas (carencias y estilo · sinergias de pareja y quinteto · impacto en la plantilla y en sus
     compañeros), sin «Conexiones: con quién jugaría». Datos de «Simular equipo completo» (contexto y química).
   - Clasificaciones en vertical por columna (plantilla por nivel, ligas del glosario).
   - Percentiles con una sola forma en todo el informe: «percentil N» (en bloques, media de percentiles).

   v3.3 · 29-10-2026: la frase de adaptación lee la forma de la curva del simulador (arranca arriba y baja, arranca abajo
   y recupera, o estable) en lugar de decir siempre «perdería un poco al principio»; «mitad del ajuste» → «mitad del cambio».
   v3.2 · 29-10-2026: títulos de sección en Index sobre banda Ink (contraste 11,6:1). Selector «Compañeros en el club de
   destino» en los controles del informe: quitar jugadores de la plantilla del simulador y añadir otros (bajas/extras del
   motor v2.1, como en «Simular equipo completo»); se guarda por club y temporada de destino (st.inf.plant). Con plantilla
   elegida, lugar en la plantilla, nivel medio y química salen de esos compañeros; el informe rotula los cambios.
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
  const rolChip = (r, est) => r ? `<span class="r3rol r-${r.toLowerCase()}${est ? " est" : ""}">${ROLN[r]}</span>` : "–";

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
      <p class="note">Lo eliges tú: el informe calcula con ese rol sus minutos, su rendimiento, el Landing de su grupo de traspaso, las sinergias y las anclas NIVEL KERNO e IMPACTO.</p></div>
      <div id="ifPlantBox"><span class="label">Compañeros en el club de destino</span>
        <p class="note">Marca quién sigue en la plantilla: quita a los que se han ido y añade a quien llegue. La simulación y todo el informe se calculan con estos compañeros.</p>
        <div id="ifPlantList" class="ifpl" role="group" aria-label="Compañeros en el club de destino"></div>
        <input type="search" id="ifPlantBus" placeholder="Añadir jugador por nombre…" aria-label="Añadir jugador a la plantilla de destino" autocomplete="off">
        <div id="ifPlantBusS" class="ifpl-res" hidden></div>
        <div class="ifpq-acc"><button class="btn ghost sm" id="ifPlantTodos" type="button">Volver a la plantilla del club</button></div></div>`);
    const hr = $1("#ifPdf") && $1("#ifPdf").previousElementSibling;
    const html = `<div id="ifPorqueBox"><span class="label">Por qué este jugador · nota del analista</span>
      <textarea id="ifPorque" rows="5" placeholder="En tus palabras: qué necesita el club, qué viste en él, por qué ahora. Se reescribe en tono Kerno para el bloque de conclusiones."></textarea>
      <div class="ifpq-acc"><button class="btn ghost sm" id="ifRedactar" type="button">Redactar en tono Kerno</button><button class="btn ghost sm" id="ifPorqueLimpiar" type="button">Borrar</button></div>
      <p class="note" id="ifPorqueMsg" aria-live="polite"></p>
      <label class="label" for="ifPorqueFinal">Texto que irá en el informe (puedes retocarlo)</label>
      <textarea id="ifPorqueFinal" rows="6" placeholder="Aparecerá aquí tras «Redactar en tono Kerno». Si lo dejas vacío, el informe usa tu nota tal cual."></textarea></div>`;
    if (hr && hr.tagName === "HR") hr.insertAdjacentHTML("beforebegin", "<hr>" + html); else $1("#ifPdf").insertAdjacentHTML("beforebegin", html);
    const nota = () => lsGet()[claveNota()] || {};
    const cargarNota = () => { const n = nota(); $1("#ifPorque").value = n.raw || ""; $1("#ifPorqueFinal").value = n.fin || ""; $1("#ifPorqueMsg").textContent = n.fin ? "Texto en tono Kerno guardado para este jugador y destino." : ""; };
    const guardarNota = () => { const o = lsGet(); o[claveNota()] = { raw: $1("#ifPorque").value, fin: $1("#ifPorqueFinal").value }; lsSet(o); };
    let tmr = null; const repintar = () => { clearTimeout(tmr); tmr = setTimeout(() => pintarInforme(), 600); };
    $1("#ifPorque").addEventListener("input", () => { guardarNota(); repintar(); });
    $1("#ifPorqueFinal").addEventListener("input", () => { guardarNota(); repintar(); });
    $1("#ifPorqueLimpiar").addEventListener("click", () => { $1("#ifPorque").value = ""; $1("#ifPorqueFinal").value = ""; guardarNota(); $1("#ifPorqueMsg").textContent = ""; pintarInforme(); });
    $1("#ifRedactar").addEventListener("click", redactar);
    $1("#ifRol").addEventListener("change", (e) => { st.inf.rol = e.target.value; st.inf.rolDe = claveNota(); guardar(); pintarInforme(); });
    controles.cargarNota = cargarNota;
    // compañeros del club de destino (mismo motor que «Simular equipo completo»: bajas y altas en la plantilla)
    const cambiaPlant = () => { guardar(); pintarInforme(); };
    $1("#ifPlantList").addEventListener("change", (e) => { const per = e.target.dataset.per; if (!per) return; const sel = plantSel();
      sel.fuera = sel.fuera.filter((x) => x !== per); if (!e.target.checked) sel.fuera.push(per); cambiaPlant(); });
    $1("#ifPlantList").addEventListener("click", (e) => { const b = e.target.closest("[data-quitar]"); if (!b) return; const sel = plantSel(); sel.extra = sel.extra.filter((x) => x !== b.dataset.quitar); cambiaPlant(); });
    $1("#ifPlantTodos").addEventListener("click", () => { const sel = plantSel(); sel.fuera = []; sel.extra = []; cambiaPlant(); });
    $1("#ifPlantBus").addEventListener("input", () => buscarPlant());
    $1("#ifPlantBusS").addEventListener("click", (e) => { const b = e.target.closest("[data-add]"); if (!b) return; const sel = plantSel();
      if (!sel.extra.includes(b.dataset.add)) sel.extra.push(b.dataset.add); sel.extra = sel.extra.slice(0, 8); $1("#ifPlantBus").value = ""; $1("#ifPlantBusS").hidden = true; cambiaPlant(); });
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
  // ---- plantilla elegida por destino: st.inf.plant["club:temporada"] = { fuera: [persona…], extra: [id del simulador…] }
  function plantSel() { const { s } = ifEstado(), p = st.inf.plant || (st.inf.plant = {}), k = `${s.dClub}:${s.dTemp}`; return p[k] || (p[k] = { fuera: [], extra: [] }); }
  const normQ = (t) => String(t || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  let PLCTX = null;   // { club, recJ } del último pintado, para la búsqueda
  function pintarPlant(club, recJ) {
    const box = $1("#ifPlantList"), pb = $1("#ifPlantBox"); if (!box || !pb) return;
    PLCTX = club ? { club, recJ } : null; pb.hidden = !club; if (!club) { box.innerHTML = ""; return; }
    const sel = plantSel(), fuera = new Set(sel.fuera), J = SIMD.jug;
    const filas = (club.plantilla || []).map(([rid, , , per]) => ({ r: J.get(rid), per, rid })).filter((o) => o.per !== (recJ && recJ.persona)).sort((a, b) => ((b.r && b.r.min_pct) || 0) - ((a.r && a.r.min_pct) || 0));
    const nomR = (o) => o.r ? nom(o.r.nombre) : o.per, sub = (r) => { if (!r) return ""; const x = jgDe(r.id); return `${r.pos3 || "–"} · ${x ? x.nombre_club : ""} ${LC[r.liga] || r.liga || ""} ${r.temporada || ""}`; };
    box.innerHTML = filas.map((o) => `<label class="${fuera.has(o.per) ? "off" : ""}"><input type="checkbox" data-per="${E(o.per)}" ${fuera.has(o.per) ? "" : "checked"}><span>${E(nomR(o))}<small>${E(sub(o.r))}</small></span></label>`).join("")
      + sel.extra.map((id) => { const r = J.get(id); return r ? `<div class="add"><span>${E(nom(r.nombre))}<small>añadido · ${E(sub(r))}</small></span><button type="button" class="btn ghost sm" data-quitar="${E(id)}" aria-label="Quitar ${E(nom(r.nombre))}">Quitar</button></div>` : ""; }).join("");
    const n = filas.length - filas.filter((o) => fuera.has(o.per)).length + sel.extra.filter((id) => J.get(id)).length;
    pb.querySelector(".label").textContent = `Compañeros en el club de destino · ${n} jugadores`;
  }
  function buscarPlant() {
    const inp = $1("#ifPlantBus"), out = $1("#ifPlantBusS"); if (!inp || !out) return;
    const q = normQ(inp.value).trim().split(/\s+/).filter(Boolean); if (!q.length || !PLCTX || !SIMD || SIMD.error) { out.hidden = true; return; }
    const ya = new Set((PLCTX.club.plantilla || []).map((x) => x[3]).concat(plantSel().extra.map((id) => (SIMD.jug.get(id) || {}).persona)));
    const mejor = new Map();
    SIMD.jug.forEach((r) => { if (!r || ya.has(r.persona) || (PLCTX.recJ && r.persona === PLCTX.recJ.persona)) return; const t = normQ(r.nombre); if (!q.every((w) => t.includes(w))) return;
      const o = mejor.get(r.persona); if (!o || r.temporada > o.temporada || (r.temporada === o.temporada && (r.min_total || 0) > (o.min_total || 0))) mejor.set(r.persona, r); });
    const res = [...mejor.values()].sort((a, b) => (b.temporada.localeCompare(a.temporada)) || ((b.min_total || 0) - (a.min_total || 0))).slice(0, 8);
    out.hidden = false;
    out.innerHTML = res.length ? res.map((r) => { const x = jgDe(r.id); return `<button type="button" data-add="${E(r.id)}">${E(nom(r.nombre))}<small>${E(r.pos3 || "–")} · ${E(x ? x.nombre_club : "")} ${E(LC[r.liga] || r.liga)} ${E(r.temporada)}</small></button>`; }).join("") : `<p class="note">Sin coincidencias en los datos del simulador.</p>`;
  }
  // nota del analista → texto en tono Kerno (Claude, vía la página principal que tiene el permiso «sample»)
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
    const prompt = `Eres redactor de Kerno Analytics, socio independiente de inteligencia de talento para el deporte de élite, empezando por el baloncesto. Reescribe la nota del analista para el apartado «Por qué lo proponemos» de una lectura de fichaje que leerá un director deportivo.

Voz de marca: exacta, franca, tranquila; como un analista senior que ha visto mucho baloncesto. Empieza por la conclusión. Lenguaje de baloncesto, sin jerga de modelos. Sin superlativos (nada de «el mejor», «élite», «revolucionario», «mágico», «garantizado», «desbloquear»). Respeto por el jugador. Si la nota expresa dudas, mantenlas con franqueza.

Reglas estrictas:
- Español de España. Tercera persona («proponemos», «en Kerno vemos»…).
- No inventes datos, cifras, lesiones, rasgos ni hechos que no estén en la nota o en el contexto. Puedes usar solo las cifras del contexto, tal cual.
- Entre 70 y 130 palabras, en 2 párrafos breves. Sin títulos, sin viñetas, sin comillas, sin firma.
- Devuelve solo el texto final.

Contexto del jugador (datos del informe):
${c}

Nota del analista:
${raw}`;
    btn.disabled = true; msg.textContent = "Redactando en tono Kerno… (la primera vez Claude pide permiso)";
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
  // fila de métrica: nombre + qué mide, valor en la liga de referencia (IF_POOL), percentil por posición con su franja
  function fila(k, R, pos) {
    const s = IFM[k], m = R.m[k]; if (!s || !m) return "";
    const op = ifOp(k, m[2]); let lo = m[3] != null ? ifOp(k, m[3]) : null, hi = m[4] != null ? ifOp(k, m[4]) : null; if (lo != null && hi != null && lo > hi) [lo, hi] = [hi, lo];
    const val = s.raw ? m[1] : m[0], neu = (s.dir ?? 1) === 0;
    return `<tr><td><b>${E(s.n)}</b><small>${E(s.d || "")}</small></td><td class="num">${ifV(k, val)}${!s.raw && m[1] != null && R.liga !== "euroleague" ? `<small>en su liga ${ifV(k, m[1])}</small>` : s.raw ? `<small>sin traducir</small>` : ""}</td>
      <td>${barraPR(op, lo, hi, { ref: 50, cls: neu ? "neu" : op >= 65 ? "up" : op <= 35 ? "dn" : "" })}</td><td class="num"><b class="${neu ? "" : ifTono(op)}">${op == null ? "–" : Math.round(op)}</b>${lo != null && hi != null ? `<small>${Math.round(lo)}–${Math.round(hi)}</small>` : ""}</td></tr>`;
  }
  function tablaM(keys, R, pos, titulo) {
    const filas = keys.filter((k) => R.m[k]).map((k) => fila(k, R, pos)).join("");
    return filas ? `<table class="r3t m"><thead><tr><th>${E(titulo)}</th><th class="num">Valor</th><th>Frente a los ${E(IF_POSN[pos] || "jugadores")} de ${E(IFPN())}</th><th class="num">Percentil</th></tr></thead><tbody>${filas}</tbody></table>` : "";
  }
  // v3.1 · curva de adaptación: eje ajustado a la curva, pérdida frente a 100 sombreada y cifras en el propio gráfico
  function curvaAdapt(a) {
    const c = (a && a.curva) || []; if (c.length < 2) return "";
    const W = 330, H = 138, l = 30, r = 66, t = 14, bb = 22, n = c.length - 1;
    const med = c.map((x) => 100 * x[1]), mn = Math.min(...med);
    const lo = Math.max(60, Math.floor(Math.min(mn - 2, 100 - 6) / 2) * 2), hi = 101.5;
    const X = (g) => l + (W - l - r) * g / n, Y = (v) => t + (H - t - bb) * (1 - (Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo));
    const banda = c.map((x) => `${X(x[0]).toFixed(1)},${Y(100 * x[3]).toFixed(1)}`).join(" ") + " " + c.slice().reverse().map((x) => `${X(x[0]).toFixed(1)},${Y(100 * x[2]).toFixed(1)}`).join(" ");
    const perd = `${X(0)},${Y(100)} ` + c.map((x, i) => `${X(x[0]).toFixed(1)},${Y(med[i]).toFixed(1)}`).join(" ") + ` ${X(n)},${Y(100)}`;
    const paso = hi - lo > 12 ? 4 : 2, ticks = []; for (let v = Math.ceil(lo / paso) * paso; v <= 100; v += paso) ticks.push(v);
    const grid = ticks.map((v) => `<line x1="${l}" x2="${W - r}" y1="${Y(v)}" y2="${Y(v)}" class="${v === 100 ? "rf" : "g"}"/><text x="${l - 5}" y="${Y(v) + 2.5}" class="ax" text-anchor="end">${v}</text>`).join("");
    const p50 = a.partidos_50 && a.partidos_50 <= n ? X(a.partidos_50) : null;
    const v0 = med[0], vN = med[n], dif = (v) => `${v - 100 >= 0 ? "+" : "−"}${N(Math.abs(v - 100), 1)} %`;
    return `<svg class="r3cv" viewBox="0 0 ${W} ${H}" role="img" aria-label="Curva de adaptación"><defs><clipPath id="r3cvc"><rect x="${l}" y="${t - 2}" width="${W - l - r}" height="${H - t - bb + 2}"/></clipPath></defs>${grid}
      <g clip-path="url(#r3cvc)"><polygon points="${banda}" class="bd"/><polygon points="${perd}" class="ls"/></g>
      ${p50 ? `<line x1="${p50}" x2="${p50}" y1="${t}" y2="${H - bb}" class="p5"/><text x="${p50 + 3}" y="${H - bb - 4}" class="ax">mitad del cambio</text>` : ""}
      <path d="M ${c.map((x, i) => `${X(x[0]).toFixed(1)} ${Y(med[i]).toFixed(1)}`).join(" L ")}" class="ln"/>
      <circle cx="${X(0)}" cy="${Y(v0)}" r="3" class="pt"/><text x="${X(0) + 2}" y="${Y(v0) - 5}" class="vl">${N(v0, 0)}</text>
      <circle cx="${X(n)}" cy="${Y(vN)}" r="3" class="pt"/><text x="${X(n) + 6}" y="${Y(vN) + 3}" class="vl">${N(vN, 0)} · ${dif(vN)}</text>
      <text x="${W - r + 6}" y="${Y(100) + 3}" class="ax">100 = su nivel</text>
      <text x="${l}" y="${H - 6}" class="ax">partido 1</text><text x="${W - r}" y="${H - 6}" class="ax" text-anchor="end">partido ${c.length}</text></svg>`;
  }
  // v3.3 · cómo evoluciona la adaptación según la forma de la curva (ya no se muestra: la v4.1 enseña el Landing del grupo de traspaso)
  function formaAdapt(a) {
    const c = (a && a.curva) || [], tmp = a && a.adapt_pct_temporada ? a.adapt_pct_temporada.media : null;
    if (tmp == null) return "";
    if (c.length < 2) return tmp >= 99 ? "rendiría prácticamente lo que dicen sus cifras traducidas" : "rendiría algo por debajo de sus cifras traducidas durante la temporada";
    const ini = 100 * c[0][1], fin_ = 100 * c[c.length - 1][1], dif = ini - fin_;
    if (tmp >= 99 && Math.abs(dif) < 1) return "rendiría prácticamente lo que dicen sus cifras traducidas";
    if (dif >= 1) return `arrancaría ${ini >= 100.5 ? "incluso por encima de" : "cerca de"} su nivel (${N(ini, 0)} en el primer partido) e iría bajando con los partidos hasta unos ${N(fin_, 0)}: el impulso de la llegada se diluye`;
    if (dif <= -1) return `perdería más al principio (${N(ini, 0)} en el primer partido) y lo iría recuperando con los partidos hasta unos ${N(fin_, 0)}`;
    return `perdería un poco de forma estable durante la temporada`;
  }
  // v3.1 · percentil con una sola forma en todo el informe
  const pctN = (op, lo, hi) => op == null ? "–" : `percentil ${Math.round(op)}${lo != null && hi != null ? ` [${Math.round(lo)}–${Math.round(hi)}]` : ""}`;
  // ---- grupo de referencia del informe (decisión del usuario, 04-11-2026): la liga del club de destino o, sin destino,
  // la suya. Valores traducidos a esa liga (vara.json, enVara; en su propia liga, su valor real) y percentiles frente a
  // los jugadores de su posición en esa liga (cuantiles de atlas/informe/<t>.json → ligas). Sin esos datos, la Euroliga.
  const pq21 = (q, v) => { if (!q || q.length !== 21 || v == null || !isFinite(v)) return null; if (v <= q[0]) return 0; if (v >= q[20]) return 100;
    let i = 0; while (i < 19 && q[i + 1] < v) i++; return Math.round(5 * (i + (v - q[i]) / Math.max(1e-9, q[i + 1] - q[i]))); };
  function enLigaR(R, j, liga) {
    const LG = R.ligas && R.ligas[liga]; if (!LG) { IF_POOL = "euroleague"; return R; }
    const pos = ["E", "A", "I"].includes(j.pos3) ? j.pos3 : "*", propia = liga === j.liga;
    const Q = (k, L = LG) => { const n = (L.n || {})[pos] || 0, q = L.q[pos] && L.q[pos][k]; return q && n >= 15 ? q : (L.q["*"] || {})[k] || null; };
    const tr = (k, v) => (v == null || !isFinite(v) ? null : conVara(liga, () => enVara(k, v, j)));
    const m = {};
    Object.entries(R.m).forEach(([k, a]) => {
      if (k === "L") { m.L = [a[0], null, pq21(Q("L"), a[0]), null, null]; return; }
      if (a[0] == null) { const LO = R.ligas[j.liga] || LG; m[k] = [null, a[1], pq21(Q(k, LO), a[1]), null, null]; return; }   // sin normalizar: frente a su liga
      let c;
      if (k === "ast_usg") { const A = R.m.ast_pct, U = R.m.usg_pct; c = propia ? a[1] : A && U && tr("ast_pct", A[0]) != null && tr("usg_pct", U[0]) ? tr("ast_pct", A[0]) / tr("usg_pct", U[0]) : null;
        m[k] = [c, a[1], pq21(Q(k), c), null, null]; return; }
      const t0 = tr(k, a[0]); c = propia && a[1] != null ? a[1] : t0;
      const sh = c != null && t0 != null ? c - t0 : 0, lo = a[5] != null ? tr(k, a[5]) : null, hi = a[6] != null ? tr(k, a[6]) : null;
      m[k] = [c, a[1], pq21(Q(k), c), lo != null ? pq21(Q(k), lo + sh) : null, hi != null ? pq21(Q(k), hi + sh) : null];
    });
    const ref = {}; ["E", "A", "I", "*"].forEach((p) => { ref[p] = {}; const qp = (LG.q[p] && ((LG.n || {})[p] || 0) >= 15) ? LG.q[p] : LG.q["*"] || {};
      Object.entries(qp).forEach(([k, q]) => { ref[p][k] = [q[2], q[10], q[18], (LG.n || {})[p] || 0]; }); });
    IF_POOL = liga;
    return { ...R, m, ref, pool_n: LG.n, pool_liga: liga, ritmo_liga: LG.ritmo };
  }
  const pctDe = (k, R) => { const m = R.m[k]; if (!m || m[2] == null) return null; let lo = m[3] != null ? ifOp(k, m[3]) : null, hi = m[4] != null ? ifOp(k, m[4]) : null; if (lo != null && hi != null && lo > hi) [lo, hi] = [hi, lo]; return { op: ifOp(k, m[2]), lo, hi }; };
  // cifras clave de la entradilla (secciones 04 y 05): valor en la liga de referencia + percentil con su rango
  function cifras(keys, R, pos) {
    const cs = keys.filter((k) => IFM[k] && R.m[k] && R.m[k][2] != null).slice(0, 5).map((k) => { const s = IFM[k], m = R.m[k], p = pctDe(k, R), neu = (s.dir ?? 1) === 0, val = s.raw ? m[1] : m[0];
      return `<div><span>${E(s.n)}</span><b>${ifV(k, val)}</b><em class="${neu ? "neu" : ifTono(p.op)}">${pctN(p.op)}</em><small>${p.lo != null ? `rango del percentil ${Math.round(p.lo)}–${Math.round(p.hi)}` : "sin rango"}</small></div>`; });
    return cs.length ? `<div class="r3dat">${cs.join("")}</div><p class="r3n r3datn">Valor expresado en ${E(IFPN())}; percentil frente a los ${E(IF_POSN[pos] || "jugadores")} de esa competición, con su rango al 90 %.</p>` : "";
  }
  // sinergias de pareja del fichaje con cada compañero: barras divergentes ordenadas de arriba abajo
  function svgSinergias(pares) {
    if (!pares.length) return "";
    const W = 690, fila = 27, top = 18, H = top + fila * pares.length + 6, nameW = 190, valW = 46, x0 = nameW + (W - nameW - valW) / 2, half = (W - nameW - valW) / 2 - 8;
    const m = Math.max(15, ...pares.map((p) => Math.abs(p.S))), X = (v) => x0 + half * v / m;
    const rows = pares.map((p, i) => { const y = top + i * fila, w = Math.abs(X(p.S) - x0);
      return `<g><text x="0" y="${y + 14}" class="nm">${E(p.nom)}</text>${p.sw ? `<circle cx="${nameW - 12}" cy="${y + 10.5}" r="3.6" fill="${p.sw}"/>` : ""}
        <rect x="${p.S >= 0 ? x0 : x0 - w}" y="${y + 5}" width="${Math.max(1, w)}" height="${fila - 11}" class="${p.S >= 0 ? "up" : "dn"}"/>
        <text x="${W}" y="${y + 14}" class="vv ${p.S >= 0 ? "up" : "dn"}" text-anchor="end">${ESC.txt(p.S)}</text></g>`; }).join("");
    return `<svg class="r3sy" viewBox="0 0 ${W} ${H}" role="img" aria-label="Sinergia de pareja con cada compañero">
      <text x="${x0 - 6}" y="10" class="ax" text-anchor="end">‹ resta</text><text x="${x0 + 6}" y="10" class="ax">suma ›</text>
      <line x1="${x0}" x2="${x0}" y1="${top - 2}" y2="${H - 4}" class="z"/>${rows}</svg>`;
  }
  // minutos de cada jugador sin y con el fichaje (pesas: gris = sin él; negro = con él)
  function svgMinutos(filas, gm) {
    if (!filas.length) return "";
    const W = 420, fila = 21, top = 16, H = top + fila * filas.length + 18, nameW = 128, valW = 64, X = (m) => nameW + (W - nameW - valW) * Math.min(1, m / gm);
    const ticks = [0, 10, 20, 30, 40].filter((v) => v <= gm).map((v) => `<line x1="${X(v)}" x2="${X(v)}" y1="${top - 4}" y2="${H - 16}" class="g"/><text x="${X(v)}" y="${H - 5}" class="ax" text-anchor="middle">${v}'</text>`).join("");
    const rows = filas.map((f, i) => { const y = top + i * fila + 8, a = f.sin, b = f.con, d = a == null ? null : b - a;
      return `<g${f.yo ? ` class="yo"` : ""}>${f.yo ? `<rect x="0" y="${y - 8}" width="${W}" height="${fila}" class="hlr"/>` : ""}<text x="0" y="${y + 3}" class="nm">${E(f.nom)}</text>
        ${a != null ? `<line x1="${X(a)}" x2="${X(b)}" y1="${y}" y2="${y}" class="cn"/><circle cx="${X(a)}" cy="${y}" r="3" class="s0"/>` : ""}<circle cx="${X(b)}" cy="${y}" r="3.4" class="s1"/>
        <text x="${W}" y="${y + 3}" class="vv${d != null && d < -0.5 ? " dn" : ""}" text-anchor="end">${a != null ? `${N(a, 0)}' a ${N(b, 0)}'` : `${N(b, 0)}' nuevo`}</text></g>`; }).join("");
    return `<svg class="r3mn" viewBox="0 0 ${W} ${H}" role="img" aria-label="Minutos por partido sin y con el fichaje">${ticks}${rows}</svg>`;
  }
  // v2.0 · «Cómo cambian los números de sus compañeros» (sustituye a la tabla): por compañero, su peso en el ataque
  // (jugadas del equipo que acaba por partido = USG% × minutos / duración), el nivel de su entorno y el cambio de cada
  // métrica individual como barra divergente; barra completa = cambio de referencia de la columna (más allá, se corta).
  const REF6 = { usg_pct: 2, pts_p100: 3, efg_pct: 2, ast_pct: 3, tov_pct: 2, oreb_pct: 2, dreb_pct: 3, pct_asistidas: 5 };
  function datos6(c6, j, gm) {
    const sh = (u, m) => (u == null || m == null || !isFinite(u) || !isFinite(m)) ? null : u * m / gm;
    const filas = c6.imp.slice(0, 8).map((x) => { const u = x.di && x.di.usg_pct, uCon = u ? u.y : null, uSin = u ? u.y - u.v : null;
      return { x, nom: nom(x.o.j.nombre), sin: sh(uSin, x.o.p.minutos_sin), con: sh(uCon, x.o.p.minutos), ent: ESC.dS("nivel", x.ddev) }; });
    let yo = null; try { const o = c6.yo && c6.yo.out && c6.yo.out.usg_pct; if (o && o.y != null && c6.fich) yo = sh(enVara("usg_pct", o.y, j), c6.fich.minutos); } catch (e) { yo = null; }
    return { filas, yo };
  }
  // A · de dónde sale su balón: barras divergentes en un mismo eje (él suma; cada compañero cede; total cedido)
  function svgBalon(D, apeJ) {
    const F = D.filas.filter((f) => f.sin != null && f.con != null).map((f) => ({ ...f, d: f.con - f.sin })); if (!F.length) return "";
    const tot = F.reduce((s, f) => s + f.d, 0), yo = D.yo != null ? D.yo : 0;
    const W = 690, fila = 23, top = 20, n = F.length + (D.yo != null ? 1 : 0) + 1, H = top + fila * n + 10, nameW = 150, labW = 132;
    const neg = Math.max(2, -tot, ...F.map((f) => -f.d)), pos = Math.max(2, yo), span = W - nameW - labW - 16, x0 = nameW + span * neg / (neg + pos), k = span / (neg + pos), X = (v) => x0 + v * k;
    let y = top, out = "";
    const fila_ = (nm, v, cls, lab, extra) => { const cy = y + fila / 2, w = Math.max(1, Math.abs(X(v) - x0)); const r = `<g>${extra || ""}<text x="0" y="${cy + 3.5}" class="nm${cls === "yo" || cls === "tt" ? " b" : ""}">${nm}</text>
      <rect x="${v >= 0 ? x0 : x0 - w}" y="${cy - 6}" width="${w}" height="12" class="${cls}"/>${cls !== "yo" ? `<text x="${v >= 0 ? x0 + w + 4 : x0 - w - 4}" y="${cy + 3}" class="vv${cls === "dn" || cls === "tt" ? " dn" : ""}" text-anchor="${v >= 0 ? "start" : "end"}">${SG0(v, 1)}</text>` : ""}
      <text x="${W}" y="${cy + 3}" class="vl" text-anchor="end">${lab}</text></g>`; y += fila; return r; };
    if (D.yo != null) out += fila_(`${E(apeJ)} · llega`, yo, "yo", `<tspan class="b">${N(yo, 1)} %</tspan> de las jugadas`, `<rect x="0" y="${y}" width="${W}" height="${fila}" class="hlr"/>`);
    F.sort((p, q) => p.d - q.d).forEach((f) => { out += fila_(E(f.nom), f.d, f.d <= -0.05 ? "dn" : f.d >= 0.05 ? "up" : "eq", `${N(f.sin, 1)} % a ${N(f.con, 1)} %`); });
    out += `<line x1="0" x2="${W}" y1="${y + 1}" y2="${y + 1}" class="hl"/>`; y += 3;
    out += fila_(`Cedido entre los ${F.length}`, tot, "tt", D.yo != null && yo > 0 ? `${N(Math.min(100, 100 * -tot / yo), 0)} % de lo que él asume` : "");
    return `<svg class="r3im" viewBox="0 0 ${W} ${H + 3}" role="img" aria-label="De dónde sale su balón">
      <text x="${x0 - 6}" y="10" class="ax" text-anchor="end">‹ cede balón</text><text x="${x0 + 6}" y="10" class="ax">asume balón ›</text>
      <line x1="${x0}" x2="${x0}" y1="${top - 2}" y2="${H - 4}" class="z0"/>${out}</svg>`;
  }
  // B · cómo cambia el juego de cada compañero: entorno + métricas, barra divergente sobre un carril de ± referencia
  function svgJuego(D) {
    const F = D.filas; if (!F.length) return "";
    const W = 690, top = 34, fila = 27, H = top + fila * F.length + 4, nameW = 128, eX = nameW + 6, eW = 64, mX = eX + eW + 14, cw = (W - mX) / CTX6I.length, hw = cw / 2 - 6;
    const mxE = Math.max(5, ...F.map((f) => Math.abs(f.ent || 0)));
    const cls = (k, o) => { const dec = k === "pct_asistidas" ? 0 : 1, tol = dec ? 0.05 : 0.5, sen = o.m ? o.m.sentido : 1; return Math.abs(o.v) < tol ? "eq" : sen === 0 ? "neu" : o.v * sen > 0 ? "up" : "dn"; };
    const head = `<text x="0" y="${top - 9}" class="hd">Compañero</text><text x="${eX}" y="${top - 18}" class="hd">Entorno</text><text x="${eX}" y="${top - 9}" class="rf">puntos 0–100</text>
      ${CTX6I.map(([, k, nm], i) => { const cx = mX + cw * (i + 0.5); return `<text x="${cx}" y="${top - 18}" class="hd" text-anchor="middle">${E(nm)}</text><text x="${cx}" y="${top - 9}" class="rf" text-anchor="middle">carril ±${REF6[k]}</text>`; }).join("")}
      <line x1="0" x2="${W}" y1="${top - 3}" y2="${top - 3}" class="hl"/>`;
    const rows = F.map((f, r) => { const y = top + r * fila, cy = y + 10, x = f.x;
      const ent = f.ent != null && isFinite(f.ent) ? (() => { const w = Math.max(1, eW * Math.min(1, Math.abs(f.ent) / mxE)); return `<rect x="${eX}" y="${cy - 4}" width="${eW}" height="8" class="tr"/><rect x="${f.ent >= 0 ? eX : eX + eW - w}" y="${cy - 4}" width="${w}" height="8" class="${f.ent >= 0.5 ? "up" : f.ent <= -0.5 ? "dn" : "eq"}"/><text x="${eX}" y="${cy + 13}" class="vs">${SG0(f.ent / 2, 0)}</text>`; })() : "";
      const met = CTX6I.map(([, k, , dec], i) => { const o = x.di && x.di[k], cx = mX + cw * (i + 0.5); if (!o) return `<text x="${cx}" y="${cy + 3}" class="vs na" text-anchor="middle">–</text>`;
        const c = cls(k, o), w = c === "eq" ? 0 : Math.max(1.5, hw * Math.min(1, Math.abs(o.v) / REF6[k])), cut = Math.abs(o.v) > REF6[k];
        return `<rect x="${cx - hw}" y="${cy - 4}" width="${2 * hw}" height="8" class="tr"/><line x1="${cx}" x2="${cx}" y1="${cy - 6}" y2="${cy + 6}" class="z"/>${w ? `<rect x="${o.v >= 0 ? cx : cx - w}" y="${cy - 4}" width="${w}" height="8" class="${c}"/>` : ""}${cut ? `<text x="${o.v >= 0 ? cx + hw + 3 : cx - hw - 3}" y="${cy + 3}" class="vs ${c}" text-anchor="middle">›</text>` : ""}<text x="${cx}" y="${cy + 13}" class="vs ${c}" text-anchor="middle">${SG0(o.v, dec)}</text>`; }).join("");
      return `<g><text x="0" y="${cy + 3.5}" class="nm">${E(f.nom)}</text>${ent}${met}<line x1="0" x2="${W}" y1="${y + fila - 1}" y2="${y + fila - 1}" class="sep"/></g>`; }).join("");
    return `<svg class="r3im" viewBox="0 0 ${W} ${H}" role="img" aria-label="Cómo cambia el juego de cada compañero">${head}${rows}</svg>`;
  }
  function lectura6(D, apeJ) {
    const F = D.filas.filter((f) => f.sin != null && f.con != null); if (!F.length) return "";
    const ced = F.map((f) => ({ f, d: f.con - f.sin })).sort((a, b) => a.d - b.d), tot = -ced.reduce((s, o) => s + o.d, 0), top2 = ced.filter((o) => o.d <= -0.1).slice(0, 2);
    let mx = null; D.filas.forEach((f) => CTX6I.forEach(([, k, nm, dec]) => { const o = f.x.di && f.x.di[k]; if (!o) return; const r = Math.abs(o.v) / REF6[k]; if (!mx || r > mx.r) mx = { r, f, nm, o, dec }; }));
    const ent = D.filas.map((f) => f.ent).filter((v) => v != null && isFinite(v)), entM = ent.length ? ent.reduce((a, b) => a + b, 0) / ent.length : null;
    const t = [];
    if (D.yo != null) t.push(`${E(apeJ)} acabaría el <b>${N(D.yo, 1)} %</b> de las jugadas del equipo por partido.`);
    t.push(tot >= 0.1 ? `Sus ocho compañeros con más minutos ceden ${N(tot, 1)} puntos de ese reparto${top2.length ? `, sobre todo ${yLista(top2.map((o) => `${E(o.f.nom.split(" ").slice(-1)[0])} (${SG0(o.d, 1)})`))}` : ""}: es el cambio real, menos minutos y menos balón.` : "Apenas resta balón a sus compañeros con más minutos.");
    if (entM != null && Math.abs(entM) >= 1) t.push(`Juegan rodeados de ${entM > 0 ? "más" : "menos"} nivel (${SG0(entM, 0)} de media en la escala 0–100).`);
    if (mx) t.push(mx.r < 0.5 ? `Su forma de jugar apenas cambia: el mayor movimiento es ${E(mx.nm)} de ${E(mx.f.nom.split(" ").slice(-1)[0])} (${SG0(mx.o.v, mx.dec)}), lejos de la referencia de la columna.` : `El cambio de papel más claro: ${E(mx.nm)} de ${E(mx.f.nom.split(" ").slice(-1)[0])} (${SG0(mx.o.v, mx.dec)}).`);
    return t.join(" ");
  }
  // composición de estilos de la plantilla (barras apiladas, una por escenario)
  function barrasEstilo(filas) {
    const eus = EUS(); if (!filas.length || !eus.length) return "";
    return `<div class="r3eb">${filas.map(([lab, v, yo]) => { const s = v.reduce((a, x) => a + (x || 0), 0) || 1;
      return `<div class="${yo ? "yo" : ""}"><span>${E(lab)}</span><p>${v.map((x, k) => { const w = 100 * (x || 0) / s; return w < 0.5 ? "" : `<i style="width:${w.toFixed(2)}%;background:${eus[k].color}">${w >= 9 ? Math.round(w) : ""}</i>`; }).join("")}</p></div>`; }).join("")}
      <div class="r3ebl">${eus.map((e) => `<span><i style="background:${e.color}"></i>${E(e.nombre)}</span>`).join("")}</div></div>`;
  }
  // quinteto más probable con él: aporte de cada jugador (RAPM-EL) + química de las 10 parejas = Net previsto
  function svgQuinteto(q, sel, yo) {
    const items = sel.map((x) => ({ lab: ape(x.j.nombre), v: rapmOk(x.j) ? x.j.rapm_el : 0, yo: x.j === yo, falta: !rapmOk(x.j) })).concat([{ lab: "Química (10 parejas)", v: q.quim, q: true }]);
    const W = 330, fila = 23, top = 6, H = top + fila * (items.length + 1) + 18, nameW = 118, valW = 40, vals = []; let run = 0;
    items.forEach((it) => { it.a = run; it.b = run + it.v; run = it.b; vals.push(it.a, it.b); }); vals.push(0, q.total);
    const mn = Math.min(...vals), mx = Math.max(...vals), pad = Math.max(0.5, (mx - mn) * 0.08), X = (v) => nameW + (W - nameW - valW) * (v - (mn - pad)) / ((mx + pad) - (mn - pad));
    const rows = items.map((it, i) => { const y = top + i * fila; return `<g>${it.yo ? `<rect x="0" y="${y}" width="${W}" height="${fila}" class="hlr"/>` : ""}<text x="0" y="${y + 13}" class="nm${it.q ? " q" : ""}">${E(it.lab)}${it.falta ? " *" : ""}</text>
      <rect x="${Math.min(X(it.a), X(it.b))}" y="${y + 4}" width="${Math.max(1, Math.abs(X(it.b) - X(it.a)))}" height="${fila - 8}" class="${it.v >= 0 ? "up" : "dn"}"/><text x="${W}" y="${y + 13}" class="vv" text-anchor="end">${SG(it.v, 1)}</text></g>`; }).join("");
    const yT = top + items.length * fila;
    return `<svg class="r3q5" viewBox="0 0 ${W} ${H}" role="img" aria-label="Net previsto del quinteto"><line x1="${X(0)}" x2="${X(0)}" y1="${top}" y2="${yT + fila}" class="z"/>${rows}
      <g><text x="0" y="${yT + 14}" class="nm t">Net previsto</text><rect x="${Math.min(X(0), X(q.total))}" y="${yT + 3}" width="${Math.max(1, Math.abs(X(q.total) - X(0)))}" height="${fila - 6}" class="tt"/><text x="${W}" y="${yT + 14}" class="vv t" text-anchor="end">${SG(q.total, 1)}</text></g>
      <text x="${X(0)}" y="${H - 4}" class="ax" text-anchor="middle">0 = quinteto medio de ${E(VN())} · pts/100</text></svg>`;
  }

  // ------------------------------------------------------------------------------------------- 4. textos de lectura
  const ART = { impacto: "el impacto en pista", anotacion: "la anotación", creacion: "la creación de juego", rebote: "el rebote", defensa: "la defensa" };
  const CONFK = (k) => { const s = window.KernoV41 && KernoV41.listo() && KernoV41.datos.prod.sellos[k]; return s ? ` · confianza ${s.confianza_es}` : ""; };
  function lgI0(s2) { const g = window.KernoV41 && KernoV41.listo() && s2 ? KernoV41.landing(s2.grupo_nacionalidad) : null; return g ? `${g.pct} %` : ""; }
  function confianza(r, R) {
    if (!r) { const n = R && R.b ? R.b.min : null; return n == null ? "baja" : n >= 1200 ? "moderada" : n >= 500 ? "moderada" : "baja"; }
    const av = (r.avisos || []).map((x) => x.tipo), grave = av.filter((t) => ["incertidumbre_alta", "liga_lejana", "muestra_pequena"].includes(t)).length;
    return av.length === 0 ? "alta" : grave >= 2 || av.length >= 3 ? "baja" : "moderada";
  }
  const AVISO_TXT = { muestra_pequena: "Su muestra en origen es corta: pocas noches para fiarse del todo de sus cifras.", liga_lejana: "El salto de nivel entre ligas es grande: la traducción tiene más margen de lo habitual.", incertidumbre_alta: "Su nivel traducido tiene un margen amplio.", cambio_rol: "El rol que le das es muy distinto del que tiene ahora: es el supuesto que más mueve la lectura.", volatilidad_alta: "Es irregular partido a partido: noches muy buenas y otras discretas.", adaptacion_generica: "Hay poca historia de jugadores con este mismo cambio de liga y país." };
  function rasgos(R) { return ifRasgos(R); }
  const etiqueta = (p) => { const L = IFPN(); return p == null ? `sin referencia en ${L}` : p >= 85 ? `en la franja alta de su puesto en ${L}` : p >= 60 ? `con nivel de titular en ${L}` : p >= 35 ? `con nivel de rotación en ${L}` : p >= 15 ? `con nivel de fondo de armario en ${L}` : `por debajo del nivel habitual de ${L}`; };

  // ------------------------------------------------------------------------------------------- 5. páginas
  const IDX_SEC = [];
  function hoja(cuerpo, o) {
    if (o.portada) return `<article class="ifsheet r3 cover${o.back ? " back" : ""}"><div class="ifbody">${cuerpo}</div></article>`;
    return `<article class="ifsheet r3${o.cls ? " " + o.cls : ""}"><header class="r3head"><span class="r3label">KERNO ANALYTICS — LECTURA DE FICHAJE · CONFIDENCIAL</span><span class="r3label">${E(o.extra || "")}</span><span class="r3hsec r3label">${String(o.num).padStart(2, "0")} · ${E(o.sec.toUpperCase())}</span></header>
      <div class="ifbody r3body">${cuerpo}</div><footer class="r3foot">${ifEscala(o.n, o.N)}<span>${E(o.fecha)}</span><span>${String(o.n).padStart(2, "0")} / ${String(o.N).padStart(2, "0")}</span></footer></article>`;
  }
  const ceja = (num, nombre, h2, lead) => `<div class="r3secw"><div class="r3sec ink"><div><span class="r3ceja">Sección ${String(num).padStart(2, "0")} · ${E(nombre)}</span><h2>${h2}</h2></div><b class="r3num">${String(num).padStart(2, "0")}</b></div>${lead ? `<p class="r3lead">${lead}</p>` : ""}</div>`;

  function evolucion(tray, j) {
    const por = new Map(); tray.forEach((x) => { const o = por.get(x.temporada); if (!o || x.min > o.min) por.set(x.temporada, x); });
    const T = [...por.keys()].sort(); if (T.length < 2) return `<p class="r3n">Solo hay una temporada suya en los datos.</p>`;
    const W = 330, H = 150, l = 30, r = 12, t = 16, bb = 30, xs = (i) => l + (W - l - r) * i / (T.length - 1), ys = (v) => t + (H - t - bb) * (1 - (v + 100) / 200);
    const Nv = T.map((t_) => sNivJ(por.get(t_))), Rr = T.map((t_) => { const x = por.get(t_); return rapmOk(x) ? ESC.S("rapm", x.rapm_el, x.temporada) : null; });
    const lin = (v, cl) => { const p = v.map((y, i) => y == null ? null : [xs(i), ys(y)]).filter(Boolean); return p.length > 1 ? `<path d="M ${p.map((q) => q.join(" ")).join(" L ")}" class="${cl}"/>` : ""; };
    const grid = [-50, 0, 50].map((v) => `<line x1="${l}" x2="${W - r}" y1="${ys(v)}" y2="${ys(v)}" class="${v === 0 ? "z" : "g"}"/><text x="${l - 5}" y="${ys(v) + 3}" class="ax" text-anchor="end">${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v)}</text>`).join("");
    const pts = Nv.map((v, i) => v == null ? "" : `<circle cx="${xs(i)}" cy="${ys(v)}" r="${T[i] === j.temporada ? 3.6 : 2.4}" class="pn"/><text x="${xs(i)}" y="${ys(v) - 7}" class="pv" text-anchor="middle">${ESC.txt(v)}</text>`).join("");
    const lab = T.map((t_, i) => `<text x="${xs(i)}" y="${H - 14}" class="ax" text-anchor="middle">${t_.slice(2)}</text><text x="${xs(i)}" y="${H - 5}" class="ax" text-anchor="middle">${E(LC[por.get(t_).liga] || "")}</text>`).join("");
    return `<svg class="r3ev" viewBox="0 0 ${W} ${H}" role="img" aria-label="Evolución de su nivel">${grid}${lin(Rr, "lr")}${lin(Nv, "ln")}${pts}${lab}</svg><p class="r3n">Línea continua: nivel Kerno; discontinua: RAPM proyectado. Escala 0–100, una temporada por punto (su equipo con más minutos).</p>`;
  }
  function ligasVara(j, d) {
    const t = META.temporadas_provisionales.includes(j.temporada) ? ultCompleta() : j.temporada;
    const L = ESC.ligasNivel(t).filter((o) => o.S != null).sort((a, b) => b.S - a.S); if (!L.length) return "";
    const m = Math.max(60, ...L.map((o) => Math.abs(o.S))), W = 160;
    return `<div class="r3blk"><h3>Normalización entre ligas: cuánto vale cada competición</h3><div class="r3lig" style="grid-template-rows:repeat(${Math.ceil(L.length / 2)},auto)">${L.map((o) => { const w = Math.abs(o.S) / m * (W / 2), x = o.S >= 0 ? W / 2 : W / 2 - w, sel = o.l === j.liga || (d && o.l === d.liga);
      return `<div class="${sel ? "sel" : ""}"><span>${E(ESC.ligaNom(o.l))}</span><svg viewBox="0 0 ${W} 10" width="${W}" height="10"><line x1="${W / 2}" x2="${W / 2}" y1="0" y2="10" class="z"/><rect x="${x}" y="2" width="${Math.max(1, w)}" height="6" class="${sel ? "on" : ""}"/></svg><b>${ESC.txt(o.S)}</b></div>`; }).join("")}</div>
      <p class="r3n">Nivel medio de los jugadores de cada liga en ${E(t)}, escala 0–100 (comparación entre ligas: Euroliga = 50). Es la regla con la que se traducen sus cifras: un 15 en una liga más exigente vale más que un 15 en una menos exigente. De más a menos exigente, columna a columna. En negrita, su liga${d && d.liga !== j.liga ? " y la del club de destino" : ""}.</p></div>`;
  }
  function lecturaAtaque(R) {
    const p = (k) => R.m[k] && R.m[k][2] != null ? ifOp(k, R.m[k][2]) : null, u = p("usg_pct"), ts = p("ts_pct"), a = p("ast_pct"), tv = p("tov_pct"), t3 = p("fg3_pct"), r3 = p("fg3a_rate"), fr = p("fta_rate"), out = [];
    if (u != null && ts != null) out.push(u >= 65 ? (ts >= 55 ? "Asume mucho volumen de ataque y lo hace con eficiencia: el perfil de jugador al que se le puede dar el balón en los finales." : ts <= 35 ? "Asume mucho volumen, pero con poca eficiencia: necesita un sistema que le dé tiros mejores o menos responsabilidad." : "Asume mucho volumen con una eficiencia en la media de su puesto.") : u <= 35 ? (ts >= 55 ? "Toca poco el balón pero aprovecha lo que le llega: buen complemento junto a creadores." : "Tiene un papel secundario en el ataque.") : (ts >= 65 ? "Con un uso medio del balón, anota con eficiencia alta." : "Uso del balón y eficiencia en la zona media de su puesto."));
    if (a != null && a >= 70) out.push(tv != null && tv <= 35 ? "Genera juego para los demás, aunque con más pérdidas de las deseables." : "Genera juego para los demás y cuida el balón.");
    if (r3 != null && t3 != null) out.push(r3 >= 60 ? (t3 >= 55 ? "El triple es un arma real: tira mucho y con buen acierto." : "Tira muchos triples sin un acierto que lo respalde.") : t3 >= 70 ? "Acierta de tres por encima de su puesto aunque tire poco: hay margen para darle más tiros." : "");
    if (fr != null && fr >= 75) out.push("Pisa la línea de tiros libres con frecuencia: castiga los cierres tardíos y carga de faltas al rival.");
    return out.filter(Boolean).join(" ");
  }
  // ------------------------------------------------------------------------------------------- anclas v4.0 (hoja, gauge y textos)
  const nivelTxt = (v) => v == null || !isFinite(v) ? "sin referencia" : v >= 80 ? "producción de referente en su puesto" : v >= 60 ? "producción de titular" : v >= 40 ? "producción de rotación" : v >= 20 ? "producción de fondo de banquillo" : "producción por debajo de lo habitual";
  const impTxt = (v) => v == null || !isFinite(v) ? "sin referencia" : v >= 62 ? "mejora al equipo con claridad" : v >= 54 ? "mejora algo al equipo" : v >= 46 ? "no cambia al equipo" : v >= 38 ? "empeora algo al equipo" : "empeora al equipo con claridad";
  function gaugeAncla(v, lo, hi, o = {}) {
    const W = o.w || 300, H = 30, X = (x) => 6 + (W - 12) * Math.max(0, Math.min(1, x / 100));
    const ticks = [0, 25, 50, 75, 100].map((k) => `<line x1="${X(k)}" x2="${X(k)}" y1="${k % 50 === 0 ? 6 : 10}" y2="${H - 10}" class="tk"/><text x="${X(k)}" y="${H - 1}" text-anchor="middle" class="tx">${k}</text>`).join("");
    if (v == null || !isFinite(v)) return `<svg class="r3g" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" aria-hidden="true"><line x1="6" x2="${W - 6}" y1="${H / 2 - 2}" y2="${H / 2 - 2}" class="tr"/>${ticks}</svg>`;
    return `<svg class="r3g" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${E(o.aria || "")}"><line x1="6" x2="${W - 6}" y1="${H / 2 - 2}" y2="${H / 2 - 2}" class="tr"/>${ticks}${lo != null && hi != null ? `<rect x="${X(lo)}" y="${H / 2 - 8}" width="${Math.max(2, X(hi) - X(lo))}" height="12" class="bd"/>` : ""}<line x1="${X(v)}" x2="${X(v)}" y1="${H / 2 - 11}" y2="${H / 2 + 7}" class="pt"/></svg>`;
  }
  function hojaAnclas(o) {
    const { j, pos, an, anEsc, anCtx, apeJ, ligaAnc, clubAnc, d, rolA, s2 } = o, propio = anCtx && anCtx.propio, im = isFinite(an.IM);
    const gm = an.liga === "nba" || an.liga === "gleague" ? 48 : 40, minMed = anCtx && anCtx.res && anCtx.res.minutos ? anCtx.res.minutos.mediana : (s2 && s2.minutos ? s2.minutos.mediana : null);
    const lead = propio ? `${E(apeJ)} en ${E(clubAnc)}, con su plantilla y su rol de ${E(ROLN[rolA].toLowerCase())}: Nivel Kerno <b>${Math.round(an.NC)}</b> (${E(nivelTxt(an.NC))})${im ? ` e Impacto <b>${Math.round(an.IM)}</b> (${E(impTxt(an.IM))})` : ""}.`
      : `Como ${E(ROLN[rolA].toLowerCase())} de ${E(clubAnc)}, ${E(apeJ)} tendría Nivel Kerno <b>${Math.round(an.NC)}</b> (${E(nivelTxt(an.NC))})${im ? ` e Impacto <b>${Math.round(an.IM)}</b> (${E(impTxt(an.IM))})` : ""}.`;
    const fila = (k, v) => `<div><dt>${k}</dt><dd>${v}</dd></div>`;
    const cNC = `<div class="r3ancla"><span class="r3lab">Nivel Kerno · producción esperada</span><div class="num"><b>${Math.round(an.NC)}</b><small>${E(nivelTxt(an.NC))}${CONFK("nivel_kerno")}</small></div>${gaugeAncla(an.NC, an.NC_lo80, an.NC_hi80, { aria: "Nivel Kerno" })}
      <dl class="r3anckv">${fila("Producción esperada", `${N(an.C ? an.C.mediana : null, 1)} puntos por partido <small>(${minMed != null ? N(minMed, 0) : "–"}' × ${s2 && s2.produccion_p100 && s2.produccion_p100.pts_p100 ? N(s2.produccion_p100.pts_p100.mediana, 1) : (anCtx && anCtx.res ? N(anCtx.res.produccion_p100.pts_p100.mediana, 1) : "–")} pts/100)</small>`)}
        ${fila("Frente a", `${an.n_ref ? N(an.n_ref, 0) : "–"} ${E(IF_POSN[an.pos || pos] || "jugadores")} de ${E(ligaAnc)} <small>(tres últimas temporadas, ponderados por minutos)</small>`)}
        ${fila("Lectura", `${E(nivelTxt(an.NC).charAt(0).toUpperCase() + nivelTxt(an.NC).slice(1))}. La cifra es la lectura; la banda, dónde puede moverse.`)}</dl></div>`;
    const cIM = `<div class="r3ancla"><span class="r3lab">Impacto · lo que cambia el equipo</span><div class="num"><b>${im ? Math.round(an.IM) : "–"}</b><small>${im ? `${E(impTxt(an.IM))}${CONFK("impacto")}` : "sin plantilla suficiente"}</small></div>${gaugeAncla(im ? an.IM : null, im ? an.IM_lo80 : null, im ? an.IM_hi80 : null, { aria: "Impacto" })}
      <dl class="r3anckv">${fila("Net del equipo con él", im ? `<b class="${an.delta_net > 0.5 ? "up" : an.delta_net < -0.5 ? "dn" : ""}">${SG0(an.delta_net, 1)}</b> por 100 posesiones <small>con él frente a sin él${CONFK("net_equipo")}</small>` : "sin plantilla suficiente para simular")}
        ${fila("RAPM proyectado", `${ESC.txt(ESC.S("rapm", an.beta))} <small>(escala 0–100; beta ${SG0(an.beta, 1)} pts/100 en la escala común a las 20 ligas${an.fuente_beta === "prior" ? ", estimado por su perfil" : an.fuente_beta === "nuevo" ? ", nivel medio de los recién llegados" : ""}) · plantilla con él ${N(an.T_con, 1)}, sin él ${N(an.T_sin, 1)}</small>`)}
        ${fila("Frente a", im ? `${N(an.n_mov, 0)} fichajes reales de ligas ${E({ elite: "de élite (EuroLeague y NBA)", domestica_alta: "domésticas de primer nivel", resto: "del resto de competiciones" }[an.grupo_im] || an.grupo_im)}` : "–")}</dl></div>`;
    const filasRol = anEsc.filter((x) => x && x.a && isFinite(x.a.NC)).map((x) => `<tr class="${x.rol === rolA ? "yo" : ""}"><td>${rolChip(x.rol)}${x.rol === rolA ? ` <small>elegido</small>` : ""}</td><td class="num">${N(x.r.minutos.media, 0)}'</td><td class="num"><b>${Math.round(x.a.NC)}</b></td><td class="num"><b>${isFinite(x.a.IM) ? Math.round(x.a.IM) : "–"}</b></td><td class="num">${isFinite(x.a.delta_net) ? SG0(x.a.delta_net, 1) : "–"}</td></tr>`).join("");
    const tablaRol = filasRol ? `<div class="r3blk"><h3>Si cambias su rol</h3><table class="r3t esc"><thead><tr><th>Rol en ${E(clubAnc)}</th><th class="num">Minutos</th><th class="num">Nivel Kerno</th><th class="num">Impacto</th><th class="num">Net del equipo</th></tr></thead><tbody>${filasRol}</tbody></table><p class="r3n">Cada fila es la misma simulación con otro rol asignado: más minutos suben la producción esperada (Nivel Kerno) pero no necesariamente el Impacto, que depende de a quién quita esos minutos.</p></div>` : "";
    const como = `<div class="r3cols c2"><div class="r3blk"><h3>De dónde sale el Nivel Kerno</h3><p class="r3p">Se simula su temporada en ${E(clubAnc)} con el rol asignado y se calcula cuánto produce por partido. La nota es el percentil que ocupa esa producción entre los ${E(IF_POSN[an.pos || pos] || "jugadores")} de ${E(ligaAnc)}, ajustado con 5.500 fichajes reales.</p></div>
      <div class="r3blk"><h3>De dónde sale el Impacto</h3><p class="r3p">Se compara la plantilla con él y sin él: valor de cada jugador en una escala común a las 20 ligas, parejas y minutos. La diferencia de puntos se sitúa entre los fichajes reales de su grupo de ligas: 50 es un fichaje que no mueve al equipo.</p></div></div>`;
    const nota = `<p class="r3n">Los minutos salen del motor del Atlas con el rol asignado; el modelo de equipo v4.0 se examinó con el motor de Kerno en servidor (misma valoración de jugadores, parejas y calibración).${propio ? " Sin club de destino, las anclas describen su papel en su club actual, con su propia plantilla." : ""}</p>`;
    return `${ceja(2, "El jugador", "Nivel Kerno e Impacto: las dos anclas", lead)}<div class="r3anc">${cNC}${cIM}</div>${tablaRol}${como}${nota}`;
  }

  function paginas(c) {
    const { j, R, pos, sim, s2, nec, fecha, tray, medias, nota } = c, b = R.b || {}, club = BY.get(j.clave), d = sim && !sim.mismo ? sim.d : null;
    const an = c.an && isFinite(c.an.NC) ? c.an : null, anEsc = c.anEsc || [], anCtx = c.anCtx || null, anIM = an && isFinite(an.IM);
    const ligaAnc = anCtx && anCtx.club ? ESC.ligaNom(anCtx.club.liga) : IFPL(), clubAnc = anCtx && anCtx.club ? anCtx.club.nombre : (d ? d.nombre_club : (club ? club.nombre_club : j.nombre_club));
    const P = R.ref[pos] || R.ref["*"], pL = R.m.L ? R.m.L[2] : null, Snv = sNivJ(j), sr = rapmOk(j) ? ESC.S("rapm", j.rapm_el, j.temporada) : null;
    const rolA = c.rol, rolO = rolDeRec(simRec(j)) || rolEstimado(j, b), rolOest = !rolDeRec(simRec(j));
    const bloques = IFB.map((bk) => ({ bk, sc: ifPuntBloque(bk, R) })).filter((o) => o.sc != null);
    const mejorB = bloques.slice().sort((a, x) => x.sc - a.sc)[0], peorB = bloques.slice().sort((a, x) => a.sc - x.sc)[0];
    const conf = confianza(s2, R), fitS = s2 && s2.fit && s2.fit.total != null ? ESC.dS("z", s2.fit.total) : null;
    const nomJ = nom(j.nombre), apeJ = ape(j.nombre), clubN = club ? club.nombre_club : j.nombre_club;
    const ref = `READ ${new Date().toISOString().slice(2, 10).replace(/-/g, "")}-${(nomJ.match(/\p{L}+/gu) || ["X"]).map((w) => w[0]).join("").slice(0, 3).toUpperCase()}`;
    const extra = (d ? `${ref} · ${d.nombre_club}` : `${ref} · Dirección deportiva`).toUpperCase().slice(0, 46);
    const pags = [];
    const nac = c.nac || pais((simRec(j) || {}).nac) || "–", posA = String(b.posicion || "").replace(/_/g, " ").toLowerCase(), posB = IF_POS1[j.pos3] || "";
    const ficha = [["Nacionalidad", nac], ["Edad", j.edad != null ? `${Math.round(j.edad)} años` : "–"], ["Altura", b.altura_cm ? `${N(b.altura_cm / 100, 2)} m` : "–"], ["Posición", `${posB ? posB.charAt(0).toUpperCase() + posB.slice(1) : "s/d"}${posA && posA !== posB ? ` · ${posA}` : ""}`]].filter(([, v]) => v !== "–");

    // 0 · portada
    pags.push({ portada: true, html: `<img class="cvestela" src="${INF_LOGO.est}" alt="" aria-hidden="true"><div class="cvtop"><img src="${INF_LOGO.hn}" alt="KERNO Analytics" class="cvlogo"></div>
      <div class="cvmid"><span class="cvk">Lectura de fichaje · ${E(j.temporada)} · Confidencial · ${ref}</span><h1 class="${nomJ.length > 26 ? "xl" : nomJ.length > 16 ? "l" : ""}">${E(nomJ)}</h1>
        <p class="cvdat">${E(clubN)} · ${E(LIGAS[j.liga] || j.liga)} · temporada ${E(j.temporada)}${d ? `<br>Encaje en ${E(d.nombre_club)} · ${E(LIGAS[d.liga] || d.liga)} ${E(d.temporada)} · rol ${E((ROLN[rolA] || "–").toLowerCase())}` : ""}</p>
        <dl class="cvfacts">${ficha.map(([a, v]) => `<div><dt>${a}</dt><dd>${E(v)}</dd></div>`).join("")}</dl></div>
      <ol class="cvidx">#INDICE#</ol>
      <div class="cvbot"><span>Preparado para ${d ? `${E(d.nombre_club)} · dirección deportiva` : "dirección deportiva"}</span><span>${E(fecha)}</span></div>` });

    // 1 · Kerno Analytics
    pags.push({ sec: "Kerno Analytics", html: `${ceja(1, "Kerno Analytics", "Una lectura en contexto, con su margen de error", "Sabrás qué jugador encaja, por qué y con cuánta seguridad.")}
      <div class="r3cols"><div><p class="r3p">Kerno Analytics es un socio independiente de inteligencia de talento para el deporte de élite, empezando por el baloncesto. Combinamos modelos predictivos con conocimiento profundo del juego para mostrar a los clubes cómo encaja un jugador en su sistema, en qué es probable que se convierta y con cuánta seguridad lo afirmamos.</p>
        <p class="r3p">Trabajamos solo para el lado del club y con confidencialidad por defecto: esta lectura es suya. Un jugador no es bueno en abstracto; es bueno para un sistema, un rol y unos compañeros. Por eso no ordenamos por fama ni por estadística total, sino por encaje.</p></div>
        <div class="r3q"><span class="r3lab">Las preguntas de cada lectura</span>
          <dl><div><dt>Encaje</dt><dd>¿Cómo funciona en este sistema, con este rol y estos compañeros?</dd></div><div><dt>Trayectoria</dt><dd>¿De dónde viene y qué ha sostenido temporada a temporada?</dd></div><div><dt>Riesgo</dt><dd>¿Qué puede fallar y qué nos haría cambiar de opinión?</dd></div><div><dt>Valor</dt><dd>Relación entre lo que aporta y lo que cuesta. <em>Fuera de esta lectura: requiere los datos económicos del club.</em></dd></div></dl></div></div>
      <div class="r3steps"><span class="r3lab">Cómo hacemos la lectura</span><ol>
        <li><b>Vemos todos sus partidos</b><span>Actas oficiales y jugada a jugada de trece competiciones. Como el ojeador que no se queda con un solo partido: buscamos lo que se repite.</span></li>
        <li><b>Lo medimos en la misma pista</b><span>Una canasta en una liga no vale lo mismo que en otra. Traducimos sus cifras a la exigencia de la liga de referencia (la del club de destino o, si no hay destino, la suya) para comparar a todos con la misma vara.</span></li>
        <li><b>Lo ponemos en tu vestuario</b><span>Un tirador rinde distinto con un base que penetra al lado. Simulamos su rol, sus minutos, sus compañeros y el estilo del club para leer cómo jugaría aquí.</span></li>
        <li><b>Decimos cuánto sabemos</b><span>Cada cifra va con su margen. Si un dato descansa en pocos minutos o en un salto de liga grande, lo decimos. Una recomendación sin su incertidumbre es solo una opinión con decimales.</span></li></ol></div>
      <div class="r3read"><span class="r3lab">Cómo leer las cifras de esta lectura</span><div>
        <div><b>Punto y rango</b>${barraPR(62, 48, 74, { ref: 50, w: 120 })}<span>El punto es la lectura; la franja, dónde puede moverse.</span></div>
        <div><b>Percentil</b><p class="r3big">80</p><span>Supera al 80 % de los jugadores de su puesto en ${E(IFPN())}; 50 es el mediano. En los bloques (anotación, rebote…), media de sus percentiles.</span></div>
        <div><b>Nivel Kerno e Impacto</b><p class="r3big">0–100</p><span>Las dos anclas de la lectura. Nivel Kerno: percentil esperado de producción entre los de su puesto en la liga del club. Impacto: percentil del cambio que provoca en el equipo (50 = no lo cambia). Las escalas 0–100 (50 = media de ${esc(VN())}) quedan para nivel por minutos, química y parejas.</span></div>
        <div><b>Colores</b><p class="r3cols3"><i style="background:#2B6FBF"></i>mejor<i style="background:#D35C2A"></i>peor<i style="background:#6550CC"></i>rasgo de estilo</p><span>El violeta no es bueno ni malo: describe cómo juega (cuánto tira de tres, cuánto usa el balón).</span></div></div></div>
      <div class="r3vals"><span class="r3lab">Lo que guía cada lectura</span><div>
        <div><b>Contexto antes que promedios</b><span>Un jugador no es bueno en abstracto. Es bueno para un sistema, un rol y un presupuesto.</span></div>
        <div><b>Franqueza calibrada</b><span>Decimos lo que sabemos y cuánto lo sabemos. Cada recomendación incluye su rango y lo que nos haría cambiar de opinión.</span></div>
        <div><b>Discreción por diseño</b><span>Las listas de un club son suyas. Confidencialidad por defecto en procesos, datos y comunicación.</span></div></div></div>
      <div class="r3call callout"><span class="r3tag">Basketball judgment, model rigor</span><p>Este análisis no sustituye en ningún caso el scouting en pista y humano, solo lo complementa con rigor matemático y científico.</p></div>` });

    // 2 · el jugador
    const filasT = tray.slice(-6).map((x) => { const r = rolDeRec(simRec(x)), m = medias.get(jKey(x)), est = !r, rr = r || rolEstimado(x, m);
      return `<tr class="${x === j ? "yo" : ""}"><td>${E(x.temporada)}</td><td>${E(x.nombre_club)}<small>${E(LC[x.liga] || x.liga)}</small></td><td>${rolChip(rr, est)}</td><td>${euSw(x)}${E(euLab(x))}</td><td class="num">${m && m.min_pg != null ? N(m.min_pg, 1) : (() => { const c = BY.get(x.clave); return c && c.min_total ? N(x.min / (c.min_total / durPartido(x.liga)), 1) : "–"; })()}</td><td class="num">${m ? N(m.pts_pg, 1) : "–"}</td><td class="num">${m ? N(m.reb_pg, 1) : "–"}</td><td class="num">${m ? N(m.ast_pg, 1) : "–"}</td><td class="num">${m ? N(m.ts_pct, 1) : "–"}</td><td class="num ${ESC.cls(sNivJ(x))}">${ESC.txt(sNivJ(x))}</td></tr>`; }).join("");
    const eu = euOf(j);
    pags.push({ sec: "El jugador", html: `${ceja(2, "El jugador", "Trayectoria, roles y perfil de juego", `${E(nomJ)}, ${E(IF_POS1[pos] || "jugador")}${rolO ? ` de ${E(ROLN[rolO].toLowerCase())}` : ""} en ${E(clubN)} (${E(LIGAS[j.liga] || j.liga)}). Sus cifras de ${E(j.temporada)}, expresadas en ${E(IFPN())}, lo sitúan <b>${E(etiqueta(pL))}</b>.`)}
      <dl class="r3id">${ficha.map(([a, v]) => `<div><dt>${a}</dt><dd>${E(v)}</dd></div>`).join("")}<div><dt>Club actual</dt><dd>${E(clubN)}</dd></div><div><dt>Rol actual</dt><dd>${rolChip(rolO, rolOest)}</dd></div></dl>
      <div class="r3blk"><h3>Trayectoria y rol en las últimas temporadas</h3><table class="r3t tray"><thead><tr><th>Temp.</th><th>Equipo</th><th>Rol</th><th>Estilo</th><th class="num">Min/p</th><th class="num">Pts</th><th class="num">Reb</th><th class="num">Ast</th><th class="num">TS%</th><th class="num">Nivel</th></tr></thead><tbody>${filasT}</tbody></table>
        <p class="r3n">Medias por partido de cada temporada (liga regular). Nivel: valoración por minutos en escala 0–100 (50 = jugador medio de ${esc(VN())} de esa temporada). Filete discontinuo: rol estimado por minutos y titularidades.</p></div>
      <div class="r3inkhero"><span class="r3tag">Su perfil en una mirada</span>
        ${eu ? `<div class="r3inkheroE"><div><span>Estilo de juego</span><b>${euSw(j)}${E(euLab(j))}</b><small>${E(eu.rol_jugador || "")} · pertenencia ${afin(j.eu_p)} de 100</small></div><p>${E(eu.jugador || eu.definicion || "")}</p></div>` : ""}
        <div class="r3inkheroK"><div class="anc"><span>Nivel Kerno</span><b>${an ? Math.round(an.NC) : "–"}</b><small>${an ? `${E(nivelTxt(an.NC))} · entre los ${E(IF_POSN[pos])} de ${E(ligaAnc)}` : `sin simulación · nivel 0–100: ${ESC.txt(Snv)}`}</small></div>
          <div class="anc"><span>Impacto</span><b>${anIM ? Math.round(an.IM) : "–"}</b><small>${anIM ? `${E(impTxt(an.IM))} · ${anCtx && anCtx.propio ? "en su club actual" : `en ${E(clubAnc)}`} · 50 = no lo cambia` : (sr != null ? `RAPM proyectado ${ESC.txt(sr)} (0–100)` : "sin simulación")}</small></div>
          <div><span>Punto fuerte</span><b class="w">${mejorB ? E(mejorB.bk.n) : "–"}</b><small>${mejorB ? `${pctN(mejorB.sc)} frente a su puesto` : ""}</small></div>
          <div><span>A mejorar</span><b class="w">${peorB && peorB !== mejorB ? E(peorB.bk.n) : "–"}</b><small>${peorB && peorB !== mejorB ? `${pctN(peorB.sc)} frente a su puesto` : ""}</small></div></div></div>
      <div class="r3cols c2"><div class="r3blk"><h3>Perfil por bloques frente a su puesto</h3><table class="r3t bloq"><tbody>${bloques.map(({ bk, sc }) => `<tr><td><b>${E(bk.n)}</b><small>${E(bk.q)}</small></td><td>${barraPR(sc, null, null, { ref: 50, w: 150, cls: sc >= 65 ? "up" : sc <= 35 ? "dn" : "" })}</td><td class="num"><b class="${ifTono(sc)}">${Math.round(sc)}</b></td></tr>`).join("")}</tbody></table><p class="r3n">Percentil de cada bloque frente a los ${E(IF_POSN[pos])} de ${E(IFPN())} (media de los percentiles de sus métricas). 50 es el ${E(IF_POS1[pos])} mediano.</p></div>
        <div class="r3blk"><h3>Evolución de su nivel</h3>${evolucion(tray, j)}</div></div>` });

    // 2-bis · las dos anclas (v4.0): hoja propia cuando hay simulación (destino o club actual)
    if (an) pags.push({ sec: "El jugador", num: 2, html: hojaAnclas({ j, pos, an, anEsc, anCtx, apeJ, ligaAnc, clubAnc, d, rolA, s2 }) });

    // 3 · conclusiones
    const ras = rasgos(R), s2ok = s2 && !s2.error, a = s2ok ? s2.adaptacion : null, eqv = s2ok ? s2.equipo : null;
    const lgI = s2ok && window.KernoV41 && KernoV41.listo() ? KernoV41.landing(s2.grupo_nacionalidad) : null, lgT = lgI ? (lgI.es[1] ? `${lgI.es[0]} a ${lgI.es[1]}` : lgI.es[0]) : "";
    const anTxt = an ? `Nivel Kerno ${Math.round(an.NC)}${anIM ? ` · Impacto ${Math.round(an.IM)}` : ""}` : "";
    const headline = d ? `${E(ROLN[rolA])} para ${E(d.nombre_club)}${an ? `: ${anTxt}` : ""}, confianza ${conf}` : an ? `${E(apeJ)} hoy: ${anTxt} en ${E(clubAnc)}, confianza ${conf}` : `${E(apeJ)} hoy: ${E(etiqueta(pL))}, confianza ${conf}`;
    const cubre = nec ? nec.filter((x) => x.v[0] === "up").slice(0, 4) : [], noCubre = nec ? nec.filter((x) => x.v[0] === "dn").slice(0, 3) : [];
    const q1 = eqv && eqv.quintetos && eqv.quintetos.find((q) => q.con_fichaje);
    const lectura = d ? `${E(apeJ)} llegaría a ${E(d.nombre_club)} como <b>${E(ROLN[rolA].toLowerCase())}</b> (${E(ROLD[rolA])}).${s2ok ? ` Con ese papel le corresponderían unos <b>${N(s2.minutos.media, 0)} minutos por noche</b> (rango 90 %: ${rng(s2.minutos, 90, 0)}).` : ""}${lgI ? ` Su grupo de traspaso (${E(lgT)}) deja de media un <b>Landing de ${SG0(lgI.pct, 1)} %</b> la primera temporada; es una cifra del grupo, no suya.` : ""}${cubre.length ? ` Cubre lo que más necesita el equipo en ${cubre.map((x) => x.n.toLowerCase()).join(", ")}.` : ""}`
      : `Esta lectura describe a ${E(apeJ)} en su contexto actual, sin club de destino: qué aporta, qué vigilar y cómo encaja hoy en ${E(clubN)}.`;
    const notaHtml = nota ? nota.split(/\n{2,}|\r?\n/).filter((t) => t.trim()).map((t) => `<p>${E(t.trim())}</p>`).join("") : "";
    const gen = []; if (b.min != null && b.min < 500) gen.push(`Su muestra de ${j.temporada} es corta (${N(b.min, 0)} minutos): sus porcentajes pueden moverse mucho.`); if (j.liga !== "euroleague") gen.push(`Sus cifras vienen de ${LIGAS[j.liga] || j.liga}: la traducción a ${IFPN()} tiene su margen, mayor cuanto más lejos esté la liga.`); if (tray.length <= 1) gen.push("Solo hay una temporada suya en los datos: no sabemos aún si su rendimiento se sostiene.");
    const cambiar = (s2ok ? (s2.avisos || []).map((x) => AVISO_TXT[x.tipo] || x.texto).concat(ras.bot.slice(0, 2).map((o) => `${IFM[o.k].mal.charAt(0).toUpperCase() + IFM[o.k].mal.slice(1)} (${IFM[o.k].n}, percentil ${Math.round(o.op)}).`)) : gen).slice(0, 4);
    const kAnc = an ? `<div class="idx"><span>Nivel Kerno</span><b>${Math.round(an.NC)}</b><small>${E(nivelTxt(an.NC))}</small></div>
        <div class="idx"><span>Impacto</span><b>${anIM ? Math.round(an.IM) : "–"}</b><small>${anIM ? E(impTxt(an.IM)) : "sin plantilla suficiente"}</small></div>` : "";
    const kNet = an && isFinite(an.delta_net) ? `<div><span>Net del equipo con él</span><b class="${an.delta_net > 0.5 ? "up" : an.delta_net < -0.5 ? "dn" : ""}">${SG0(an.delta_net, 1)}</b><small>pts/100 con él frente a sin él</small></div>`
      : (eqv ? `<div><span>Net del equipo con él</span><b class="${eqv.d_net > 0.5 ? "up" : eqv.d_net < -0.5 ? "dn" : ""}">${SG0(eqv.d_net, 2)}</b><small>pts/100 · rango 90 %: ${SG0(eqv.d_net_lo90, 1)} a ${SG0(eqv.d_net_hi90, 1)}</small></div>` : "");
    const kpis = d && s2ok ? `<div class="r3kp big${an ? " anc6" : ""}">${kAnc || ""}
        ${an ? (`<div><span>Lugar en la plantilla</span><b>${(c.c6 ? c.c6.orden : sim.orden).findIndex((o) => o.el) + 1}.º</b><small>de ${(c.c6 ? c.c6.orden : sim.orden).length} por nivel · confianza ${conf}</small></div>`) : ""}
        ${lgI ? `<div><span>Landing · su grupo de traspaso</span><b>${SG0(lgI.pct, 1)} %</b><small>${E(lgT)} · primera temporada</small></div>` : ""}
        <div><span>Minutos con ese rol</span><b>${N(s2.minutos.media, 0)}'</b><small>rango 90 %: ${rng(s2.minutos, 90, 0)}'</small></div>
        ${kNet}
        ${an ? "" : `<div><span>Lugar en la plantilla</span><b>${(c.c6 ? c.c6.orden : sim.orden).findIndex((o) => o.el) + 1}.º</b><small>de ${(c.c6 ? c.c6.orden : sim.orden).length} por nivel</small></div>`}</div>`
      : an ? `<div class="r3kp big anc6">${kAnc}<div><span>Nivel por minutos</span><b class="${ESC.cls(Snv)}">${ESC.txt(Snv)}</b><small>escala 0–100 · 50 = media de ${esc(VN())}</small></div><div><span>RAPM proyectado</span><b class="${ESC.cls(sr)}">${sr != null ? ESC.txt(sr) : "–"}</b><small>RAPM multiliga v4.0 en ${E(IFPL())}, escala 0–100</small></div><div><span>Minutos con ese rol</span><b>${anCtx && anCtx.res && anCtx.res.minutos ? N(anCtx.res.minutos.media, 0) : "–"}'</b><small>${anCtx && anCtx.res && anCtx.res.minutos ? `rango 90 %: ${rng(anCtx.res.minutos, 90, 0)}'` : ""}</small></div>${kNet}</div>`
      : `<div class="r3kp big"><div class="idx"><span>Nivel por minutos</span><b class="${ESC.cls(Snv)}">${ESC.txt(Snv)}</b><small>escala 0–100 · 50 = media de ${esc(VN())}</small></div><div><span>Percentil</span><b>${pL != null ? Math.round(pL) : "–"}</b><small>nivel frente a los ${E(IF_POSN[pos])} de ${E(IFPN())}</small></div><div><span>RAPM proyectado</span><b class="${ESC.cls(sr)}">${sr != null ? ESC.txt(sr) : "–"}</b><small>RAPM multiliga v4.0, escala 0–100</small></div><div><span>Rol actual</span><b class="r3w">${rolO ? ROLN[rolO] : "–"}</b><small>${rolOest ? "estimado por minutos" : "en su temporada"}</small></div></div>`;
    pags.push({ sec: "Conclusiones", html: `${ceja(3, "Conclusiones", d ? "Veredicto, adaptación y rol" : "Veredicto y contexto actual", "")}
      <div class="r3theread"><span class="r3lab">The Read</span><p>${headline}.</p></div>
      ${notaHtml ? `<div class="r3why callout"><span class="r3tag">Por qué lo proponemos</span>${notaHtml}</div>` : ""}
      <p class="r3p r3lead2">${lectura}</p>
      ${kpis}
      <div class="r3cols">
        <div class="r3blk"><h3>Lo que aporta</h3><ul class="r3l up">${ras.top.slice(0, 4).map((o) => `<li><b>${E(IFM[o.k].bien.charAt(0).toUpperCase() + IFM[o.k].bien.slice(1))}</b><span>${E(IFM[o.k].n)} · ${pctN(o.op)} frente a su puesto en ${E(IFPN())}</span></li>`).join("") || `<li><span>Ningún registro destaca con claridad sobre su puesto en ${E(IFPN())}.</span></li>`}</ul>
          ${d && cambiar.length ? `<div class="r3wwc" style="margin-top:14px"><span class="r3lab">What would change our mind</span><ul class="r3l">${cambiar.map((t) => `<li><span>${E(t)}</span></li>`).join("")}</ul></div>` : ""}</div>
        <div class="r3blk">${lgI ? `<h3>Landing: el cambio de liga</h3><div class="r3adk"><div><b class="${lgI.pct < 0 ? "dn" : "up"}">${SG0(lgI.pct, 1)} %</b><span>primera temporada</span><small>${E(lgT)}</small></div><div><b>${N(lgI.n, 0)}</b><span>traspasos del grupo</span><small>${E(lgT)}</small></div></div>
          <p class="r3n">Landing es lo que suele perder de valor su grupo de traspaso en la primera temporada por el coste de adaptarse a la nueva competición, frente al nivel que alcanza una vez adaptado. Es una cifra del grupo, no del jugador; sólo se muestra si su rango del 80 % excluye 0. Confianza baja: no tiene todavía un examen propio con fichajes reales.</p>` : `<h3>A vigilar</h3><ul class="r3l dn">${ras.bot.slice(0, 4).map((o) => `<li><b>${E(IFM[o.k].mal.charAt(0).toUpperCase() + IFM[o.k].mal.slice(1))}</b><span>${E(IFM[o.k].n)} · ${pctN(o.op)} frente a su puesto en ${E(IFPN())}</span></li>`).join("") || `<li><span>Ningún registro queda claramente por debajo de su puesto en ${E(IFPN())}.</span></li>`}</ul>`}
          ${q1 ? `<p class="r3n"><b>Quinteto más probable con él:</b> ${q1.nombres.map((x) => E(nom(String(x)).split(" ").slice(-1)[0])).join(", ")} (${Math.round(100 * q1.prob)} % de las temporadas simuladas).</p>` : ""}</div></div>
      ${!d ? (() => { const e = ifEsperado(R, c.ritmo || 72, 25); return `<div class="r3cols c2"><div class="r3blk"><h3>Su temporada por partido</h3><div class="r3mini"><div><b>${N(b.min_pg, 1)}</b><span>minutos</span></div><div><b>${N(b.pts_pg, 1)}</b><span>puntos</span></div><div><b>${N(b.reb_pg, 1)}</b><span>rebotes</span></div><div><b>${N(b.ast_pg, 1)}</b><span>asistencias</span></div></div><p class="r3n">${E(LIGAS[j.liga] || j.liga)} ${E(j.temporada)}, liga regular${b.gp ? ` · ${b.gp} partidos` : ""}.</p></div>
        <div class="r3blk"><h3>Qué produce por cada 25 minutos en ${E(IFPN())}</h3><div class="r3mini"><div><b>${N(e.pts, 1)}</b><span>puntos</span></div><div><b>${N(e.reb, 1)}</b><span>rebotes</span></div><div><b>${N(e.ast, 1)}</b><span>asistencias</span></div><div><b>${N(e.ts, 0)}<small>%</small></b><span>TS%</span></div></div><p class="r3n">Sus cifras expresadas en ${E(IFPN())}, al ritmo medio de esa competición.</p></div></div>`; })() : ""}
      ${d && !an && c.esc && c.esc.length ? `<div class="r3blk"><h3>Si cambias su rol</h3><table class="r3t esc"><thead><tr><th>Rol en ${E(d.nombre_club)}</th><th class="num">Minutos</th><th class="num">Puntos / partido</th><th class="num">Net del equipo</th></tr></thead><tbody>${c.esc.map((o) => `<tr class="${o.rol === rolA ? "yo" : ""}"><td>${rolChip(o.rol)}${o.rol === rolA ? " <small style=\"display:inline\">asignado</small>" : ""}</td><td class="num">${N(o.r.minutos.media, 0)}' <small style="display:inline">${rng(o.r.minutos, 90, 0)}</small></td><td class="num">${o.r.por_partido.pts ? `${N(o.r.por_partido.pts.media, 1)} <small style="display:inline">${rng(o.r.por_partido.pts, 90, 1)}</small>` : "–"}</td><td class="num">${SG0(o.r.equipo.d_net, 2)}</td></tr>`).join("")}</tbody></table><p class="r3n">Misma simulación con cada rol. Rangos al 90 %. Sirve para decidir qué papel le das: más rol no siempre suma igual al equipo.</p></div>` : ""}
      ${!d && cambiar.length ? `<div class="r3wwc"><span class="r3lab">What would change our mind</span><ul class="r3l">${cambiar.map((t) => `<li><span>${E(t)}</span></li>`).join("")}</ul></div>` : ""}` });

    // 4 · ataque y tiro
    const cp = ifCampo(R, pos, b), K4 = ["pts_p100", "usg_pct", "ts_pct", "fg3_pct", "ft_pct", "fg3a_rate", "fta_rate", "ast_pct", "tov_pct", "orapm"];
    const prod = s2ok ? s2.produccion_p100 : null, pp = s2ok ? s2.por_partido : null;
    const simAt = prod ? `<table class="r3t sim"><thead><tr><th>En ${E(d.nombre_club)} · ${E(ROLN[rolA])}</th><th class="num">Media</th><th class="num">Rango 90 %</th></tr></thead><tbody>
        ${[["Minutos por partido", s2.minutos, 0], ["Posesiones en pista por partido", pp && pp.posesiones, 1], ["Puntos por partido", pp && pp.pts, 1], ["Puntos / 100 posesiones", prod.pts_p100, 1], ["TS% · acierto real", prod.ts_pct, 1], ["USG% · peso en el ataque", prod.usg_pct, 1], ["AST% · asistencias", prod.ast_pct, 1], ["TOV% · pérdidas", prod.tov_pct, 1], ["Rebotes de ataque / 100 posesiones", prod.oreb_p100, 1]].filter(([, o]) => o && o.media != null).map(([n, o, dd]) => `<tr><td>${n}${o.recorte_cero ? "*" : ""}</td><td class="num"><b>${N(o.media, dd)}</b></td><td class="num">${rng(o, 90, dd)}${o.recorte_cero ? "*" : ""}</td></tr>`).join("")}</tbody></table>${notaCero(s2).replace('class="note"', 'class="r3n"')}` : "";
    const fAt = ["anotacion", "creacion"].map((k) => bloques.find((o) => o.bk.k === k)).filter(Boolean);
    const leadAt = `${E(cp.txt || "")}${fAt.length ? ` Bloques: <b>anotación, ${pctN(fAt[0].sc)}</b>${fAt[1] ? ` · <b>creación, ${pctN(fAt[1].sc)}</b>` : ""}.` : ""}`;
    pags.push({ sec: "Ataque y tiro", cls: "dense", html: `${ceja(4, "Ataque y tiro", "Anotación, tiro y creación", leadAt)}
      ${cifras(["pts_p100", "ts_pct", "usg_pct", "fg3_pct", "ast_pct"], R, pos)}
      ${tablaM(K4, R, pos, "Métrica de ataque")}
      <p class="r3p r3lec">${E(lecturaAtaque(R))}</p>
      <div class="r3cols at"><div class="r3blk"><h3>Desde dónde tira</h3>${cp.svg}<p class="r3n">Porcentaje de sus tiros desde cada zona y, debajo, el del ${E(IF_POS1[pos])} mediano de ${E(IFPN())}. Violeta: tira más desde esa zona; gris: menos.</p></div>
        <div class="r3blk">${simAt ? `<h3>Su ataque con el rol asignado</h3>${simAt}<p class="r3n">Rangos: lo que puede variar una temporada. Con mejores compañeros, un jugador suele tirar menos y con más acierto.</p>` : `<h3>Lectura</h3><p class="r3p">${fAt[0] && fAt[0].sc >= 60 ? "Anota por encima de lo habitual en su puesto." : fAt[0] && fAt[0].sc <= 40 ? "Su anotación queda por debajo de lo habitual en su puesto." : "Su anotación está en la zona media de su puesto."} ${fAt[1] && fAt[1].sc >= 60 ? "Además genera juego para los demás." : ""}</p>`}</div></div>` });

    // 5 · defensa y rebote
    const K5 = ["drtg", "drapm", "stl_pct", "blk_pct", "stop_pct", "pf_p100", "dreb_pct", "oreb_pct"];
    const fDf = ["defensa", "rebote"].map((k) => bloques.find((o) => o.bk.k === k)).filter(Boolean);
    const simDf = pp ? `<table class="r3t sim"><thead><tr><th>En ${E(d.nombre_club)} · por partido</th><th class="num">Media</th><th class="num">Rango 90 %</th></tr></thead><tbody>
        ${[["Rebotes", pp.reb], ["Robos", pp.stl], ["Tapones", pp.blk], ["Posesiones en pista", pp.posesiones]].filter(([, o]) => o && o.media != null).map(([n, o]) => `<tr><td>${n}</td><td class="num"><b>${N(o.media, 1)}</b></td><td class="num">${rng(o, 90)}</td></tr>`).join("")}</tbody></table>` : "";
    const leadDf = (() => { const dr = R.m.drtg, rb = R.m.dreb_pct, pd = pctDe("drtg", R), pr = pctDe("dreb_pct", R), t = [];
      if (dr && pd) t.push(`Con él en pista, su equipo encaja <b>${ifV("drtg", IFM.drtg && IFM.drtg.raw ? dr[1] : dr[0])} puntos por 100 posesiones</b> (${pctN(pd.op)})`);
      if (rb && pr) t.push(`captura el <b>${ifV("dreb_pct", IFM.dreb_pct && IFM.dreb_pct.raw ? rb[1] : rb[0])} de los rebotes defensivos</b> (${pctN(pr.op)})`);
      const bl = fDf.length ? ` Bloques: <b>defensa, ${pctN(fDf[0].sc)}</b>${fDf[1] ? ` · <b>rebote, ${pctN(fDf[1].sc)}</b>` : ""}.` : "";
      return (t.length ? t.join(" y ") + "." : `Su defensa frente a los jugadores de su puesto en ${IFPN()}.`) + bl; })();
    pags.push({ sec: "Defensa y rebote", cls: "dense", html: `${ceja(5, "Defensa y rebote", "Defensa, rebote y confianza del entrenador", leadDf)}
      ${cifras(["drtg", "drapm", "dreb_pct", "oreb_pct", "blk_pct", "stl_pct", "pf_p100"], R, pos)}
      ${tablaM(K5, R, pos, "Métrica de defensa y rebote")}
      <p class="r3n">La defensa es lo que peor recoge un acta: robos, tapones y rebotes cuentan lo que pasa con el balón, no las ayudas ni las rotaciones bien hechas. Por eso aquí pesa también el RAPM proyectado: cuántos puntos encaja su equipo con él y sin él.</p>
      <div class="r3cols c2"><div class="r3blk"><h3>Lectura</h3><p class="r3p">${(() => { const dp = R.m.drapm ? ifOp("drapm", R.m.drapm[2]) : null, st = R.m.stl_pct ? R.m.stl_pct[2] : null, bk = R.m.blk_pct ? R.m.blk_pct[2] : null, dr = R.m.dreb_pct ? R.m.dreb_pct[2] : null; const t = [];
          if (dp != null) t.push(dp >= 65 ? "Su equipo defiende claramente mejor con él en pista." : dp <= 35 ? "Su equipo encaja más con él en pista: punto a vigilar en el sistema defensivo." : "Con él en pista, su equipo defiende en la línea de su media.");
          if (st != null && st >= 70) t.push("Lee líneas de pase: roba más que la mayoría de su puesto."); if (bk != null && bk >= 70) t.push("Protege el aro con tapones por encima de su puesto.");
          if (dr != null) t.push(dr >= 65 ? "Cierra bien el rebote defensivo, lo que acaba posesiones." : dr <= 35 ? "Rebotea poco en defensa: necesita compañeros que cierren." : ""); return E(t.filter(Boolean).join(" ")); })()}</p></div>
        <div class="r3blk">${simDf ? `<h3>Su producción defensiva con el rol asignado</h3>${simDf}` : ""}</div></div>
      <div class="r3blk"><h3>La confianza de su entrenador actual</h3><dl class="r3id r3rolid">${[["Titular", b.q_titular != null && b.gp ? `${b.q_titular} de ${b.gp} partidos` : b.gs != null && b.gp ? `${b.gs} de ${b.gp} partidos` : "–"], ["En pista en los finales", b.q_cierra != null && b.gp ? `${b.q_cierra} de ${b.gp} partidos` : "–"], ["Minutos en el último cuarto", b.q_pct_min_q4 != null ? `${N(b.q_pct_min_q4, 0)} % de los suyos` : "–"], ["Minutos decisivos", b.q_clutch_min != null ? `${N(b.q_clutch_min, 0)}'${b.q_clutch_net != null ? ` · Net ${SG0(b.q_clutch_net, 1)}` : ""}` : "–"], ["Faltas recibidas", b.pfd_pg != null ? `${N(b.pfd_pg, 1)} por partido` : "–"], ["+/− por partido", b.plus_minus_pg != null ? SG0(b.plus_minus_pg, 1) : "–"]].map(([a, v]) => `<div><dt>${a}</dt><dd>${E(v)}</dd></div>`).join("")}</dl><p class="r3n">Datos del jugada a jugada de su temporada actual. Que cierre partidos dice mucho de cómo lo ve su cuerpo técnico en defensa.</p></div>` });

    // 6 · contexto y conexiones
    const necT = nec ? `<table class="r3t nec"><thead><tr><th>Aspecto del juego</th><th>${E(d.nombre_club)} · percentil en su liga</th><th>${E(apeJ)} · percentil en su puesto</th><th>Lectura</th></tr></thead><tbody>${nec.map((x) => `<tr><td><b>${E(x.n)}</b><small>${E(x.det)}</small></td><td>${barraPR(x.e, null, null, { ref: 50, w: 110, cls: x.estilo ? "neu" : x.e >= 65 ? "up" : x.e <= 35 ? "dn" : "" })}</td><td>${barraPR(x.p, null, null, { ref: 50, w: 110, cls: x.estilo ? "neu" : x.p >= 65 ? "up" : x.p <= 35 ? "dn" : "" })}</td><td class="ver ${x.v[0]}">${E(x.v[1])}</td></tr>`).join("")}</tbody></table>` : "";
    function necPar(e, p, estilo, w) { const x = (v) => 6 + (w - 12) * Math.max(0, Math.min(100, v)) / 100, cl = estilo ? "neu" : p >= 65 ? "up" : p <= 35 ? "dn" : "";
      return `<svg class="r3nec" viewBox="0 0 ${w} 18" width="${w}" height="18" aria-hidden="true"><line x1="6" x2="${w - 6}" y1="9" y2="9" class="tr"/>${[25, 50, 75].map((v) => `<line x1="${x(v).toFixed(1)}" x2="${x(v).toFixed(1)}" y1="${v === 50 ? 2.5 : 6}" y2="${v === 50 ? 15.5 : 12}" class="${v === 50 ? "rf" : "tk"}"/>`).join("")}<line x1="${x(e).toFixed(1)}" x2="${x(p).toFixed(1)}" y1="9" y2="9" class="gap ${cl}"/><rect x="${(x(e) - 4.5).toFixed(1)}" y="4.5" width="9" height="9" class="eq"/><circle cx="${x(p).toFixed(1)}" cy="9" r="5.4" class="pt ${cl}"/></svg>`; }
    function tablaNec(rows, club, ape, top, w, corta, densa) {
      const chip = (v) => `<span class="r3chip ${v[0] || "nt"}">${E(v[1])}</span>`;
      return `<table class="r3t nec2${corta ? " corta" : ""}${densa ? " densa" : ""}"><thead><tr><th>Aspecto del juego</th>${corta ? "" : `<th class="num">${E(club)}</th>`}<th><span class="r3necl"><i class="eq"></i>equipo <i class="pt"></i>${E(ape)}</span></th>${corta ? "" : `<th class="num">${E(ape)}</th>`}<th>Lectura</th></tr></thead><tbody>${rows.map((x) => `<tr class="${x === top ? "top" : ""}"><td><b>${E(x.n)}</b><small>${E(x.det)}</small></td>${corta ? "" : `<td class="num">${Math.round(x.e)}</td>`}<td>${necPar(x.e, x.p, x.estilo, w)}</td>${corta ? "" : `<td class="num"><b class="${x.estilo ? "" : x.p >= 65 ? "up" : x.p <= 35 ? "dn" : ""}">${Math.round(x.p)}</b></td>`}<td>${chip(x.v)}</td></tr>`).join("")}</tbody></table>`;
    }
    const rankV = (orden, yoF, temp, simu) => `<ol class="r3rank">${orden.slice(0, 14).map((o, i) => { const S = sNivCL(o.L, temp) ?? 0; return `<li class="${yoF(o) ? "yo" : ""}"><span>${i + 1}</span><span>${E(nom(o.j.nombre))}${simu && o.el ? " · simulado" : ""}</span><b>${ESC.txt(S)}</b></li>`; }).join("")}</ol>`;
    if (d) {
      const c6 = c.c6, est = s2ok ? s2.estilo : null, hueco = est && est.hueco_cubierto ? simEu(est.hueco_cubierto) : null, peu = est ? euDeVec(est.jugador) : null, teu = est ? euDeVec(est.equipo) : null;
      const dU = est ? 100 * (est.d_entropia_uso || 0) : null, dPs = est ? 100 * (est.d_entropia_pases || 0) : null;
      const QA = c6 && c6.qa != null ? c6.qa : sim.qa, QD = c6 && c6.qd != null ? c6.qd : sim.qd;
      const qd = QA != null && QD != null ? Math.round(ESC.dS("sinergia_rapm", QD)) - Math.round(ESC.dS("sinergia_rapm", QA)) : null;
      const sa = c6 && c6.nivSin != null ? sNivCL(c6.nivSin, d.temporada) : sNivCL(sim.antes.L, d.temporada), sd = c6 && c6.nivCon != null ? sNivCL(c6.nivCon, d.temporada) : sNivCL(sim.despues.L, d.temporada);
      const cubreN = nec ? nec.filter((x) => x.v[1] === "Cubre una carencia" || x.v[1] === "Refuerza un punto fuerte").map((x) => x.n.toLowerCase()) : [], noN = nec ? nec.filter((x) => x.v[1] === "No corrige la carencia").map((x) => x.n.toLowerCase()) : [];
      const lead6a = `${cubreN.length ? `Con ${E(apeJ)}, ${E(d.nombre_club)} gana en <b>${E(cubreN.join(", "))}</b>.` : `${E(apeJ)} no cubre con claridad ninguna carencia de ${E(d.nombre_club)}.`}${noN.length ? ` Sigue sin corregir: ${E(noN.join(", "))}.` : ""}${eqv ? ` Net del equipo con él: <b>${SG0(eqv.d_net, 2)} pts/100</b>.` : ""}`;
      const kTeam = `<div class="r3kp t4">
          <div class="idx"><span>Net del equipo</span><b class="${eqv && eqv.d_net > 0.5 ? "up" : eqv && eqv.d_net < -0.5 ? "dn" : ""}">${eqv ? SG0(eqv.d_net, 2) : "–"}</b><small>${eqv ? `pts/100 · ${SG0(eqv.net_sin, 1)} <i class="k-ar" aria-hidden="true"></i> ${SG0(eqv.net_con, 1)}` : ""}</small></div>
          <div><span>Nivel de la plantilla</span><b>${ESC.txt(sa)} <i class="k-ar" aria-hidden="true"></i> ${ESC.txt(sd)}</b><small>${c6 && c6.nivSin != null ? "nivel medio por minutos · escala 0–100" : `escala 0–100 · ${sim.antes.rk}.º <i class="k-ar" aria-hidden="true"></i> ${sim.despues.rk}.º de ${sim.n} en su liga`}</small></div>
          <div><span>Química de la plantilla</span><b>${QA != null && QD != null ? `${ESC.txt(ESC.dS("sinergia_rapm", QA))} <i class="k-ar" aria-hidden="true"></i> ${ESC.txt(ESC.dS("sinergia_rapm", QD))}` : "–"}</b><small>escala 0–100 · 50 = pareja media de ${E(VN())}</small></div>
          <div><span>Reparto del balón</span><b>${est ? `${N(100 * est.entropia_uso[0], 0)} <i class="k-ar" aria-hidden="true"></i> ${N(100 * est.entropia_uso[1], 0)}` : "–"}</b><small>de 100 · más alto = uso del balón más repartido${est ? ` · pase ${N(100 * est.entropia_pases[0], 0)} <i class="k-ar" aria-hidden="true"></i> ${N(100 * est.entropia_pases[1], 0)}` : ""}</small></div></div>`;
      // «Ranking frente a su liga» (CEO, 04-11-2026): el equipo sin y con él entre los clubes de la liga de referencia
      const rkT = (() => {
        const R = c6 && c6.rkL; if (!R) return "";
        const eus = EUS(), colE = (eu) => (eu != null && eus[eu] ? eus[eu].color : "#8F9993"), corta = (s, n) => (s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);
        const filas = R.clubs.map((c) => ({ t: "el", ...c })).concat([{ t: "sin", nom: `Sin ${apeJ}`, v: R.sin.v, eu: R.sin.eu }, { t: "con", nom: `Con ${apeJ}`, v: R.con.v, eu: R.con.eu }]).sort((a, b) => b.v - a.v || (a.t === "con" ? -1 : 1));
        // puesto real de cada fila en la clasificación completa (el «sin él» lleva el puesto que tendría sin él)
        let p0 = 0; filas.forEach((f) => { f.rk = f.t === "sin" ? R.sin.rk : ++p0; });
        // Ligas de más de 20 clubes (CEO, 06-11-2026): solo los clubes más cercanos al equipo con él y, aunque quede lejos,
        // el equipo sin él; los tramos omitidos se señalan con su número de clubes.
        let vis = filas;
        if (filas.length > 22) {
          const ic = filas.findIndex((f) => f.t === "con"), is = filas.findIndex((f) => f.t === "sin"), K = 7;
          let a = Math.max(0, ic - K), b = Math.min(filas.length, ic + K + 1);
          if (is < a && a - is <= 3) a = is; if (is >= b && is - b <= 2) b = is + 1;
          const sel = new Set(filas.slice(a, b)); sel.add(filas[is]); sel.add(filas[0]);
          vis = []; let prev = -1;
          filas.forEach((f, i) => { if (!sel.has(f)) return; if (i - prev > 1) vis.push({ t: "gap", n: filas.slice(prev + 1, i).filter((x) => x.t === "el").length }); vis.push(f); prev = i; });
          if (prev < filas.length - 1) vis.push({ t: "gap", n: filas.slice(prev + 1).filter((x) => x.t === "el").length });
        }
        const vv = vis.filter((f) => f.t !== "gap").map((f) => f.v);
        const lo = Math.max(-100, Math.min(-25, ...vv) - 6), hi = Math.min(100, Math.max(25, ...vv) + 6);
        const W = 380, x0 = 152, x1 = W - 30, rh = 13.2, top = 14, H = top + vis.length * rh + 2, X = (v) => (x0 + (v - lo) / (hi - lo) * (x1 - x0)).toFixed(1);
        let g = "", pos = 0;
        [-75, -50, -25, 0, 25, 50, 75].filter((v) => v >= lo && v <= hi).forEach((v) => { g += `<line x1="${X(v)}" x2="${X(v)}" y1="${top - 2}" y2="${H}" class="${v === 0 ? "z" : "gr"}"/><text x="${X(v)}" y="8" class="ax">${v === 0 ? "media" : ESC.txt(v)}</text>`; });
        vis.forEach((f, i) => { const y = top + i * rh, cy = (y + rh / 2).toFixed(1), yo = f.t !== "el";
          if (f.t === "gap") { g += `<text x="20" y="${(y + rh / 2 + 3).toFixed(1)}" class="ax" style="text-anchor:start">··· ${f.n} ${f.n === 1 ? "club" : "clubes"} ···</text>`; return; }
          g += `${yo ? `<rect x="0" y="${(y + 0.6).toFixed(1)}" width="${W}" height="${(rh - 1.2).toFixed(1)}" class="${f.t}"/>` : ""}<text x="2" y="${(y + rh / 2 + 3).toFixed(1)}" class="n">${f.rk}.</text><text x="20" y="${(y + rh / 2 + 3).toFixed(1)}" class="nm${yo ? " b" : ""}">${E(corta(f.nom, 27))}</text>
            <line x1="${X(Math.min(0, f.v))}" x2="${X(Math.max(0, f.v))}" y1="${cy}" y2="${cy}" class="bar ${f.t}"/><circle cx="${X(f.v)}" cy="${cy}" r="${f.t === "con" ? 4 : f.t === "sin" ? 3.4 : 2.7}" class="pt ${f.t}"${f.t === "el" ? ` style="fill:${colE(f.eu)}"` : ""}/><text x="${W - 2}" y="${(y + rh / 2 + 3).toFixed(1)}" class="v${yo ? " b" : ""}">${ESC.txt(f.v)}</text>`; });
        const svg = `<svg class="r3rkl" viewBox="0 0 ${W} ${H.toFixed(1)}" role="img" aria-label="Ranking frente a ${E(R.ligaN)}">${g}</svg>`;
        // lectura del cambio de puesto
        const dR = R.sin.rk - R.con.rk, dV = Math.round(R.con.v) - Math.round(R.sin.v);
        const pasa = R.clubs.filter((c) => c.v > R.sin.v && !(c.v > R.con.v)).sort((a, b) => b.v - a.v).map((c) => c.nom);
        const sobre = R.clubs.filter((c) => c.v > R.con.v).sort((a, b) => a.v - b.v)[0];
        const txt1 = dR > 0 ? `Con ${E(apeJ)}, ${E(d.nombre_club)} pasaría del <b>${R.sin.rk}.º al ${R.con.rk}.º</b> de ${R.n} por nivel en ${E(R.ligaN)} ${E(R.tEL)}${pasa.length ? `: adelanta a ${E(yLista(pasa.slice(0, 4)))}${pasa.length > 4 ? ` y ${pasa.length - 4} más` : ""}` : ""}.`
          : dR < 0 ? `Con ${E(apeJ)}, ${E(d.nombre_club)} bajaría del <b>${R.sin.rk}.º al ${R.con.rk}.º</b> de ${R.n} por nivel en ${E(R.ligaN)} ${E(R.tEL)}.`
          : `Con ${E(apeJ)}, ${E(d.nombre_club)} se mantendría <b>${R.con.rk}.º de ${R.n}</b> por nivel en ${E(R.ligaN)} ${E(R.tEL)}${dV ? `: ${dV > 0 ? "gana" : "pierde"} ${Math.abs(dV)} punto${Math.abs(dV) === 1 ? "" : "s"} sin cambiar de puesto` : ""}.`;
        const txt2 = sobre ? ` El siguiente escalón, ${E(sobre.nom)}, queda a ${Math.max(1, Math.round(sobre.v) - Math.round(R.con.v))} punto${Math.max(1, Math.round(sobre.v) - Math.round(R.con.v)) === 1 ? "" : "s"}.` : ` Sería el club de más nivel de la liga.`;
        const txt3 = R.real ? ` Como referencia, el ${E(R.real.nom)} real de ${E(R.tEL)} ${R.prov ? "va" : "fue"} ${R.real.rk}.º (${ESC.txt(R.real.v)})${Math.abs(Math.round(R.real.v) - Math.round(R.sin.v)) >= 3 ? `; la diferencia con la plantilla sin él sale de los jugadores y minutos que se consideran ahora` : ""}.` : "";
        const txt4 = d.temporada !== R.tEL ? ` La plantilla es la de ${E(d.temporada)}; los demás clubes, los de ${E(R.tEL)}, la última temporada completa (${E(d.temporada)} aún no tiene clubes con datos).` : R.prov ? ` Temporada en curso: los clubes de ${E(R.ligaN)} ${E(R.tEL)} con sus datos hasta hoy.` : "";
        return `<div class="r3cols at r3rkb"><div class="r3blk"><h3>Ranking frente a ${E(R.ligaN)} ${E(R.tEL)}</h3>${svg}</div>
          <div class="r3blk"><h3>Su sitio en la liga, sin y con él</h3><div class="r3kp t2"><div><span>Puesto por nivel</span><b>${R.sin.rk}.º <i class="k-ar" aria-hidden="true"></i> ${R.con.rk}.º</b><small>de ${R.n} clubes</small></div><div><span>Nivel del equipo</span><b>${ESC.txt(R.sin.v)} <i class="k-ar" aria-hidden="true"></i> ${ESC.txt(R.con.v)}</b><small>escala 0–100 · 50 = club medio</small></div></div>
            <p class="r3p">${txt1}${txt2}${txt3}${txt4}</p>
            <p class="r3n">Nivel de caja del equipo: el que dan las métricas de rendimiento de sus jugadores, ponderadas por los minutos previstos, frente a los clubes de ${E(R.ligaN)}. Mide nivel, no estilo, y no incluye química ni quintetos; no es el nivel medio por minutos de arriba. En amarillo, con él; en gris, sin él, con el puesto que tendría sin él.${vis !== filas ? ` Liga de ${R.n} clubes: se muestran el primero, los más cercanos al equipo con él y el equipo sin él; «···» indica los clubes omitidos.` : ""} El color de cada club es su estilo. Valor central, sin rango.</p></div></div>`;
      })();
      const barras = est && est.composicion_sin && est.composicion_con ? barrasEstilo([["Plantilla sin él", est.composicion_sin], [`Con ${apeJ}`, est.composicion_con, true]].concat(est.objetivo ? [["Referencia de su estilo", est.objetivo]] : [])) : "";
        const yoT = c6 && c6.yo ? ["ortg", "drtg", "ts_pct", "usg_pct", "ast_pct", "rapm"].map((k) => { const o = c6.yo.out[k]; if (!o || o.x == null) return ""; const f = (v) => k === "rapm" ? SG(v, 2) : N(v, 1), dif = o.y - o.x, sen = o.m.sentido, cls = Math.abs(dif) < (k === "rapm" ? 0.05 : 0.1) ? "eq" : sen === 0 ? "neu" : dif * sen > 0 ? "up" : "dn";
          return `<div><span>${E((CTXN_R[k] || [o.m.nombre])[0])}</span><b>${f(o.x)} <i class="k-ar" aria-hidden="true"></i> <em class="${cls}">${f(o.y)}</em></b></div>`; }).join("") : "";
      if (!nec || !nec.length) {
      pags.push({ sec: "Contexto y conexiones", num: 6, html: `${ceja(6, "Contexto y conexiones", "Carencias del equipo y encaje de estilo", lead6a)}${necT}
        <div class="r3cols c2"><div class="r3blk"><h3>Estilo y encaje en el sistema</h3><p class="r3p">${peu ? `${E(apeJ)} es un jugador de estilo <b>${E(peu.eu_etiqueta)}</b>` : `${E(apeJ)}`}${teu ? ` en un equipo de estilo <b>${E(teu.eu_etiqueta)}</b>` : ""}.${hueco ? ` Su perfil cubre sobre todo el hueco de <b>${E(hueco.eu_etiqueta)}</b> que deja la plantilla.` : ""}${dU != null ? ` Con él, el balón se reparte ${Math.abs(dU) < 0.5 ? "igual que ahora" : dU > 0 ? "entre más manos" : "en menos manos"} y la circulación de pase se vuelve ${Math.abs(dPs) < 0.5 ? "igual de variada" : dPs > 0 ? "más variada (menos previsible para el rival)" : "más concentrada"}.` : ""}</p>
            ${qd != null ? `<p class="r3n"><b>Química de la plantilla:</b> ${Math.abs(qd) < 2 ? "apenas cambia: encaja sin alterar el equilibrio" : qd > 0 ? "mejora cómo se combinan los perfiles" : "resta química: habría que acompañarlo bien"}.</p>` : ""}</div>
          <div class="r3blk"><h3>Estilos de la plantilla, sin y con él</h3>${barras}<p class="r3n">Peso de cada estilo en la plantilla, por minutos. La referencia es el reparto habitual de los equipos con su mismo estilo: lo que falta frente a ella es el hueco que puede cubrir un fichaje.</p></div></div>
        <div class="r3blk"><h3>El equipo con él dentro</h3>${kTeam}${c6 && (c6.quitados.length || c6.anadidos.length) ? `<p class="r3n"><b>Plantilla considerada:</b> la del club${c6.quitados.length ? `, sin ${E(yLista(c6.quitados.map((x) => nom(x))))}` : ""}${c6.anadidos.length ? `${c6.quitados.length ? ";" : ","} con ${E(yLista(c6.anadidos.map((x) => nom(x))))}` : ""}.</p>` : ""}</div>
          ${yoT ? `<div class="r3blk"><h3>Sus propios números en esta plantilla</h3><div class="r3yo">${yoT}</div><p class="r3n">De su valor expresado en ${E(IFPN())} con los compañeros que tuvo a su valor previsto con esta plantilla.</p></div>` : ""}${rkT}` });
      } else {
        const rend = nec.filter((x) => x.g !== "estilo"), estN = nec.filter((x) => x.g === "estilo");
        const cnt = (f) => rend.filter(f), cub = cnt((x) => x.v[1] === "Cubre una carencia"), ref = cnt((x) => x.v[1] === "Refuerza un punto fuerte"), neu = cnt((x) => x.v[0] === ""), mal = cnt((x) => x.v[0] === "dn");
        const top = cub.slice().sort((a, b) => (b.p - b.e) - (a.p - a.e))[0] || null;
        const lst = (a) => a.length ? E(a.map((x) => x.n.toLowerCase()).join(", ")) : "ninguno";
        const kNec = `<div class="r3kp t4 r3neck"><div class="idx"><span>Cubre carencias</span><b class="${cub.length ? "up" : ""}">${cub.length}</b><small>${lst(cub)}</small></div>
          <div><span>Refuerza puntos fuertes</span><b>${ref.length}</b><small>${lst(ref)}</small></div>
          <div><span>Sin cambio claro</span><b>${neu.length}</b><small>de ${rend.length} aspectos de rendimiento</small></div>
          <div><span>No corrige o queda por debajo</span><b class="${mal.length ? "dn" : ""}">${mal.length}</b><small>${lst(mal)}</small></div></div>`;
        const necT2 = tablaNec(rend, d.nombre_club, apeJ, top, 230);
        const leadEst = hueco ? `Su perfil cubre sobre todo el hueco de <b>${E(hueco.eu_etiqueta)}</b> que deja la plantilla de ${E(d.nombre_club)}.` : peu && teu ? `${E(apeJ)} es un jugador de estilo <b>${E(peu.eu_etiqueta)}</b> en un equipo de estilo <b>${E(teu.eu_etiqueta)}</b>.` : `Así cambia el reparto de estilos de ${E(d.nombre_club)} con ${E(apeJ)}.`;
        pags.push({ sec: "Contexto y conexiones", num: 6, html: `${ceja(6, "Contexto y conexiones", "Carencias del equipo: qué cubre con él", lead6a)}
          ${kNec}
          <div class="r3blk"><h3>Rendimiento: dónde está el equipo y qué aporta él</h3>${necT2}
            <p class="r3n">Cuadrado: el percentil de ${E(d.nombre_club)} entre los equipos de su liga. Círculo: el de ${E(apeJ)} frente a los ${E(IF_POSN[pos] || "jugadores")} de ${E(IFPN())} (azul, en el tercio alto; naranja, en el bajo). <b>Cubre una carencia</b>: el equipo está en el tercio bajo de su liga y él en el tercio alto de su puesto; <b>refuerza un punto fuerte</b>: los dos en el tercio alto; <b>no corrige</b>: los dos en el tercio bajo; <b>por debajo del equipo</b>: el equipo es fuerte y él no. En amarillo, la carencia que más cubre. Percentiles de la temporada regular; el del equipo, con todo su plantel.</p></div>` });
        pags.push({ sec: "Contexto y conexiones", num: 6, html: `${ceja(6, "Contexto y conexiones", "Cómo cambia el estilo del equipo con él", leadEst)}
          <div class="r3cols c2"><div class="r3blk"><h3>Su impacto en el estilo</h3>${estN.length ? tablaNec(estN, d.nombre_club, apeJ, null, 110, true) : ""}
              <h3 style="margin-top:12px!important">Estilo y encaje en el sistema</h3><p class="r3p">${peu ? `${E(apeJ)} es un jugador de estilo <b>${E(peu.eu_etiqueta)}</b>` : `${E(apeJ)}`}${teu ? ` en un equipo de estilo <b>${E(teu.eu_etiqueta)}</b>` : ""}.${hueco ? ` Su perfil cubre sobre todo el hueco de <b>${E(hueco.eu_etiqueta)}</b> que deja la plantilla.` : ""}${dU != null ? ` Con él, el balón se reparte ${Math.abs(dU) < 0.5 ? "igual que ahora" : dU > 0 ? "entre más manos" : "en menos manos"} y la circulación de pase se vuelve ${Math.abs(dPs) < 0.5 ? "igual de variada" : dPs > 0 ? "más variada (menos previsible para el rival)" : "más concentrada"}.` : ""}</p>
              ${qd != null ? `<p class="r3n"><b>Química de la plantilla:</b> ${Math.abs(qd) < 2 ? "apenas cambia: encaja sin alterar el equilibrio" : qd > 0 ? "mejora cómo se combinan los perfiles" : "resta química: habría que acompañarlo bien"}.</p>` : ""}</div>
            <div class="r3blk"><h3>Estilos de la plantilla, sin y con él</h3>${barras}<p class="r3n">Peso de cada estilo en la plantilla, por minutos. La referencia es el reparto habitual de los equipos con su mismo estilo: lo que falta frente a ella es el hueco que puede cubrir un fichaje.</p></div></div>
          <div class="r3blk"><h3>El equipo con él dentro</h3>${kTeam}${c6 && (c6.quitados.length || c6.anadidos.length) ? `<p class="r3n"><b>Plantilla considerada:</b> la del club${c6.quitados.length ? `, sin ${E(yLista(c6.quitados.map((x) => nom(x))))}` : ""}${c6.anadidos.length ? `${c6.quitados.length ? ";" : ","} con ${E(yLista(c6.anadidos.map((x) => nom(x))))}` : ""}.</p>` : ""}</div>
          ${yoT ? `<div class="r3blk"><h3>Sus propios números en esta plantilla</h3><div class="r3yo">${yoT}</div><p class="r3n">De su valor expresado en ${E(IFPN())} con los compañeros que tuvo a su valor previsto con esta plantilla.</p></div>` : ""}${rkT}` });
      }
      // 06 · B · sinergias de pareja y quinteto
      if (c6 && (c6.pares.length || c6.q5)) {
        const P = c6.pares, b1 = P[0], w1 = P[P.length - 1], nomC = (o) => nom(o.j.nombre);
        const nPos = P.filter((x) => Math.round(x.S) > 0).length, rp = c6.refPar;
        const lead6b = P.length ? `La pareja que más sumaría en ${E(d.nombre_club)} es con <b>${E(nomC(b1.o))}</b> (${ESC.txt(b1.S)}) y la que menos suma, con <b>${E(nomC(w1.o))}</b> (${ESC.txt(w1.S)}). ${nPos === 0 ? `Ninguna de sus ${P.length} parejas suma` : nPos === 1 ? `Una de sus ${P.length} parejas suma` : `${nPos} de sus ${P.length} parejas suman`} frente a una pareja media de ${E(VN())}.${rp ? ` Como referencia, la pareja de la plantilla actual que más suma (${E(ape(rp.A.j.nombre))} + ${E(ape(rp.B.j.nombre))}) está en ${ESC.txt(ESC.dS("sinergia_rapm", rp.v))}.` : ""}` : "";
        const filasP = P.map((x) => ({ nom: `${nomC(x.o)} · ${N(x.o.p.minutos, 0)}'`, S: x.S, sw: (euOf(x.o.j) || {}).color }));
        const tops = (arr) => arr.map((x) => `<li class="${Math.round(x.S) > 0 ? "up" : Math.round(x.S) < 0 ? "dn" : ""}"><b>${E(nomC(x.o))}</b><span>${ESC.txt(x.S)} · por estilo ${ESC.txtD(x.est)} · por nivel ${ESC.txtD(x.niv)}</span></li>`).join("");
        const q5 = c6.q5;
        pags.push({ sec: "Contexto y conexiones", num: 6, html: `${ceja(6, "Contexto y conexiones", "Sinergias de pareja con la plantilla", lead6b)}
          ${P.length ? `<div class="r3blk"><h3>Cómo se entendería con cada compañero</h3>${svgSinergias(filasP)}<p class="r3n">Sinergia prevista de cada pareja (${E(apeJ)} + compañero) frente a una pareja media de ${E(VN())}, escala 0–100; combina el encaje de sus estilos y el nivel de los dos. Junto al nombre, minutos por partido del compañero con él en la plantilla y su estilo (color). Valor central del modelo de química, sin rango por pareja.${notaMin()}</p></div>` : ""}
          <div class="r3cols c2">${q5 ? `<div class="r3blk"><h3>${q5.modo === "con" ? "Quinteto más probable con él" : "El quinteto principal, con él dentro"}</h3>${svgQuinteto(q5.q, q5.sel, j)}<p class="r3n">${q5.modo === "con" ? `Aparece en el ${Math.round(100 * q5.prob)} % de las temporadas simuladas.` : `Con el rol de ${E(ROLN[rolA].toLowerCase())} no entra en los quintetos más repetidos. El principal (${Math.round(100 * q5.prob)} % de las temporadas simuladas) tiene un Net previsto de ${SG(q5.base.total, 1)}; con ${E(apeJ)} en lugar de ${E(ape(q5.fuera.j.nombre))} (su puesto, menos minutos), ${SG(q5.q.total, 1)}.`} Net previsto = RAPM proyectado de cada jugador + química de sus 10 parejas, frente a un quinteto medio de ${E(VN())}. Valor central, sin rango.${q5.q.falta.length ? " *Sin jugada a jugada: cuenta 0." : ""}</p></div>` : "<div></div>"}
            ${P.length ? `<div class="r3blk"><h3>Qué explica cada química</h3><span class="r3lab">Sus tres parejas con más química</span><ul class="r3l sg">${tops(P.slice(0, 3))}</ul><span class="r3lab" style="margin-top:8px">Las tres que menos suman</span><ul class="r3l sg">${tops(P.slice(-3).reverse())}</ul><p class="r3n">«Por estilo»: cómo se complementan sus formas de jugar. «Por nivel»: lo que añade o resta el nivel de los dos.</p></div>` : ""}</div>` });
      }
      // 06 · C · impacto en la plantilla y en sus compañeros
      if (c6) {
        const gm = (d.liga === "nba" || d.liga === "gleague") ? 48 : 40, mins = s2.plantilla.filter((p) => (p.minutos >= 0.5 || (p.minutos_sin || 0) >= 0.5) && (p.fichaje || !mmIn() || c6.okPer.has(p.persona))).map((p) => ({ nom: p.fichaje ? apeJ : nom(p.nombre || "").split(" ").slice(-1)[0], sin: p.fichaje ? null : p.minutos_sin, con: p.minutos, yo: p.fichaje }));
        const pierde = mins.filter((m) => !m.yo && m.sin != null && m.con - m.sin <= -1).sort((x, y) => (x.con - x.sin) - (y.con - y.sin));
        const mI = (k) => { const a = c6.imp.filter((x) => x.di && x.di[k]); return a.length ? a.reduce((s, x) => s + x.di[k].v, 0) / a.length : null; };
        const dUsg = mI("usg_pct"), dPts = mI("pts_p100"), cede = c6.imp.filter((x) => x.di && x.di.usg_pct).sort((a, b) => a.di.usg_pct.v - b.di.usg_pct.v)[0];
        const lead6c = `${pierde.length ? `Sus ${N(c6.fich ? c6.fich.minutos : 0, 0)} minutos salen sobre todo de <b>${E(pierde.slice(0, 3).map((m) => `${m.nom} (${N(m.sin, 0)}' a ${N(m.con, 0)}')`).join(", "))}</b>.` : "Entra sin quitar minutos de forma apreciable a nadie."}${dUsg != null ? ` Con él, sus compañeros cambian de media ${SG0(dUsg, 1)} puntos de USG% y ${SG0(dPts, 1)} puntos por 100 posesiones: ${Math.abs(dUsg) < 0.3 && Math.abs(dPts ?? 0) < 0.3 ? "su llegada apenas mueve sus números" : dUsg < 0 ? "comparten más el balón con él" : "asumen más balón a su lado"}.${cede && cede.di.usg_pct.v <= -0.3 ? ` Quien más balón cede es ${E(nom(cede.o.j.nombre))} (${SG0(cede.di.usg_pct.v, 1)} de USG%).` : ""}` : ""}`;
        const fmtD = (k, o) => { if (!o) return `<td class="num">–</td>`; const v = o.v, sen = o.m ? o.m.sentido : 1, dec = k === "rapm" ? 2 : 1, tol = 0.5 * Math.pow(10, -dec), cls = Math.abs(v) < tol ? "eq" : (sen === 0 ? "neu" : v * sen > 0 ? "up" : "dn");
          return `<td class="num"><b class="${cls}">${SG0(v, dec)}</b></td>`; };
        const maxEnt = c6.imp.length ? Math.max(...c6.imp.map((x) => Math.abs(ESC.dS("nivel", x.ddev)))) : 0;
        const fmtI = (dec, o) => { if (!o) return `<td class="num">–</td>`; const v = o.v, sen = o.m ? o.m.sentido : 1, tol = dec ? 0.05 : 0.5, cls = Math.abs(v) < tol ? "eq" : (sen === 0 ? "neu" : v * sen > 0 ? "up" : "dn");
          return `<td class="num"><b class="${cls}">${SG0(v, dec)}</b><small>${N(o.y, dec)}</small></td>`; };
        const grp = CTX6I.reduce((a, [g]) => { const l = a[a.length - 1]; if (l && l[0] === g) l[1]++; else a.push([g, 1]); return a; }, []);
        const D6 = c6.imp.length ? datos6(c6, j, gm) : null;
        pags.push({ sec: "Contexto y conexiones", num: 6, html: `${ceja(6, "Contexto y conexiones", "Impacto en la plantilla y en sus compañeros", lead6c)}
          <div class="r3cols mn"><div class="r3blk"><h3>Minutos por partido, sin y con él</h3>${svgMinutos(mins, gm)}<p class="r3n">Gris: minutos de cada jugador en la plantilla actual simulada; negro: con ${E(apeJ)} dentro y su rol asignado. Medias de las temporadas simuladas.${notaMin()}</p></div>
            <div class="r3blk"><h3>Lugar en la plantilla por nivel</h3>${rankV(c6.orden || sim.orden, (o) => o.el, d.temporada, true)}<p class="r3n">Nivel por minutos (0–100). De arriba abajo, de más a menos nivel.${notaMin()}</p>
              ${(() => { const PN = { E: "Exteriores", A: "Aleros", I: "Interiores" }, acc = { E: [0, 0], A: [0, 0], I: [0, 0] };
                s2.plantilla.forEach((p) => { const k = p.pos3 in acc ? p.pos3 : null; if (!k) return; acc[k][0] += p.fichaje ? 0 : (p.minutos_sin || 0); acc[k][1] += p.minutos || 0; });
                const fl = Object.keys(acc).filter((k) => acc[k][0] + acc[k][1] > 0); if (!fl.length) return "";
                return `<h3 style="margin-top:14px!important">Minutos por puesto</h3><table class="r3t sim"><thead><tr><th>Puesto</th><th class="num">Sin él</th><th class="num">Con él</th><th class="num">Cambio</th></tr></thead><tbody>${fl.map((k) => { const dlt = acc[k][1] - acc[k][0]; return `<tr class="${k === j.pos3 ? "yo" : ""}"><td>${PN[k]}</td><td class="num">${N(acc[k][0], 0)}'</td><td class="num"><b>${N(acc[k][1], 0)}'</b></td><td class="num">${SG0(dlt, 0)}'</td></tr>`; }).join("")}</tbody></table><p class="r3n">Suma de minutos por partido de cada puesto en la plantilla simulada (${(d.liga === "nba" || d.liga === "gleague") ? 240 : 200}' por partido). En amarillo, su puesto.</p>`; })()}</div></div>

` });
        if (D6) { const svB = svgBalon(D6, apeJ), svJ = svgJuego(D6);
          pags.push({ sec: "Contexto y conexiones", num: 6, html: `${ceja(6, "Contexto y conexiones", "Cómo cambian los números de sus compañeros", lectura6(D6, apeJ))}
          ${svB ? `<div class="r3blk"><h3>De dónde sale su balón</h3>${svB}<p class="r3n">Peso en el ataque: jugadas del equipo que acaba cada uno por partido (USG% × minutos ÷ ${gm}'), sin y con ${E(apeJ)}. Barra naranja, lo que cede cada compañero; negra, lo que asume él; abajo, lo que ceden entre todos. El resto lo ceden compañeros con menos minutos. Medias de las temporadas simuladas.${notaMin()}</p></div>` : ""}
          ${svJ ? `<div class="r3blk"><h3>Cómo cambia el juego de cada compañero</h3>${svJ}<p class="r3n">Cambio previsto de cada métrica al entrar ${E(apeJ)}, en ${E(IFPN())}. El carril gris va de menos a más el cambio de referencia de la columna (±); la barra que llega al borde es un cambio grande y, si lo supera, se corta (›). Azul, mejora; naranja, empeora; violeta, cambio de papel (ni mejor ni peor); sin barra, sin cambio. TOV%: menos es mejor. Entorno: nivel medio de los compañeros de cada uno, escala 0–100. Ocho compañeros con más minutos; valores centrales del modelo de contexto, sin rango.${notaMin()}</p></div>` : ""}` }); }
      }
    } else {
      const A = c.actual || {}, sa = A.sim, nA = A.nec, cl = A.club;
      // v1.6: la misma tabla que con destino (cuadrado: el equipo en su liga; círculo: él en su puesto), en versión densa
      const nR = nA ? nA.filter((x) => x.g !== "estilo") : [], nE = nA ? nA.filter((x) => x.g === "estilo") : [];
      const tabla = nA ? `${tablaNec(nR, cl ? cl.nombre_club : "Su equipo", apeJ, null, 200, false, true)}<p class="r3n">Cuadrado: percentil de ${E(cl ? cl.nombre_club : "su equipo")} entre los clubes de su liga. Círculo: el suyo frente a los ${E(IF_POSN[pos] || "jugadores")} de ${E(IFPN())}. Muestra en qué se apoya hoy su equipo y qué pone él.</p>` : "";
      const tablaE = nE.length ? `<div class="r3blk"><h3>Su estilo frente al de su equipo</h3>${tablaNec(nE, cl ? cl.nombre_club : "Su equipo", apeJ, null, 110, true)}<p class="r3n">Rasgos de estilo, no de calidad: cuánto tira de tres y cuánto pasa frente a lo que hace su equipo.</p></div>` : "<div></div>";
      const rank = sa && sa.orden ? `<div class="r3cols c2"><div class="r3blk"><h3>Su lugar en la plantilla actual por nivel</h3>${rankV(sa.orden, (o) => o.j === j, j.temporada)}${mmIn() ? `<p class="r3n">${notaMin().trim()}</p>` : ""}${sa.qa != null ? `<p class="r3n"><b>Química de su plantilla actual:</b> ${ESC.txt(ESC.dS("sinergia_rapm", sa.qa))} en escala 0–100.</p>` : ""}</div>${tablaE}</div>` : tablaE !== "<div></div>" ? `<div class="r3cols c2"><div></div>${tablaE}</div>` : "";
      pags.push({ sec: "Contexto y conexiones", num: 6, html: `${ceja(6, "Contexto y conexiones", "Papel en su equipo actual", "El baloncesto no es una suma de individualidades: un jugador se entiende junto a sus compañeros. Así encaja hoy en su equipo.")}${tabla}${rank}<p class="r3n">Esta lectura no incluye club de destino: describe su papel en ${E(clubN)}. Con un destino, se añade cómo cambiaría ese equipo con él dentro.</p>` });
    }

    // 7 · glosario
    const G = [["Lectura", "La conclusión de Kerno sobre un jugador para un club concreto, con su razonamiento y su margen de error."], ["Rango", "Entre qué valores es probable que esté una cifra. El rango del 90 % deja fuera solo los escenarios más extremos; el del 50 %, el tramo central."], ["Confianza", "Alta, moderada o baja según la muestra del jugador, el salto de liga y la regularidad de su rendimiento."],
      ["Liga de referencia", `Las cifras se traducen a lo que valdrían en ${IFPN()} (la del club de destino o, sin destino, la suya): su liga = 0. Así se compara con la misma regla a jugadores de competiciones distintas.`], ["Percentil", `De 0 a 100 frente a su puesto en ${IFPN()}: 80 = supera al 80 % de ellos; 50 = el mediano. En los bloques, media de sus percentiles.`], ["Escala 0–100", `Nivel, impacto y química se expresan de 0 a 100; 50 es la media de ${VN()} en nivel, impacto y química. Los cambios, en puntos de esa escala con signo.`],
      ["Nivel Kerno", `De 0 a 100: percentil esperado de su producción (minutos × puntos por 100 posesiones) entre los de su puesto en ${IFPN()}. 50 = fichaje mediano. La banda del gráfico muestra dónde puede moverse. Calibrado con 5.500 fichajes reales.`],
      ["Impacto", "De 0 a 100: percentil del cambio en la diferencia de puntos del equipo con él frente a sin él, entre los fichajes reales de su grupo de ligas. 50 = no cambia al equipo. Calibrado frente al on/off de 4.400 fichajes."],
      ["Net del equipo con él", "Puntos por 100 posesiones que gana o pierde la plantilla con él: valor de cada jugador, parejas y minutos, encogido con 1.149 cambios de plantilla reales. Minutos del motor del Atlas; el modelo se examinó con el motor en servidor."],
      ["Nivel por minutos", `Valoración por eficiencia y producción en la escala 0–100 con ${IFPN()} = 0 (escala anterior a las anclas).`], ["Landing", "Lo que suele perder de valor su grupo de traspaso (p. ej., de EE. UU. a Europa) en la primera temporada por el coste de adaptación, frente al nivel que alcanza una vez adaptado; rango del 80 %. Es una cifra del grupo, no del jugador, y sólo se muestra si el rango excluye 0."], ["Confianza", "Alta, moderada o baja: sale del examen de cada cifra con fichajes reales, nunca del criterio del modelo. Con confianza baja y un rango que incluye 0 se lee «sin cambio apreciable»."],
      ["Rol", "Residual (menos de 5'), Profundidad (5–15'), Rotación (15–22'), Titular (más de 22' y de inicio) y Go-to-guy (referencia ofensiva). En la simulación lo asigna el club."], ["Química", "Cómo se combinan los perfiles de la plantilla por parejas, en escala 0–100."], ["Reparto del balón", "Lo concentrado o repartido que está el uso del balón y el pase: más repartido es más difícil de defender."],
      ["RAPM-EL", "Puntos por 100 posesiones que suma su equipo con él en pista, descontando compañeros y rivales."], ["ORtg / DRtg", "Puntos que produce y que encaja su equipo por 100 posesiones."], ["TS% / eFG%", "Acierto real (cuenta triples y libres) y acierto de campo con el triple valiendo uno y medio."],
      ["USG%", "Parte de las jugadas del equipo que termina él: su peso en el ataque."], ["AST% / TOV%", "Canastas de compañeros que asiste y balones que pierde por cada 100 jugadas que usa."], ["OREB% / DREB%", "Rebotes de ataque y de defensa que captura de los disponibles."], ["STL% / BLK% / STOP%", "Robos, tapones y posesiones rivales que acaba con éxito."], ["3PAr / FTr", "Peso del triple en sus tiros y tiros libres que provoca por cada 100 tiros."]];
    const estG = EUS().map((e) => `<div><dt><i class="r3sw" style="background:${e.color}"></i>${E(e.nombre)}</dt><dd>${E(e.definicion || "")}</dd></div>`).join("");
    pags.push({ sec: "Glosario", html: `${ceja(7, "Glosario", "Términos y escalas", "")}<dl class="r3glos">${G.map(([a, t]) => `<div><dt>${E(a)}</dt><dd>${E(t)}</dd></div>`).join("")}</dl>` });
    pags.push({ sec: "Glosario", num: 7, html: `${ceja(7, "Glosario", "Estilos de juego y ligas", "")}
      <div class="r3blk"><h3>Estilos de juego</h3><dl class="r3glos est">${estG}</dl></div>
      ${ligasVara(j, d)}
      <p class="r3n">Fuentes: actas oficiales y jugada a jugada de cada competición (liga regular), datos públicos a ${E(fecha)}. Modelos y simulación de Kerno Analytics. Una temporada es una muestra: con menos de 500 minutos las cifras oscilan mucho.</p>` });
    pags.push({ portada: true, back: true, html: `<img src="${INF_LOGO.vn}" alt="KERNO Analytics" class="cvback-logo"><p class="cvclaim">Make the right read.</p><p class="cvfine">Kerno Analytics · Documento confidencial</p>` });
    const Nn = pags.length; let num = 0;
    pags.forEach((p) => { if (p.portada) return; if (p.num == null) p.num = num + 1; num = p.num; });
    const vistos = new Set();
    pags[0].html = pags[0].html.replace("#INDICE#", pags.map((p, i) => { if (p.portada || vistos.has(p.num)) return ""; vistos.add(p.num); return `<li><span>${String(p.num).padStart(2, "0")}</span><span>${E(p.sec)}</span><b>${i + 1}</b></li>`; }).join(""));
    return pags.map((p, i) => hoja(p.html, { ...p, n: i + 1, N: Nn, fecha, extra }));
  }

  // ------------------------------------------------------------------------------------------- 5b. datos de la sección 06
  // Plantilla del destino tal como la simula el motor (minutos sin y con el fichaje) emparejada con los registros del
  // Atlas para usar la química por parejas y el contexto de compañeros (mismas funciones que «Simular equipo completo»).
  let JGPID = null;
  function jgDe(key) {
    if (!JGPID) { JGPID = new Map(); JG.forEach((x) => { const k = `${x.liga}|${x.temporada}|${x.pid}`, o = JGPID.get(k); if (!o || x.min > o.min) JGPID.set(k, x); }); }
    return key ? JGPID.get(key) || null : null;
  }
  const CTX6 = ["ortg", "drtg", "ts_pct", "rapm"];
  // «Cómo cambian los números de sus compañeros» (decisión del CEO, 04-11-2026): métricas individuales del modelo de
  // contexto en lugar de ratings y RAPM. Grupo, clave, nombre corto y decimales; el TS% no entra (su sensibilidad al
  // entorno es 0 en el modelo: nunca cambia)
  const CTX6I = [["Uso", "usg_pct", "USG%", 1], ["Anotación y tiro", "pts_p100", "Pts/100", 1], ["Anotación y tiro", "efg_pct", "eFG%", 1],
    ["Creación", "ast_pct", "AST%", 1], ["Creación", "tov_pct", "TOV%", 1], ["Rebote", "oreb_pct", "OREB%", 1], ["Rebote", "dreb_pct", "DREB%", 1], ["Cómo anota", "pct_asistidas", "% asistidas", 0]];
  const yLista = (xs) => xs.length <= 1 ? xs.join("") : `${xs.slice(0, -1).join(", ")} y ${xs[xs.length - 1]}`;
  const CTXN_R = { ortg: ["ORtg"], drtg: ["DRtg"], ts_pct: ["TS%"], usg_pct: ["USG%"], ast_pct: ["AST%"], rapm: ["RAPM-EL"] };
  // minutos mínimos (temporada) para que un compañero entre en el informe; el jugador del informe siempre entra
  const mmIn = () => (typeof ifMinMin === "function" ? ifMinMin() : 0);
  const okMin = (x) => { const m = mmIn(); return !m || !!(x && (x.min || 0) >= m); };
  const notaMin = () => { const m = mmIn(); return m ? ` Solo compañeros con ${m} minutos o más en la temporada.` : ""; };
  function contexto6(j, d, s2, extras, bajas) {
    try {
      const club = simClub(d); if (!club || !s2 || !Array.isArray(s2.plantilla)) return null;
      const keyDe = new Map((club.plantilla || []).map((x) => [x[3], x[0]])); (extras || []).forEach((r) => keyDe.set(r.persona, r.id));
      const tm = s2.plantilla.filter((p) => !p.fichaje).map((p) => ({ p, j: jgDe(keyDe.get(p.persona)) })).filter((o) => o.j && o.j !== j);
      const fich = s2.plantilla.find((p) => p.fichaje); if (!tm.length) return null;
      const temp = d.temporada;
      const filasSin = tm.filter((o) => o.p.minutos_sin > 0).map((o) => ({ j: o.j, w: o.p.minutos_sin }));
      const filasCon = tm.filter((o) => o.p.minutos > 0).map((o) => ({ j: o.j, w: o.p.minutos })).concat([{ j, w: fich ? fich.minutos : 0 }]);
      const q = hayQ(), ref = q ? synRef() : null;
      const pares = q ? tm.filter((o) => o.p.minutos > 0.5 && okMin(o.j)).map((o) => { const r = sinJ(j, o.j), v = r.total - ref, pp = partes(r); return { o, v, S: ESC.dS("sinergia_rapm", v), est: ESC.dS("sinergia_rapm", pp.est), niv: ESC.dS("sinergia_rapm", pp.niv) }; }).sort((a, b) => b.v - a.v) : [];
      const c = hayC();
      const imp = c && filasSin.length ? tm.filter((o) => o.p.minutos > 0.5 && okMin(o.j)).slice(0, 10).map((o) => { const ds = devDestino(filasSin, o.j, temp), dc = devDestino(filasCon, o.j, temp), A = proyectar(o.j, ds), B = proyectar(o.j, dc), dd = {};
        CTX6.forEach((k) => { const a = A.out[k], b = B.out[k]; dd[k] = a && b && a.y != null && b.y != null ? { v: b.y - a.y, m: b.m } : null; });
        // métricas individuales en la escala de la liga de referencia (enVara): valor con él y cambio frente a sin él
        const di = {}; CTX6I.forEach(([, k]) => { const a = A.out[k], b = B.out[k]; if (!a || !b || a.y == null || b.y == null) { di[k] = null; return; }
          const ya = enVara(k, a.y, o.j), yb = enVara(k, b.y, o.j); di[k] = isFinite(ya) && isFinite(yb) ? { v: yb - ya, y: yb, m: b.m } : null; });
        return { o, dd, di, ddev: dc - ds }; }) : [];
      const yo = c ? proyectar(j, devDestino(filasCon, j, temp)) : null;
      const qs = (s2.equipo && s2.equipo.quintetos) || [], q1 = qs.find((x) => x.con_fichaje);
      const mapSel = (ids) => ids.map((per) => per === s2.persona ? { j, p: fich } : (() => { const o = tm.find((t) => t.p.persona === per); return o ? { j: o.j, p: o.p } : null; })());
      let q5 = null;
      if (q && q1) { const sel = mapSel(q1.jugadores); if (sel.every(Boolean)) q5 = { q: quinteto(sel), sel, prob: q1.prob, modo: "con" }; }
      else if (q && qs[0]) { const base = mapSel(qs[0].jugadores);
        if (base.every(Boolean)) { const cand = base.filter((x) => x.j.pos3 === j.pos3), pool = cand.length ? cand : base, fuera = pool.slice().sort((a, b) => a.p.minutos - b.p.minutos)[0], alt = base.map((x) => x === fuera ? { j, p: fich } : x);
          q5 = { q: quinteto(alt), sel: alt, prob: qs[0].prob, modo: "por", fuera, base: quinteto(base) }; } }
      const refPar = q && filasSin.length > 1 ? quimicaPlantilla(filasSin).pares.sort((a, b) => b.v - a.v)[0] : null;
      const lw = (f) => { let a = 0, w = 0; f.forEach((o) => { a += o.w * Lof(o.j); w += o.w; }); return w ? a / w : null; };
      const orden = tm.filter((o) => o.p.minutos > 0.5 && okMin(o.j)).map((o) => ({ j: o.j, L: Lof(o.j) })).concat([{ j, L: Lof(j), el: true }]).sort((a, b) => b.L - a.L);
      const quitados = (club.plantilla || []).filter((x) => bajas && bajas.has(x[3])).map((x) => (SIMD.jug.get(x[0]) || {}).nombre).filter(Boolean);
      const okPer = new Set(tm.filter((o) => okMin(o.j)).map((o) => o.p.persona));
      // «Ranking frente a su liga» (CEO, 04-11-2026): mismo cálculo que el ranking del planificador de plantilla completa.
      // Nivel de caja del equipo (equipoDe: rasgos de los jugadores ponderados por los minutos del simulador) frente a los
      // clubes de la liga de referencia en su última temporada completa (elClubs), en la escala 0–100 (sNivCL(Lclub(·))).
      let rkL = null;
      try {
        // Temporada del ranking (CEO, 06-11-2026): SIEMPRE la liga de la temporada en la que se integra el jugador (la del club de
        // destino), aunque esté en curso; solo si esa temporada no tiene clubes con nivel se usa la última completa.
        const ELd = CL.filter((c) => c.liga === d.liga && c.temporada === d.temporada && c.nivel != null && isFinite(c.nivel)), usarD = ELd.length >= 3;
        const EL = usarD ? ELd.slice().sort((a, b) => b.nivel - a.nivel) : elClubs(), tEL = usarD ? d.temporada : ultCompleta(), prov = usarD && META.temporadas_provisionales.includes(tEL);
        const nv = (fs) => { const fl = fs.filter((o) => o.w > 0), e = fl.length ? equipoDe(fl.map((o) => ({ ...valsJ(o.j, "n"), w: o.w }))) : null;
          return e ? { v: sNivCL(Lclub(e.L), tEL), eu: (euComp(fl) || {}).eu } : null; };
        const S = nv(filasSin), C2 = nv(filasCon), propio = EL.find((c) => c.clave_club === d.clave_club) || null;
        if (S && C2 && EL.length > 2) {
          const clubs = EL.filter((c) => c !== propio).map((c) => ({ nom: c.nombre_club, v: sNivCL(Lclub(c.nivel), tEL), eu: c.eu })).filter((c) => c.v != null);
          const rk = (v) => 1 + clubs.filter((c) => c.v > v).length;
          rkL = { tEL, prov, liga: EL[0].liga, ligaN: ESC.varaNom(EL[0].liga), clubs, sin: { ...S, rk: rk(S.v) }, con: { ...C2, rk: rk(C2.v) }, n: clubs.length + 1,
            real: propio ? { v: sNivCL(Lclub(propio.nivel), tEL), rk: rk(sNivCL(Lclub(propio.nivel), tEL)), nom: propio.nombre_club } : null };
        }
      } catch (e) { rkL = null; }
      return { rkL, tm, okPer, pares, imp, yo, q5, fich, refPar, orden, qa: q && filasSin.length > 1 ? quimicaPlantilla(filasSin).idx : null, qd: q && filasCon.length > 1 ? quimicaPlantilla(filasCon).idx : null,
        nivSin: lw(filasSin), nivCon: lw(filasCon), quitados, anadidos: (extras || []).map((r) => r.nombre) };
    } catch (e) { console.warn("Sección 06:", e); return null; }
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
    if (s.sim) { d = ifClub(s.dClub, s.dTemp); await ifCargarEq(); if (d) sim = conVara(d.liga, () => ifSimular(j, d)); }   // química y nivel frente a la liga de destino
    if (sim && sim.orden) sim.orden = sim.orden.filter((o) => o.el || o.j === j || okMin(o.j));
    // rol asignado: el elegido para este jugador-destino; por defecto, su rol de partida
    const rol0 = rolDeRec(recJ) || rolEstimado(j, R0 && R0.b) || "ROTACION";
    const rol = (st.inf.rol && st.inf.rolDe === claveNota() && ROLES.includes(st.inf.rol)) ? st.inf.rol : rol0;
    if ($1("#ifRol")) $1("#ifRol").value = rol;
    let bajas = new Set(), extras = [], clubS = null;
    if (sim && !sim.mismo && recJ && SIMD && !SIMD.error) { clubS = simClub(d); if (clubS) { const sel = plantSel(); bajas = new Set(sel.fuera); const enClub = new Set((clubS.plantilla || []).map((x) => x[3])); extras = sel.extra.map((id) => SIMD.jug.get(id)).filter((r) => r && !enClub.has(r.persona));
      try { s2 = SIM2.simular({ rec: recJ, club: clubS, bajas, extras, rol }); } catch (e) { s2 = { error: e.message }; } } }
    pintarPlant(clubS, recJ);
    if (tok !== IFTOK) return;
    if (!R0) { box.classList.remove("cargando"); box.innerHTML = `<p class="note">Sin datos detallados de ${E(nom(j.nombre))} en ${E(j.temporada)}.</p>`; return; }
    const R = { ...R0, ref: D.ref, pool_de: D.pool_de, min_pool: D.min_pool, pool_n: D.pool_n, liga: j.liga, ligas: D.ligas };
    const pos = ["E", "A", "I"].includes(j.pos3) ? j.pos3 : "A";
    const tray = JG.filter((x) => x.persona_id === j.persona_id).sort((a, x) => a.temporada.localeCompare(x.temporada) || x.min - a.min);
    const med = await medias(tray); if (tok !== IFTOK) return;
    const fecha = new Date().toLocaleDateString("es-ES", { day: "numeric", month: "long", year: "numeric" });
    const notaFin = ($1("#ifPorqueFinal") && $1("#ifPorqueFinal").value.trim()) || ($1("#ifPorque") && $1("#ifPorque").value.trim()) || "";
    const nacT = tray.map((x) => (simRec(x) || {}).nac).find(Boolean);
    let actual = null; if (!(sim && !sim.mismo)) { try { await ifCargarEq(); const cl = BY.get(j.clave); if (cl) { const sa = conVara(cl.liga, () => ifSimular(j, cl)); if (sa && sa.orden) sa.orden = sa.orden.filter((o) => o.el || o.j === j || okMin(o.j)); actual = { club: cl, nec: ifNecesidades(cl, R), sim: sa }; } } catch (e) { actual = null; } }
    let esc = [];
    if (s2 && !s2.error) { const club = simClub(d); esc = ROLES.map((r) => { try { const x = r === rol ? s2 : SIM2.simular({ rec: recJ, club, bajas, extras, rol: r }); return x && !x.error ? { rol: r, r: x } : null; } catch (e) { return null; } }).filter(Boolean); }
    const c6 = s2 && !s2.error && d ? conVara(d.liga, () => contexto6(j, d, s2, extras, bajas)) : null;
    // v4.0 (05-11-2026) · anclas NIVEL KERNO e IMPACTO y Δ̂Net de la capa 4 (atlas/v40.js) con los minutos del motor del Atlas:
    // en el club de destino con el rol elegido o, sin destino, en su club actual (simulación con su propia plantilla).
    let an = null, anEsc = [], anCtx = null;
    if (window.CernoV40 && CernoV40.listo() && recJ) {
      try {
        if (s2 && !s2.error && clubS) { an = CernoV40.anclasFichaje(s2, recJ, clubS); anCtx = { club: clubS, d, propio: false, rol }; anEsc = esc.map((o) => ({ rol: o.rol, r: o.r, a: o.r === s2 ? an : CernoV40.anclasFichaje(o.r, recJ, clubS) })); }
        else if (!(sim && !sim.mismo)) { const cl = BY.get(j.clave), cs = cl ? simClub(cl) : null;
          if (cs) { const rolP = rol, r0 = SIM2.simular({ rec: recJ, club: cs, rol: rolP }); if (r0 && !r0.error) { an = CernoV40.anclasFichaje(r0, recJ, cs); anCtx = { club: cs, d: cl, propio: true, rol: rolP, res: r0 };
            anEsc = ROLES.map((rr) => { try { const x = rr === rolP ? r0 : SIM2.simular({ rec: recJ, club: cs, rol: rr }); return x && !x.error ? { rol: rr, r: x, a: rr === rolP ? an : CernoV40.anclasFichaje(x, recJ, cs) } : null; } catch (e) { return null; } }).filter(Boolean); } } }
      } catch (e) { console.error("v4.0:", e); an = null; anEsc = []; anCtx = null; }
    }
    // referencia del informe (decisión del usuario, 04-11-2026): 0 = la liga del club de destino; sin destino, la de su liga
    const ligaRef = sim && !sim.mismo && d ? d.liga : j.liga;
    const Rv = enLigaR(R, j, ligaRef);
    // carencias del club (v1.6): el jugador, en percentil de su puesto en la liga de referencia (la del destino o la suya)
    if (sim && !sim.mismo) nec = ifNecesidades(d, Rv);
    if (actual && actual.club) actual.nec = ifNecesidades(actual.club, Rv);
    const hojas = conVara(ligaRef, () => { const h = paginas({ j, R: Rv, pos, sim, s2: s2 && !s2.error ? s2 : null, nec, fecha, tray, medias: med, nota: notaFin, rol, nac: pais(nacT), esc, ritmo: Rv.ritmo_liga || D.ritmo_el || 72, actual, c6, an, anEsc, anCtx }); rotular("p-informe"); return h; });
    box.innerHTML = hojas.map((h) => `<div class="ifwrap">${h}</div>`).join("");
    box.classList.remove("cargando"); ifEscalar();
    $1("#ifSimNota").innerHTML = s.sim ? (sim && sim.mismo ? `<span class="warn">Ya juega en ese club esa temporada: elige otro destino.</span>` : s2 && s2.error ? `<span class="warn">No se pudo simular (${E(s2.error)}).</span>` : !s2 && sim ? `<span class="warn">El simulador no tiene plantilla de ese club y temporada (hay de 2025-26 y 2026-27): se muestra la lectura sin simulación de rol.</span>` : "") : "";
    IFULT = { nom: nom(j.nombre), temp: j.temporada, dest: sim && !sim.mismo ? sim.d.nombre_club : null };
    $1("#ifResumen").textContent = `${hojas.length} páginas A4 · ${nom(j.nombre)}${IFULT.dest ? ` · destino ${IFULT.dest}` : ""}`;
    // contexto para la redacción en tono Kerno (solo datos del propio informe)
    const club = BY.get(j.clave), pL = R.m.L ? R.m.L[2] : null;
    ULT = { ctx: [`Jugador: ${nom(j.nombre)}, ${IF_POS1[pos] || "jugador"}, ${j.edad != null ? Math.round(j.edad) + " años" : "edad s/d"}, ${club ? club.nombre_club : j.nombre_club} (${LIGAS[j.liga] || j.liga} ${j.temporada}).`,
      `Estilo: ${euLab(j)}. Nivel: ${etiqueta(pL)}${pL != null ? ` (percentil ${Math.round(pL)} en su puesto)` : ""}.`,
      sim && !sim.mismo ? `Destino: ${sim.d.nombre_club} (${LIGAS[sim.d.liga] || sim.d.liga} ${sim.d.temporada}), rol asignado ${ROLN[rol]}.` : "Sin club de destino.",
      s2 && !s2.error ? `Simulación: ${N(s2.minutos.media, 0)} minutos por partido.${lgI0(s2) ? ` Landing de su grupo de traspaso: ${lgI0(s2)}.` : ""}` : "",
      nec ? `Cubre carencias del equipo en: ${nec.filter((x) => x.v[1] === "Cubre una carencia").map((x) => x.n.toLowerCase()).join(", ") || "ninguna clara"}.` : ""].filter(Boolean).join("\n") };
  }
  pintarInforme = pintarV3;            // el resto de la página (controles, PDF, HTML) llama a esta función por su nombre
  window.CernoInformeV3 = { version: "3.3", indice, paginas };

  // ------------------------------------------------------------------------------------------- 7. estilos (pantalla, PDF e HTML imprimible)
  const CSS3 = `
.ifsheet.r3{--i:#0C1210;--i2:#3F4B45;--mu:#56625C;--fa:#707B75;--ln:#CFD5D0;--l2:#B2BAB5;--s2:#E3E7E2;--up:#2B6FBF;--dn:#D35C2A;--vi:#6550CC;font:400 10px/1.45 "Mona Sans",system-ui,sans-serif;color:var(--i)}
.ifsheet.r3 .r3head{display:flex;gap:10px;align-items:center;padding:30px 52px 9px;font:500 6.6px/1 "Geist Mono",ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--mu);border-bottom:1.2px solid var(--i)}
.ifsheet.r3 .r3head span:nth-child(2){margin-left:auto;color:var(--i2)}.ifsheet.r3 .r3head .r3hsec{color:var(--i);font-weight:600}
.ifsheet.r3 .r3body{padding:22px 52px 8px;gap:16px}
.ifsheet.r3 .r3foot{display:flex;align-items:center;gap:14px;padding:9px 52px 26px;border-top:.6px solid var(--l2);font:500 6.6px "Geist Mono",ui-monospace,monospace;letter-spacing:.08em;color:var(--mu);text-transform:uppercase}
.ifsheet.r3 .r3foot span:last-child{margin-left:auto;color:var(--i)}
.ifsheet.r3 .r3foot .ifscale{display:inline-flex;align-items:flex-end;height:9px}.ifsheet.r3 .r3foot .ifscale i{display:block;width:.6px;height:4px;margin-right:4.8px;background:#707B75}.ifsheet.r3 .r3foot .ifscale i.M{height:7px}.ifsheet.r3 .r3foot .ifscale i.on{width:1.8px;height:9px;background:#0F2E25}
.r3secw{display:grid;gap:0}.r3sec{display:flex;justify-content:space-between;gap:18px;align-items:center;background:#0F2E25;padding:10px 16px 11px}
.r3ceja{font:500 7.4px "Geist Mono",ui-monospace,monospace;letter-spacing:.1em;text-transform:uppercase;color:#8F9993}
.r3sec.ink h2{font:620 24px/1.12 "Mona Sans",sans-serif!important;letter-spacing:-.02em!important;margin:4px 0 0!important;max-width:560px;text-transform:none!important;color:#8A6B35!important}
.r3sec.ink .r3num{font:250 38px/1 "Mona Sans",sans-serif;color:#707B75;letter-spacing:-.02em}
.r3lead{font:400 13.4px/1.45 "Mona Sans", sans-serif;color:var(--i2);margin-top:9px!important;max-width:620px}
.r3p{font:400 11.8px/1.5 "Mona Sans",sans-serif;color:var(--i2);margin:0 0 7px!important}
.r3n{font:400 9.4px/1.45 "Mona Sans",sans-serif;color:var(--mu);margin-top:5px!important}
.r3lab,.r3tag{display:block;font:500 7.2px "Geist Mono",ui-monospace,monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--mu);margin-bottom:6px}
.r3cols{display:grid;grid-template-columns:1.15fr 1fr;gap:20px}.r3cols.c2{grid-template-columns:1fr 1fr}
.r3blk h3{font:620 12.4px/1.25 "Mona Sans",sans-serif!important;letter-spacing:-.005em!important;margin:0 0 6px!important;padding-top:7px;border-top:.9px solid var(--i);text-transform:none!important}
.r3q dl{display:grid;gap:7px;margin:0}.r3q dl div{display:grid;grid-template-columns:72px 1fr;gap:8px;border-top:.5px solid var(--l2);padding-top:6px}.r3q dt{font:620 11px "Mona Sans",sans-serif}.r3q dd{margin:0;font-size:10.6px;color:var(--i2)}.r3q em{color:var(--mu)}
.r3steps ol{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(4,1fr);gap:14px;counter-reset:p}.r3steps li{counter-increment:p;border-top:.9px solid var(--i);padding-top:7px}
.r3steps li::before{content:"0" counter(p);display:block;font:500 7.4px "Geist Mono",monospace;color:var(--mu);margin-bottom:4px}.r3steps b{display:block;font:620 11.6px/1.2 "Mona Sans",sans-serif;margin-bottom:4px}.r3steps span{font-size:10.4px;color:var(--i2);line-height:1.45}
.r3call{background:#0F2E25;color:#F3F4F0;padding:12px 16px}.r3call.callout .r3tag{color:#8A6B35;border:1px solid #8A6B35;display:inline-block;padding:2px 6px}.r3call p{font:400 13px/1.45 "Mona Sans", sans-serif;margin:4px 0 0!important}
.r3id{display:grid;grid-template-columns:repeat(6,1fr);gap:0;margin:0;border-top:.9px solid var(--i)}.r3id div{padding:7px 8px 6px 0;border-right:.5px solid var(--l2)}.r3id div:last-child{border:0}
.r3id dt{font:500 7.4px "Geist Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--mu)}.r3id dd{margin:3px 0 0;font:620 12px/1.2 "Mona Sans",sans-serif}
.r3t{width:100%;border-collapse:collapse;font-size:10.4px}.r3t th{font:500 7.4px "Geist Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--mu);text-align:left;padding:0 6px 5px 0;border-bottom:.9px solid var(--i)}
.r3t td{padding:5px 6px 5px 0;border-bottom:.5px solid var(--l2);vertical-align:middle}.r3t td small{display:block;font-size:8.4px;color:var(--mu);line-height:1.25;margin-top:1px}.r3t .num{text-align:right;font-family:"Geist Mono",ui-monospace,monospace;white-space:nowrap}.r3t.sim{font-size:9.8px}
.r3t td.num small{font-family:"Geist Mono",monospace}.r3t tr.yo td{background:#DCE7E2}.r3t td b.up{color:var(--up)}.r3t td b.dn{color:var(--dn)}
.r3t.tray td{padding:5px 6px 5px 0}.r3t.tray td:nth-child(2) small{display:inline;margin-left:5px}
.r3t td.ver{font-weight:600;font-size:9.8px}.r3t td.ver.up{color:var(--up)}.r3t td.ver.dn{color:var(--dn)}
.r3t.nec2 td{padding:5.5px 8px 5.5px 0;vertical-align:middle}.r3t.nec2 td:first-child b{font-size:11.2px}.r3t.nec2 td.num{font:600 12px "Geist Mono",monospace;text-align:right;width:46px}.r3t.nec2 td.num b{font-size:13px}.r3t.nec2 tr.top td{background:#DCE7E2}
.r3t.nec2.corta td{padding:4px 6px 4px 0}.r3t.nec2.densa td{padding:2px 8px 2px 0}.r3t.nec2.densa td:first-child b{font-size:10.4px}.r3t.nec2.densa td small{font-size:7.6px;line-height:1.15}.r3t.nec2.densa .r3chip{padding:1.5px 6px;font-size:8.6px}.r3t.nec2.corta td:first-child b{font-size:10.4px}.r3t.nec2.corta td small{font-size:8px}
.r3nec{display:block}.r3nec .tr{stroke:#B2BAB5;stroke-width:1.2}.r3nec .tk{stroke:#CFD5D0;stroke-width:.8}.r3nec .rf{stroke:#707B75;stroke-width:.8;stroke-dasharray:1.5 1.5}.r3nec .gap{stroke:#8F9993;stroke-width:3;opacity:.45}.r3nec .gap.up{stroke:#2B6FBF}.r3nec .gap.dn{stroke:#D35C2A}.r3nec .gap.neu{stroke:#6550CC}
.r3nec .eq{fill:#F3F4F0;stroke:#0C1210;stroke-width:1.4}.r3nec .pt{fill:#0C1210}.r3nec .pt.up{fill:#2B6FBF}.r3nec .pt.dn{fill:#D35C2A}.r3nec .pt.neu{fill:#6550CC}
.r3necl{display:inline-flex;align-items:center;gap:5px;text-transform:none;letter-spacing:0}.r3necl i{display:inline-block;width:8px;height:8px}.r3necl i.eq{border:1.3px solid #0F2E25;background:#F3F4F0}.r3necl i.pt{border-radius:50%;background:#0F2E25;margin-left:6px}
.r3chip{display:inline-block;font:600 9.2px "Mona Sans",sans-serif;padding:2.5px 7px;border-radius:2px;border:1px solid #B2BAB5;color:#56625C;white-space:nowrap}.r3chip.up{border-color:#2B6FBF;color:#1F4A3D;background:rgba(15, 46, 37, .10)}.r3chip.dn{border-color:#D35C2A;color:#0C1210;background:rgba(211, 92, 42,.10)}
.r3kp.r3neck small{display:block;line-height:1.3}.r3kp.r3neck b.up{color:var(--up)}.r3kp.r3neck b.dn{color:var(--dn)}
.r3pr{display:block}.r3pr .tr{stroke:#B2BAB5;stroke-width:1}.r3pr .rf{stroke:#707B75;stroke-width:.8;stroke-dasharray:1.5 1.5}.r3pr .bd{fill:rgba(15, 46, 37, .14)}.r3pr .pt{fill:#0C1210}.r3pr .pt.up{fill:#2B6FBF}.r3pr .pt.dn{fill:#D35C2A}.r3pr .pt.neu{fill:#6550CC}
.r3na{font-size:8px;color:var(--fa)}
.r3sw{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;vertical-align:0}
.r3rol{display:inline-block;font:500 7.6px "Geist Mono",monospace;letter-spacing:.04em;border:.6px solid #B2BAB5;padding:1px 5px;white-space:nowrap}.r3rol.r-titular,.r3rol.r-go_to_guy{border-color:#0C1210;font-weight:600}
.r3est{display:grid;grid-template-columns:210px 1fr;gap:16px;align-items:start;border-top:.9px solid var(--i);padding-top:8px}.r3est b{display:block;font:620 16px "Mona Sans",sans-serif}.r3est small{display:block;font-size:9.4px;color:var(--mu);margin-top:2px}.r3est p{font:400 12.6px/1.45 "Mona Sans", sans-serif;color:var(--i2);margin:0}
.r3kp{display:grid;grid-template-columns:repeat(4,1fr);border-top:.9px solid var(--i);border-bottom:.5px solid var(--l2)}.r3kp.big{grid-template-columns:1.2fr repeat(4,1fr)}
.r3kp>div{padding:8px 10px 8px 0;border-right:.5px solid var(--l2);margin-right:10px}.r3kp>div:last-child{border:0;margin:0}
.r3kp span{display:block;font:500 7.4px "Geist Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--mu)}.r3kp b{display:block;font:620 25px/1.1 "Mona Sans",sans-serif;letter-spacing:-.02em;margin:4px 0 2px}.r3kp b.r3w{font-size:13px;line-height:1.4}
.r3kp .idx{border-left:2pt solid #0F2E25;padding-left:10px}.r3kp .idx b{font-size:34px}.r3kp small{display:block;font-size:8.6px;color:var(--mu);line-height:1.3}.r3kp b.up{color:var(--up)}.r3kp b.dn{color:var(--dn)}
.r3l{list-style:none;padding:0;margin:0;display:grid;gap:5px}.r3l li{display:grid;gap:1px;padding-left:9px;border-left:2px solid #B2BAB5}.r3l.up li{border-left-color:#2B6FBF}.r3l.dn li{border-left-color:#D35C2A}.r3l b{font:620 10.8px "Mona Sans",sans-serif}.r3l span{font-size:10px;color:var(--i2)}
.r3why{background:#163B30;color:#F3F4F0;padding:12px 16px 10px}.r3why.callout .r3tag{color:#8A6B35;border:1px solid #8A6B35;display:inline-block;padding:2px 6px}.r3why p{font:400 12.6px/1.5 "Mona Sans", sans-serif;margin:3px 0 6px!important}.r3why .r3vacio{color:#8F9993;font-style:italic}
.r3cv{width:100%;height:auto;display:block}.r3cv .rf{stroke:#707B75;stroke-dasharray:2 2;stroke-width:.8}.r3cv .bd{fill:rgba(15, 46, 37, .10)}.r3cv .ln{fill:none;stroke:#0C1210;stroke-width:1.4}.r3cv .ax{font:500 7px "Geist Mono",monospace;fill:#56625C}
.r3blk .ifcourt{width:100%;height:auto}.r3blk .ifcourt .zn{font:600 8px "Mona Sans",sans-serif;fill:#0C1210;text-anchor:middle}.r3blk .ifcourt .zv{font:600 11px "Geist Mono",monospace;fill:#0C1210;text-anchor:middle}.r3blk .ifcourt .zm,.r3blk .ifcourt .zf{font:500 7px "Geist Mono",monospace;fill:#56625C;text-anchor:middle}
.r3kp.t2{grid-template-columns:1fr 1fr}.r3kp b i{font-style:normal;color:var(--mu);font-weight:400}.r3rkb{margin-top:2px}.r3rkb .r3p{font-size:9.6px;line-height:1.45}.r3rkl{display:block;width:100%;height:auto}.r3rkl .gr{stroke:#CFD5D0;stroke-width:.6}.r3rkl .z{stroke:#8F9993;stroke-width:.8}.r3rkl .ax{font:500 6.6px "Geist Mono",monospace;fill:#56625C;text-anchor:middle}.r3rkl text.n{font:500 7.2px "Geist Mono",monospace;fill:#707B75}.r3rkl text.nm{font:400 8.2px "Mona Sans",sans-serif;fill:#2B3631}.r3rkl text.b{font-weight:650;fill:#0C1210}.r3rkl text.v{font:500 7.6px "Geist Mono",monospace;fill:#56625C;text-anchor:end}.r3rkl text.v.b{fill:#0C1210;font-weight:650}.r3rkl rect.con{fill:#DCE7E2}.r3rkl rect.sin{fill:rgba(12, 18, 16,.06)}.r3rkl .bar{stroke:#B2BAB5;stroke-width:2.4;stroke-linecap:round}.r3rkl .bar.sin{stroke:#707B75;stroke-width:3.4}.r3rkl .bar.con{stroke:#0C1210;stroke-width:3.8}.r3rkl .pt{stroke:#F3F4F0;stroke-width:.9}.r3rkl .pt.sin{fill:#56625C}.r3rkl .pt.con{fill:#8A6B35;stroke:#0C1210;stroke-width:1.2}.r3rank{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:1fr}.r3rank li{display:grid;grid-template-columns:20px 1fr auto;gap:6px;padding:2.5px 0;border-bottom:.5px solid #B2BAB5;font-size:10px}.r3rank li span:first-child{font-family:"Geist Mono",monospace;color:#56625C}.r3rank li b{font-family:"Geist Mono",monospace;font-weight:500}.r3rank li.yo{background:#DCE7E2;font-weight:620}.r3rank li.pos span:nth-child(2){color:#0C1210}
.r3t.q5 td{font-size:9.8px}
.r3glos{display:grid;grid-template-columns:1fr 1fr;column-gap:22px;row-gap:0;margin:0}.r3glos div{display:grid;grid-template-columns:96px 1fr;gap:8px;padding:5px 0;border-bottom:.5px solid #B2BAB5}.r3glos dt{font:620 10px "Mona Sans",sans-serif}.r3glos dd{margin:0;font-size:9.4px;color:var(--i2);line-height:1.4}.r3glos.est div{grid-template-columns:86px 1fr}
.ifsheet.r3.cover{background:#0F2E25;color:#F3F4F0}.ifsheet.r3.cover .ifbody{padding:58px 62px 46px;display:flex;flex-direction:column;justify-content:space-between;position:relative;height:100%}
.ifsheet.r3.cover .cvtop{display:flex;justify-content:space-between;align-items:center}.ifsheet.r3.cover .cvlogo{height:40px;width:auto;display:block}.ifsheet.r3.cover .cvk{font:500 7.6px "Geist Mono",monospace;letter-spacing:.12em;text-transform:uppercase;color:#B2BAB5}
.ifsheet.r3.cover h1{font:620 46px/1.04 "Mona Sans",sans-serif!important;letter-spacing:-.03em!important;color:#F3F4F0;margin:0!important;text-transform:none!important}
.ifsheet.r3.cover h1 .hl{color:#0C1210;background:linear-gradient(transparent 10%,#8A6B35 10%,#8A6B35 92%,transparent 92%);padding:0 .1em;-webkit-box-decoration-break:clone;box-decoration-break:clone}
.ifsheet.r3.cover .cvdat{font:400 14px/1.45 "Mona Sans", sans-serif;color:#B2BAB5;margin-top:14px!important}
.ifsheet.r3.cover .cvfacts{display:grid;grid-template-columns:repeat(4,1fr);margin-top:26px!important;border-top:1.2px solid #F3F4F0}.ifsheet.r3.cover .cvfacts div{padding:8px 10px 0 0}.ifsheet.r3.cover .cvfacts dt{font:500 6.8px "Geist Mono",monospace;letter-spacing:.1em;text-transform:uppercase;color:#8F9993}.ifsheet.r3.cover .cvfacts dd{margin:4px 0 0;font:500 11px "Geist Mono",monospace;color:#F3F4F0}
.ifsheet.r3.cover .cvidx{list-style:none;padding:0;margin:0;display:grid;gap:0;max-width:330px}.ifsheet.r3.cover .cvidx li{display:grid;grid-template-columns:24px 1fr auto;gap:8px;padding:5px 0;border-bottom:.5px solid #3F4B45;font:500 9.4px "Mona Sans",sans-serif;color:#B2BAB5}.ifsheet.r3.cover .cvidx li span:first-child,.ifsheet.r3.cover .cvidx li b{font:500 8px "Geist Mono",monospace;color:#8F9993}
.ifsheet.r3.cover .cvbot{display:grid;grid-template-columns:1.4fr 1fr 1fr;gap:14px;border-top:.6px solid #3F4B45;padding-top:10px}.ifsheet.r3.cover .cvbot span{display:block;font:500 6.6px "Geist Mono",monospace;letter-spacing:.1em;text-transform:uppercase;color:#8F9993}.ifsheet.r3.cover .cvbot b{display:block;font:500 9px "Geist Mono",monospace;color:#F3F4F0;margin-top:3px}
.ifsheet.r3.cover .cvscale{position:absolute;right:62px;top:120px;display:inline-flex;align-items:flex-end;height:14px}.ifsheet.r3.cover .cvscale i{width:.8px;height:6px;margin-right:6px;background:#707B75;display:block}.ifsheet.r3.cover .cvscale i.M{height:10px}.ifsheet.r3.cover .cvscale i.on{width:2.4px;height:14px;background:#8A6B35}
.ifsheet.r3.cover.back .ifbody{align-items:center;justify-content:center;gap:18px}.ifsheet.r3.cover.back .cvback-logo{height:120px;width:auto}.ifsheet.r3.cover.back .cvclaim{font:620 20px "Mona Sans",sans-serif;color:#F3F4F0;margin:0}.ifsheet.r3.cover.back .cvfine{position:absolute;bottom:40px;font:500 7px "Geist Mono",monospace;letter-spacing:.1em;text-transform:uppercase;color:#8F9993}
#ifRolBox{display:grid;gap:6px;margin-top:4px}#ifPorqueBox{display:grid;gap:6px}#ifPorqueBox textarea{width:100%;font:400 13px/1.45 var(--f-body);color:var(--ink);background:var(--surface);border:1px solid var(--line-2);border-radius:2px;padding:8px 10px;resize:vertical}
.ifpq-acc{display:flex;gap:6px;flex-wrap:wrap}
#ifPlantBox{display:grid;gap:6px;margin-top:8px}.ifpl{display:grid;gap:2px;max-height:300px;overflow:auto;border:1px solid var(--line);padding:4px 6px}
.ifpl label,.ifpl .add{display:flex;gap:8px;align-items:center;font-size:12.5px;color:var(--ink);padding:3px 0;border-bottom:1px solid var(--line);cursor:pointer}.ifpl label.off span{color:var(--muted);text-decoration:line-through}
.ifpl small{display:block;font-size:10.5px;color:var(--muted)}.ifpl .add{justify-content:space-between;cursor:default}.ifpl .add span{border-left:2px solid var(--ink);padding-left:6px}
.ifpl-res{display:grid;gap:2px;border:1px solid var(--line-2);padding:4px}.ifpl-res button{text-align:left;font:500 12.5px var(--f-body);color:var(--ink);background:transparent;border:0;border-bottom:1px solid var(--line);padding:5px 4px;cursor:pointer}
.ifpl-res button:hover,.ifpl-res button:focus-visible{background:var(--row-hover)}.ifpl-res small{display:block;font-size:10.5px;color:var(--muted)}
.ifsheet.r3 .r3t th{background:none!important}.ifsheet.r3 .cvidx{grid-template-columns:1fr!important;column-gap:0!important}.ifsheet.r3.cover .cvidx li{grid-template-columns:24px 1fr auto!important}
.r3vals>div{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.r3vals>div>div{border-top:.9px solid var(--i);padding-top:7px;display:grid;gap:4px;align-content:start}.r3vals b{font:620 11px "Mona Sans",sans-serif}.r3vals span{font-size:9.8px;color:var(--i2);line-height:1.4}
.r3read>div{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.r3read>div>div{border-top:.9px solid var(--i);padding-top:7px;display:grid;gap:4px;align-content:start}.r3read b{font:620 11px "Mona Sans",sans-serif}.r3read span{font-size:9.8px;color:var(--i2);line-height:1.4}.r3big{font:620 22px/1 "Mona Sans",sans-serif;margin:0!important}
.r3cols3{display:flex;align-items:center;gap:5px;font-size:8.4px;color:var(--i2);margin:2px 0!important;flex-wrap:wrap}.r3cols3 i{width:8px;height:8px;border-radius:50%;display:inline-block}
.r3ev{width:100%;height:auto;display:block}.r3ev .g{stroke:#CFD5D0;stroke-width:.6}.r3ev .z{stroke:#707B75;stroke-width:.7;stroke-dasharray:2 2}.r3ev .ln{fill:none;stroke:#0C1210;stroke-width:1.4}.r3ev .lr{fill:none;stroke:#8F9993;stroke-width:1.2;stroke-dasharray:3 2}.r3ev .pn{fill:#0C1210}.r3ev .pv{font:600 7.4px "Geist Mono",monospace;fill:#0C1210}.r3ev .ax{font:500 6.8px "Geist Mono",monospace;fill:#56625C}
.r3t.bloq td{padding:5px 6px 5px 0}.r3t.esc td small{color:#56625C}.r3lec{border-left:2pt solid #0F2E25;padding-left:10px}
.r3mini{display:grid;grid-template-columns:repeat(4,1fr);border-top:.5px solid #B2BAB5;border-bottom:.5px solid #B2BAB5}.r3mini div{padding:6px 0}.r3mini b{display:block;font:620 19px/1.1 "Mona Sans",sans-serif}.r3mini small{font-size:9px}.r3mini span{font:500 6.8px "Geist Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:#56625C}
.r3id.r3rolid{grid-template-columns:repeat(3,1fr);row-gap:0}.r3id.r3rolid div{border-bottom:.5px solid #B2BAB5}.r3id.r3rolid div:nth-child(3n){border-right:0}
.r3lig{display:grid;grid-template-columns:1fr 1fr;grid-auto-flow:column;column-gap:22px}.r3lig div{display:grid;grid-template-columns:1fr 160px 30px;gap:8px;align-items:center;padding:2.5px 0;border-bottom:.5px solid #CFD5D0;font-size:9.2px}.r3lig div.sel{font-weight:620}.r3lig b{font:500 8px "Geist Mono",monospace;text-align:right}.r3lig rect{fill:#8F9993}.r3lig rect.on{fill:#0C1210}.r3lig .z{stroke:#707B75;stroke-width:.6}
/* v3.1 */
.r3lead2{font-size:11.2px!important;line-height:1.5!important}
.r3inkhero{background:#0F2E25;color:#F3F4F0;padding:12px 16px 14px;display:grid;gap:10px}
.r3inkhero .r3tag{color:#8A6B35;border:1px solid #8A6B35;display:inline-block;justify-self:start;padding:2px 6px;margin:0}
.r3inkheroE{display:grid;grid-template-columns:220px 1fr;gap:16px;align-items:start;border-bottom:.6px solid #3F4B45;padding-bottom:10px}
.r3inkheroE span,.r3inkheroK span{display:block;font:500 7.2px "Geist Mono",monospace;letter-spacing:.1em;text-transform:uppercase;color:#8F9993}
.r3inkheroE b{display:block;font:620 19px/1.15 "Mona Sans",sans-serif;margin-top:4px;color:#F3F4F0}.r3inkheroE small{display:block;font-size:9px;color:#B2BAB5;margin-top:3px}
.r3inkheroE p{font:400 12.4px/1.45 "Mona Sans", sans-serif;color:#CFD5D0;margin:0!important}
.r3inkheroK{display:grid;grid-template-columns:repeat(4,1fr)}.r3inkheroK>div{padding:0 12px 0 0;margin-right:12px;border-right:.6px solid #3F4B45}.r3inkheroK>div:last-child{border:0;margin:0}
.r3inkheroK b{display:block;font:620 32px/1.05 "Mona Sans",sans-serif;letter-spacing:-.02em;margin:5px 0 3px;color:#F3F4F0}.r3inkheroK b.w{font-size:16px;line-height:1.25;margin-top:7px}
.r3inkheroK b.up{color:#3A82D6}.r3inkheroK b.dn{color:#D9662F}.r3inkheroK small{display:block;font-size:8.8px;line-height:1.35;color:#B2BAB5}
.r3dat{display:grid;grid-template-columns:repeat(5,1fr);border-top:1.2px solid var(--i);border-bottom:.5px solid var(--l2)}
.r3dat>div{padding:8px 10px 8px 0;margin-right:10px;border-right:.5px solid var(--l2)}.r3dat>div:last-child{border:0;margin:0}
.r3dat span{display:block;font:500 7.2px "Geist Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--mu);min-height:17px}
.r3dat b{display:block;font:620 23px/1.05 "Mona Sans",sans-serif;letter-spacing:-.02em;margin:3px 0 3px}
.r3dat em{display:block;font:600 9.6px "Geist Mono",monospace;font-style:normal;color:var(--i)}.r3dat em.up{color:var(--up)}.r3dat em.dn{color:var(--dn)}.r3dat em.neu{color:var(--vi)}
.r3dat small{display:block;font-size:8.2px;color:var(--mu);margin-top:2px;line-height:1.3}
.r3datn{margin-top:-10px!important}
.r3cv .g{stroke:#CFD5D0;stroke-width:.6}.r3cv .ls{fill:rgba(211, 92, 42,.30)}.r3cv .p5{stroke:#707B75;stroke-width:.7;stroke-dasharray:2 2}.r3cv .pt{fill:#0C1210}.r3cv .vl{font:600 7.6px "Geist Mono",monospace;fill:#0C1210}
.r3adk{display:grid;grid-template-columns:repeat(3,1fr);border-top:.5px solid #B2BAB5;margin-top:4px}.r3adk div{padding:5px 8px 0 0}.r3adk b{display:block;font:620 17px/1.1 "Mona Sans",sans-serif}.r3adk b.dn{color:var(--dn)}.r3adk b.up{color:var(--up)}
.r3adk span{display:block;font:500 6.8px "Geist Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:#56625C}.r3adk small{font:500 8px "Geist Mono",monospace;color:#56625C}
.r3cols.at{grid-template-columns:1.35fr 1fr}.r3cols.mn{grid-template-columns:1.45fr 1fr}
.r3kp.t4{grid-template-columns:1.2fr repeat(3,1fr)}.r3kp.t4 b{font-size:21px}.r3kp.t4 .idx b{font-size:28px}
.r3sy,.r3mn,.r3q5{width:100%;height:auto;display:block}
.r3sy .nm,.r3mn .nm,.r3q5 .nm{font:500 9.6px "Mona Sans",sans-serif;fill:#0C1210}.r3q5 .nm.q{fill:#56625C;font-style:italic}.r3q5 .nm.t,.r3q5 .vv.t{font-weight:700}
.r3sy .vv,.r3mn .vv,.r3q5 .vv{font:600 9px "Geist Mono",monospace;fill:#0C1210}.r3sy .vv.dn,.r3mn .vv.dn{fill:#D35C2A}.r3sy .vv.up{fill:#1F4A3D}
.r3sy rect.up,.r3q5 rect.up{fill:#2B6FBF}.r3sy rect.dn,.r3q5 rect.dn{fill:#D35C2A}.r3q5 rect.tt{fill:#0C1210}
.r3sy .z,.r3q5 .z{stroke:#0C1210;stroke-width:.8}.r3sy .ax,.r3mn .ax,.r3q5 .ax{font:500 7px "Geist Mono",monospace;fill:#56625C}
.r3mn .g{stroke:#CFD5D0;stroke-width:.6}.r3mn .cn{stroke:#8F9993;stroke-width:1.6}.r3mn .s0{fill:#F3F4F0;stroke:#707B75;stroke-width:1.2}.r3mn .s1{fill:#0C1210}
.r3mn .hlr,.r3q5 .hlr{fill:#DCE7E2}
.r3eb{display:grid;gap:7px}.r3eb>div{display:grid;grid-template-columns:104px 1fr;gap:8px;align-items:center}.r3eb>div>span{font-size:9.6px;color:#3F4B45}.r3eb>div.yo>span{font-weight:620;color:#0C1210}
.r3eb p{display:flex;height:17px;margin:0!important;background:#E3E7E2}.r3eb i{display:flex;align-items:center;justify-content:center;font:600 7.4px "Geist Mono",monospace;font-style:normal;color:#F3F4F0;border-right:1px solid #F3F4F0}
.r3ebl{display:flex!important;flex-wrap:wrap;gap:4px 10px;grid-template-columns:none!important;margin-top:2px}.r3ebl span{font-size:8.4px;color:#3F4B45;display:inline-flex;align-items:center;gap:4px}.r3ebl i{width:8px;height:8px;border-radius:50%;display:inline-block;border:0}
.r3im{display:block;width:100%;height:auto}.r3im .nm{font:500 9.6px "Mona Sans",sans-serif;fill:#0C1210}.r3im .nm.b{font-weight:700}.r3im .gp{font:600 6.8px "Geist Mono",monospace;letter-spacing:.08em;text-transform:uppercase;fill:#0C1210}.r3im .hd{font:500 6.8px "Geist Mono",monospace;letter-spacing:.06em;text-transform:uppercase;fill:#56625C}.r3im .rf{font:500 6.4px "Geist Mono",monospace;fill:#8F9993}.r3im .hl{stroke:#0C1210;stroke-width:.9}.r3im .sep{stroke:#CFD5D0;stroke-width:.5}.r3im .g{stroke:#E3E7E2;stroke-width:.6}.r3im .z{stroke:#B2BAB5;stroke-width:.6}.r3im .cn{stroke:#8F9993;stroke-width:1.6}.r3im .s0{fill:#F3F4F0;stroke:#707B75;stroke-width:1.2}.r3im .s1{fill:#0C1210}.r3im rect.yo{fill:#0C1210}.r3im .hlr{fill:#DCE7E2}.r3im .vv{font:600 8.6px "Geist Mono",monospace;fill:#0C1210}.r3im .vl{font:500 8.6px "Geist Mono",monospace;fill:#56625C}.r3im .vl .b,.r3im tspan.b{font-weight:700;fill:#0C1210}.r3im .ax{font:500 7px "Geist Mono",monospace;fill:#56625C}.r3im .z0{stroke:#0C1210;stroke-width:.9}.r3im rect.tt{fill:#B04A20}.r3im rect.tr{fill:#E3E7E2}.r3im .vv.dn{fill:#D35C2A}.r3im .vs{font:600 7.2px "Geist Mono",monospace;fill:#56625C}.r3im .ob{font:italic 400 8.4px "Mona Sans",sans-serif;fill:#707B75}.r3im rect.up{fill:#2B6FBF}.r3im rect.dn{fill:#D35C2A}.r3im rect.neu{fill:#6550CC}.r3im rect.eq{fill:#B2BAB5}.r3im .vs.up{fill:#1F4A3D}.r3im .vs.dn{fill:#D35C2A}.r3im .vs.neu{fill:#6550CC}.r3im .vs.eq,.r3im .vs.na{fill:#8F9993}.r3t.imp td{padding:4px 6px 4px 0}.r3t.imp.ind td{padding:1.6px 5px 1.6px 0;line-height:1.15}.r3t.imp.ind td.num small{display:block;font:500 7.4px "Geist Mono",monospace;color:#707B75;margin-top:0}.r3t.imp.ind tr.g th{font-size:6.8px;color:#707B75;border-bottom:.5px solid #B2BAB5;padding-bottom:2px;text-align:center}.r3t.imp.ind th{padding-right:5px}.r3t.imp td b.up{color:var(--up)}.r3t.imp td b.dn{color:var(--dn)}.r3t.imp td b.eq{color:#707B75;font-weight:500}.r3t.imp td b.neu{color:var(--vi)}
.r3yo{display:grid;grid-template-columns:repeat(6,1fr);border-top:.5px solid #B2BAB5;border-bottom:.5px solid #B2BAB5}.r3yo div{padding:6px 8px 6px 0}
.r3yo span{display:block;font:500 7px "Geist Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:#56625C}.r3yo b{display:block;font:500 11.6px "Geist Mono",monospace;margin-top:3px}.r3yo b i{font-style:normal;color:#8F9993}
.r3yo em{font-style:normal;font-weight:700}.r3yo em.up{color:var(--up)}.r3yo em.dn{color:var(--dn)}.r3yo em.neu{color:var(--vi)}.r3yo em.eq{color:#0C1210}
.r3l.sg li.up{border-left-color:#2B6FBF}.r3l.sg li.dn{border-left-color:#D35C2A}.r3l.sg li.up b{color:#1F4A3D}.r3l.sg li.dn b{color:#D35C2A}
.ifsheet.r3.dense .r3body{gap:12px}.r3t.esc td{padding:3.5px 6px 3.5px 0}.r3why p{margin:2px 0 5px!important}.ifsheet.r3.dense .r3t.sim td{padding:3.5px 6px 3.5px 0}.r3t.m td{padding:3.5px 6px 3.5px 0}.r3t.m td small{margin-top:0}
.r3glos div{padding:4px 0!important}.r3lig div{padding:2px 0!important}
.r3blk .ifcourt .zn{font-size:9px!important}.r3blk .ifcourt .zv{font-size:12.5px!important}`;
  const CSS40 = `
/* v4.0 · anclas NIVEL KERNO e IMPACTO */
.r3inkheroK>div.anc b{color:#8A6B35}
.r3kp.big.anc6{grid-template-columns:1.15fr 1.15fr repeat(4,1fr)}
.r3kp.big.anc6 .idx b{font-size:34px}
.r3kp .idx+.idx{border-left:2pt solid #0F2E25}
.r3anc{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin:4px 0 10px}
.r3ancla{border-top:1.2px solid #0F2E25;padding-top:8px}
.r3ancla .num{display:flex;align-items:flex-end;gap:12px;margin:2px 0 4px}
.r3ancla .num b{font:620 54px/1 "Mona Sans",sans-serif;letter-spacing:-.03em;color:#0C1210}
.r3ancla .num small{font:500 8.4px/1.35 "Geist Mono",monospace;letter-spacing:.06em;text-transform:uppercase;color:#56625C;padding-bottom:5px}
.r3g{display:block;margin:2px 0 6px}
.r3g .tr{stroke:#B2BAB5;stroke-width:1.2}
.r3g .tk{stroke:#CFD5D0;stroke-width:.8}
.r3g .tx{font:500 7px "Geist Mono",monospace;fill:#707B75}
.r3g .bd{fill:rgba(15, 46, 37, .14)}
.r3g .pt{stroke:#0C1210;stroke-width:2.2}
.r3anckv{display:grid;gap:3px;margin:0}
.r3anckv div{display:grid;grid-template-columns:96px 1fr;gap:8px;padding:3px 0;border-bottom:.5px solid #CFD5D0;font-size:9.8px;line-height:1.4}
.r3anckv dt{font:500 7.2px/1.6 "Geist Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:#56625C}
.r3anckv dd{margin:0;color:#2B3631}
.r3anckv dd small{color:#56625C;font-size:8.8px}
.r3anckv dd b.up{color:#2B6FBF}.r3anckv dd b.dn{color:#D35C2A}
.r3t.esc td small{color:#707B75;font-size:8px}
.ieq-tiles.v40{grid-template-columns:1.25fr repeat(3,1fr)}
.ieq-tiles .idx.v40 b{color:#0C1210}
.ieq-anc{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.ieq-anc .r3ancla .num b{font-size:46px}
.ieq-pr{display:block}
.ieq-pr .nm{font:500 8.6px "Mona Sans",sans-serif;fill:#2B3631}
.ieq-pr .nm .sb{fill:#707B75;font-size:7.4px}
.ieq-pr .tr{stroke:#CFD5D0;stroke-width:.8}
.ieq-pr .rf{stroke:#8F9993;stroke-width:.8;stroke-dasharray:1.5 1.5}
.ieq-pr .bd{fill:rgba(15, 46, 37, .14)}
.ieq-pr .pt{fill:#0C1210}
.ieq-pr .vv{font:500 8.6px "Geist Mono",monospace;fill:#0C1210}
.ieq-pr .vs{font:400 7.2px "Geist Mono",monospace;fill:#707B75}
.ieq-pr .hl{fill:#DCE7E2}
.ieq-pr .ax{font:500 6.8px "Geist Mono",monospace;fill:#707B75}
.ieq-card .k em.v40{color:#1F4A3D}
`;
  const CSSK = `
/* ===================== Kerno Analytics v2.0 · hojas A4 (lectura de fichaje e informe de equipo) =====================
   Una sola capa de marca para pantalla, PDF e HTML imprimible. Interior Chalk; portada y contraportada Racing a sangre.
   Racing #0F2E25 · Chalk #F3F4F0 · Ink #0C1210 · Brass #B8975C (sobre Racing) · Brass Deep #8A6B35 (sobre claro).
   Bombardier: titular de portada, número de sección y cifras héroe · Mona Sans: texto · Geist Mono: etiquetas y datos. */
.ifsheet.r3{--i:#0C1210;--i2:#3F4B45;--mu:#56625C;--fa:#707B75;--ln:#CFD5D0;--l2:#B2BAB5;--s2:#E3E7E2;--up:#2B6FBF;--dn:#D35C2A;--vi:#6550CC;--rc:#0F2E25;--r1:#DCE7E2;--bd:rgba(15,46,37,.14);--brd:#8A6B35;
  background:#F3F4F0!important;color:#0C1210;font-family:"Mona Sans",sans-serif!important;font-weight:420;font-stretch:98%;font-variant-numeric:lining-nums tabular-nums;-webkit-font-smoothing:antialiased}
.ifsheet.r3 b,.ifsheet.r3 strong{font-weight:620}
.ifsheet.r3 h1,.ifsheet.r3 h2,.ifsheet.r3 h3,.ifsheet.r3 h4{font-family:"Mona Sans",sans-serif!important}

/* cabecera mono: título · confidencial · destinatario · sección (a 11 mm del borde) */
.ifsheet.r3 .r3head{display:flex!important;align-items:baseline!important;gap:14px!important;padding:37px 52px 0!important;border:0!important;
  font:500 8px/1 "Geist Mono",monospace!important;letter-spacing:.07em!important;text-transform:uppercase!important;color:#56625C!important;white-space:nowrap}
.ifsheet.r3 .r3head span{min-width:0}
.ifsheet.r3 .r3head span:first-child{color:#0F2E25!important;font-weight:600!important;flex:none}
.ifsheet.r3 .r3head span:nth-child(2){margin-left:auto!important;color:#56625C!important;overflow:hidden;text-overflow:ellipsis}
.ifsheet.r3 .r3head .r3hsec{color:#0C1210!important;font-weight:500!important;flex:none;padding-left:14px;border-left:.6px solid #B2BAB5}
.ifsheet.r3 .r3body{padding:15px 52px 4px!important}
/* pie: marcador de calles (8 marcas; la de la página, más alta y en latón profundo) y NN / TT */
.ifsheet.r3 .r3foot{display:flex!important;align-items:flex-end!important;gap:16px!important;padding:6px 52px 37px!important;border:0!important;
  font:500 8.5px/1 "Geist Mono",monospace!important;letter-spacing:.08em!important;text-transform:uppercase!important;color:#56625C!important}
.ifsheet.r3 .r3foot span:last-child{margin-left:auto!important;color:#0C1210!important;font-weight:500}
.ifsheet.r3 .ifscale{display:inline-flex!important;align-items:flex-end!important;gap:5px!important;height:12px!important}
.ifsheet.r3 .ifscale i{display:block!important;width:1px!important;height:6px!important;margin:0!important;background:#B2BAB5!important}
.ifsheet.r3 .ifscale i.on{width:1.6px!important;height:12px!important;background:#8A6B35!important}

/* sección: filete Racing 1,2 pt · ceja mono · H2 Mona 640 ancho 92 · número grande Bombardier S200 */
.ifsheet.r3 .r3secw{display:grid;gap:0}
.ifsheet.r3 .r3sec,.ifsheet.r3 .r3sec.ink{display:flex!important;justify-content:space-between!important;align-items:flex-start!important;gap:18px!important;
  background:none!important;padding:9px 0 0!important;border-top:1.6px solid #0F2E25!important;position:relative}
.ifsheet.r3 .r3ceja{display:block;font:500 9px/1.2 "Geist Mono",monospace!important;letter-spacing:.1em!important;text-transform:uppercase!important;color:#56625C!important}
.ifsheet.r3 .r3sec h2,.ifsheet.r3 .r3sec.ink h2{font:640 27px/1.12 "Mona Sans",sans-serif!important;font-stretch:92%!important;letter-spacing:-.015em!important;
  color:#0C1210!important;margin:5px 0 0!important;max-width:580px;text-transform:none!important}
.ifsheet.r3 .r3num{font:400 56px/.86 "Bombardier","Mona Sans",sans-serif!important;letter-spacing:.02em!important;color:#CFD5D0!important;flex:none;margin-top:2px}
.ifsheet.r3 .r3lead{font:420 13.4px/1.42 "Mona Sans",sans-serif!important;font-stretch:98%;color:#3F4B45!important;margin-top:8px!important;max-width:640px}
.ifsheet.r3 .r3lead b{color:#0C1210}

/* texto, etiquetas y bloques */
.ifsheet.r3 .r3p{color:#3F4B45}
.ifsheet.r3 .r3p b{color:#0C1210}
.ifsheet.r3 .r3lab,.ifsheet.r3 .r3tag{font:500 8px/1.2 "Geist Mono",monospace!important;letter-spacing:.1em!important;text-transform:uppercase!important;color:#56625C}
.ifsheet.r3 .r3blk h3{font:620 12.4px/1.25 "Mona Sans",sans-serif!important;font-stretch:95%!important;letter-spacing:-.005em!important;border-top:.9px solid #0F2E25!important;text-transform:none!important}
.ifsheet.r3 .r3steps li,.ifsheet.r3 .r3vals>div>div,.ifsheet.r3 .r3read>div>div,.ifsheet.r3 .r3id,.ifsheet.r3 .r3dat,.ifsheet.r3 .r3kp,.ifsheet.r3 .r3est{border-top-color:#0F2E25!important}
.ifsheet.r3 .r3steps li::before{font-family:"Geist Mono",monospace;color:#56625C}
.ifsheet.r3 .r3id dd{font-weight:620}
.ifsheet.r3 .r3lec,.ifsheet.r3 .ieq-lim{border-left-color:#0F2E25!important}
.ifsheet.r3 .ieq-q5{background:#DCE7E2!important;border-left-color:#0F2E25!important}

/* tablas: cabecera de etiqueta mono, filete Racing 0,9 pt, filas S300 0,5 pt, cifras mono a la derecha, protagonista R100 */
.ifsheet.r3 .r3t th{font:500 7.6px/1.2 "Geist Mono",monospace!important;letter-spacing:.08em!important;text-transform:uppercase!important;color:#56625C!important;border-bottom:1.2px solid #0F2E25!important;background:none!important}
.ifsheet.r3 .r3t td{border-bottom:.67px solid #B2BAB5}
.ifsheet.r3 .r3t .num{font-family:"Geist Mono",monospace!important;font-variant-numeric:tabular-nums}
.ifsheet.r3 .r3t tr.yo td,.ifsheet.r3 .r3t tr.top td{background:#DCE7E2!important;font-weight:620}
.ifsheet.r3 .r3t tr.yo td b,.ifsheet.r3 .r3t tr.top td b{font-weight:640}
.ifsheet.r3 .r3rank li.yo{background:#DCE7E2!important;font-weight:620}
.ifsheet.r3 .r3lig div.sel{font-weight:620;color:#0F2E25}

/* chips de rol: estimado = filete discontinuo (sin glifos ausentes en las fuentes) */
.ifsheet.r3 .r3rol{font:500 7.6px/1.35 "Geist Mono",monospace!important;border:.67px solid #B2BAB5;color:#3F4B45;border-radius:0}
.ifsheet.r3 .r3rol.r-titular,.ifsheet.r3 .r3rol.r-go_to_guy{border-color:#0F2E25;color:#0F2E25;font-weight:600}
.ifsheet.r3 .r3rol.est{border-style:dashed}
.ifsheet.r3 .r3chip{border-radius:0}

/* flecha dibujada (Bombardier, Mona Sans y Geist Mono no tienen el glifo) */
.ifsheet .k-ar{display:inline-block;position:relative;width:.72em;height:max(1.1px,.075em);background:currentColor;vertical-align:.3em;margin:0 .32em 0 .2em;font-style:normal}
.ifsheet .k-ar::after{content:"";position:absolute;right:0;top:50%;width:.3em;height:.3em;border-top:max(1.1px,.075em) solid currentColor;border-right:max(1.1px,.075em) solid currentColor;transform:translate(0,-50%) rotate(45deg)}

/* cifras héroe en Bombardier, con su rango en Geist Mono */
.ifsheet.r3 .r3kp b,.ifsheet.r3 .r3dat b,.ifsheet.r3 .r3mini b,.ifsheet.r3 .r3adk b,.ifsheet.r3 .ieq-tiles b,.ifsheet.r3 .r3big{font-family:"Bombardier","Mona Sans",sans-serif!important;font-weight:400!important;letter-spacing:.02em!important;font-stretch:100%}
.ifsheet.r3 .r3kp b{font-size:25px!important;line-height:1.05!important;margin:5px 0 3px!important}
.ifsheet.r3 .r3kp .idx b{font-size:34px!important}
.ifsheet.r3 .r3kp.t4 b{font-size:21px!important}.ifsheet.r3 .r3kp.t4 .idx b{font-size:28px!important}
.ifsheet.r3 .r3kp.big.ieq-tmk b{font-size:23px!important}
.ifsheet.r3 .r3kp b.r3w,.ifsheet.r3 .r3kp b.w{font:620 13px/1.4 "Mona Sans",sans-serif!important;letter-spacing:0!important}
.ifsheet.r3 .r3kp b i:not(.k-ar){color:#56625C}
.ifsheet.r3 .r3kp .idx,.ifsheet.r3 .ieq-tiles .idx{border-left:2.6px solid #0F2E25!important}
.ifsheet.r3 .r3kp small,.ifsheet.r3 .r3dat small,.ifsheet.r3 .ieq-tiles small{font-family:"Mona Sans",sans-serif;color:#56625C}
.ifsheet.r3 .r3dat b{font-size:21px!important;line-height:1.05!important;margin:3px 0 2px!important}
.ifsheet.r3 .r3dat em{font-family:"Geist Mono",monospace!important}
.ifsheet.r3 .r3mini b{font-size:20px!important;line-height:1.1!important}
.ifsheet.r3 .r3adk b{font-size:18px!important;line-height:1.1!important}
.ifsheet.r3 .ieq-tiles b{font-size:30px!important;line-height:1.05!important}
.ifsheet.r3 .ieq-tiles .idx.v40 b{color:#0F2E25}
.ifsheet.r3 .r3big{font-size:24px!important;line-height:1!important;color:#0F2E25}
.ifsheet.r3 .r3ancla{border-top:1.6px solid #0F2E25!important}
.ifsheet.r3 .r3ancla .num b{font:400 58px/.95 "Bombardier","Mona Sans",sans-serif!important;letter-spacing:.02em!important;color:#0F2E25!important}
.ifsheet.r3 .ieq-anc .r3ancla .num b{font-size:48px!important}
.ifsheet.r3 .r3ancla .num small{font:500 8.4px/1.4 "Geist Mono",monospace!important;color:#56625C!important}

/* llamadas Racing: etiqueta mono en latón, texto Chalk */
.ifsheet.r3 .r3call,.ifsheet.r3 .r3why,.ifsheet.r3 .r3inkhero{background:#0F2E25!important;color:#F3F4F0!important;border:0!important}
.ifsheet.r3 .r3call .r3tag,.ifsheet.r3 .r3why .r3tag,.ifsheet.r3 .r3inkhero .r3tag,.ifsheet.r3 .r3call.callout .r3tag,.ifsheet.r3 .r3why.callout .r3tag{color:#B8975C!important;border:0!important;padding:0!important;display:block!important;margin:0 0 6px!important}
.ifsheet.r3 .r3call p,.ifsheet.r3 .r3why p{font:420 12.6px/1.5 "Mona Sans",sans-serif!important;color:#F3F4F0!important}
.ifsheet.r3 .r3why .r3vacio{color:#B2BAB5;font-style:normal}
.ifsheet.r3 .r3inkheroE{border-bottom-color:#2C5C4C!important}
.ifsheet.r3 .r3inkheroE span,.ifsheet.r3 .r3inkheroK span{color:#B2BAB5!important;font-size:7.6px!important}
.ifsheet.r3 .r3inkheroE b{color:#F3F4F0!important}
.ifsheet.r3 .r3inkheroE small,.ifsheet.r3 .r3inkheroK small{color:#B2BAB5!important}
.ifsheet.r3 .r3inkheroE p{font:420 12.4px/1.45 "Mona Sans",sans-serif!important;color:#E3E7E2!important}
.ifsheet.r3 .r3inkheroK>div{border-right-color:#2C5C4C!important}
.ifsheet.r3 .r3inkheroK b{font:400 34px/1.05 "Bombardier","Mona Sans",sans-serif!important;letter-spacing:.02em!important;color:#F3F4F0!important}
.ifsheet.r3 .r3inkheroK>div.anc b{color:#F3F4F0!important}
.ifsheet.r3 .r3inkheroK b.w{font:620 16px/1.25 "Mona Sans",sans-serif!important;letter-spacing:-.005em!important}
.ifsheet.r3 .r3inkheroK b.up{color:#3A82D6!important}.ifsheet.r3 .r3inkheroK b.dn{color:#D9662F!important}

/* The Read (la conclusión, primero) y What would change our mind (único panel de latón de la hoja) */
.ifsheet.r3 .r3theread{background:#FFFFFF;border-left:3px solid #0F2E25;padding:9px 16px 10px;break-inside:avoid}
.ifsheet.r3 .r3theread .r3lab{color:#0F2E25!important;margin:0 0 4px!important}
.ifsheet.r3 .r3theread p{font:620 15.4px/1.32 "Mona Sans",sans-serif!important;font-stretch:95%;letter-spacing:-.01em;color:#0C1210;margin:0!important}
.ifsheet.r3 .r3theread small{display:block;margin-top:5px;font:500 8.4px/1.3 "Geist Mono",monospace;letter-spacing:.06em;text-transform:uppercase;color:#56625C}
.ifsheet.r3 .r3wwc{background:#FFFFFF;border-left:3px solid #8A6B35;padding:8px 14px 8px}
.ifsheet.r3 .r3wwc .r3l{gap:3px}
.ifsheet.r3 .r3wwc>.r3lab{color:#8A6B35!important;margin:0 0 6px!important}
.ifsheet.r3 .r3wwc .r3l li{border-left-color:#CFD5D0}
.ifsheet.r3 .r3wwc .r3l span{font-size:9.9px;line-height:1.38;color:#3F4B45}

/* gráficos: protagonista Racing, contexto Sage, banda de incertidumbre Racing 14 % */
.ifsheet.r3 .r3pr .bd,.ifsheet.r3 .r3g .bd,.ifsheet.r3 .r3cv .bd,.ifsheet.r3 .ieq-pr .bd{fill:rgba(15,46,37,.14)!important}
.ifsheet.r3 .r3pr .pt,.ifsheet.r3 .ieq-pr .pt,.ifsheet.r3 .r3nec .pt{fill:#0F2E25}
.ifsheet.r3 .r3pr .pt.up,.ifsheet.r3 .r3nec .pt.up{fill:#2B6FBF}.ifsheet.r3 .r3pr .pt.dn,.ifsheet.r3 .r3nec .pt.dn{fill:#D35C2A}.ifsheet.r3 .r3pr .pt.neu,.ifsheet.r3 .r3nec .pt.neu{fill:#6550CC}
.ifsheet.r3 .r3g .pt{stroke:#0F2E25!important}
.ifsheet.r3 .r3nec .eq{fill:#F3F4F0;stroke:#0F2E25}
.ifsheet.r3 .r3cv .ln,.ifsheet.r3 .r3ev .ln{stroke:#0F2E25!important}
.ifsheet.r3 .r3cv .pt,.ifsheet.r3 .r3ev .pn{fill:#0F2E25!important}
.ifsheet.r3 .r3ev .pv,.ifsheet.r3 .r3cv .vl{fill:#0F2E25}
.ifsheet.r3 .r3rkl rect.con,.ifsheet.r3 .r3mn .hlr,.ifsheet.r3 .r3q5 .hlr,.ifsheet.r3 .r3im .hlr,.ifsheet.r3 .ieq-pr .hl,.ifsheet.ieq .hlr{fill:#DCE7E2!important}
.ifsheet.r3 .r3rkl .bar.con{stroke:#0F2E25!important}
.ifsheet.r3 .r3rkl .pt.con{fill:#8A6B35!important;stroke:#0F2E25!important}
.ifsheet.r3 .r3lig rect.on,.ifsheet.r3 .r3mn .s1,.ifsheet.r3 .r3im .s1,.ifsheet.r3 .r3im rect.yo,.ifsheet.r3 .r3q5 rect.tt{fill:#0F2E25!important}
.ifsheet.r3 .r3necl i.eq{border-color:#0F2E25!important}.ifsheet.r3 .r3necl i.pt{background:#0F2E25!important}
.ifsheet.r3 .r3sy .vv.up{fill:#1F4A3D}
.ifsheet.r3 .r3blk .ifcourt .zn{font-family:"Geist Mono",monospace!important;letter-spacing:.06em;text-transform:uppercase}
.ifsheet.r3 .r3cols.at{grid-template-columns:1.18fr 1fr}
.ifsheet.r3.dense .r3t.sim td{padding:2.4px 6px 2.4px 0!important}
.ifsheet.r3 .ieq-pr .nm{font-size:8px}

/* ---------------------------------------------------------------- portada Racing a sangre */
.ifsheet.r3.cover:not(.back){background:#0F2E25!important;color:#F3F4F0!important}
.ifsheet.r3.cover:not(.back) .ifbody{position:relative!important;height:100%!important;padding:0 68px 58px!important;display:flex!important;flex-direction:column!important;justify-content:flex-end!important;gap:0!important}
.ifsheet.r3.cover .cvestela{position:absolute;right:-92px;top:-36px;width:700px;height:700px;display:block;pointer-events:none}
.ifsheet.r3.cover .cvtop{position:absolute!important;left:68px;top:64px;display:block!important}
.ifsheet.r3.cover .cvtop .cvlogo,.ifsheet.r3.cover .cvtop img.cvlogo{width:200px!important;height:auto!important;display:block}
.ifsheet.r3.cover .cvmid{position:relative;margin:0!important}
.ifsheet.r3.cover .cvk{display:block;font:500 9.3px/1.3 "Geist Mono",monospace!important;letter-spacing:.1em!important;text-transform:uppercase!important;color:#B8975C!important;margin:0 0 16px}
.ifsheet.r3.cover h1,.ifsheet.r3.cover .cvmid h1{font:400 54px/1 "Bombardier","Mona Sans",sans-serif!important;letter-spacing:.03em!important;text-transform:uppercase!important;color:#F3F4F0!important;margin:0!important;max-width:620px}
.ifsheet.r3.cover h1.l{font-size:44px!important}
.ifsheet.r3.cover h1.xl{font-size:36px!important}
.ifsheet.r3.cover h1 .hl{background:none!important;color:inherit!important;padding:0!important}
.ifsheet.r3.cover .cvdat{font:420 15px/1.45 "Mona Sans",sans-serif!important;font-stretch:98%;color:#B2BAB5!important;margin:16px 0 0!important;max-width:560px}
.ifsheet.r3.cover .cvfacts{display:grid!important;grid-template-columns:repeat(4,1fr)!important;margin:26px 0 0!important;border-top:.67px solid #2C5C4C!important}
.ifsheet.r3.cover .cvfacts div{padding:8px 12px 0 0!important}
.ifsheet.r3.cover .cvfacts dt{font:500 7.6px/1.2 "Geist Mono",monospace!important;letter-spacing:.1em!important;text-transform:uppercase!important;color:#B2BAB5!important}
.ifsheet.r3.cover .cvfacts dd{margin:4px 0 0!important;font:620 12px/1.3 "Mona Sans",sans-serif!important;color:#F3F4F0!important}
.ifsheet.r3.cover .cvidx{list-style:none;padding:0;margin:30px 0 0!important;display:grid!important;grid-template-columns:1fr 1fr!important;column-gap:34px!important;max-width:none!important;border-top:.67px solid #2C5C4C}
.ifsheet.r3.cover .cvidx li{display:grid!important;grid-template-columns:30px 1fr auto!important;gap:8px;padding:5px 0!important;border-bottom:.67px solid #1F4A3D!important;font:420 9.6px/1.3 "Mona Sans",sans-serif!important;color:#E3E7E2!important}
.ifsheet.r3.cover .cvidx li span:first-child,.ifsheet.r3.cover .cvidx li b{font:500 8.2px/1.45 "Geist Mono",monospace!important;color:#B2BAB5!important;letter-spacing:.06em}
.ifsheet.r3.cover .cvbot{display:flex!important;justify-content:space-between!important;gap:20px;margin-top:26px;padding-top:10px!important;border-top:.67px solid #2C5C4C!important;
  font:500 8.5px/1.3 "Geist Mono",monospace!important;letter-spacing:.1em!important;text-transform:uppercase!important;color:#B2BAB5!important}
.ifsheet.r3.cover .cvbot b,.ifsheet.r3.cover .cvbot span{font:inherit!important;color:inherit!important;margin:0!important;display:inline!important;letter-spacing:inherit!important}
.ifsheet.r3.cover .cvscale{display:none!important}

/* ---------------------------------------------------------------- contraportada Racing */
.ifsheet.r3.cover.back{background:#0F2E25!important}
.ifsheet.r3.cover.back .ifbody{position:relative!important;height:100%!important;padding:0!important;display:flex!important;flex-direction:column!important;align-items:center!important;justify-content:center!important;gap:40px!important}
.ifsheet.r3.cover.back .cvback-logo{width:230px!important;height:auto!important;display:block}
.ifsheet.r3.cover.back .cvclaim{font:400 27px/1 "Bombardier","Mona Sans",sans-serif!important;letter-spacing:.04em!important;text-transform:uppercase!important;color:#F3F4F0!important;margin:0!important;width:auto!important}
.ifsheet.r3.cover.back .cvfine{position:absolute!important;left:68px;right:68px;bottom:58px!important;text-align:center;font:500 8.5px/1.4 "Geist Mono",monospace!important;letter-spacing:.1em!important;text-transform:uppercase!important;color:#B2BAB5!important}
`;
  const st3 = document.createElement("style"); st3.id = "cerno-informe-v3"; st3.textContent = CSS3 + CSS40 + CSSK; document.head.appendChild(st3);
  ifEstilos = () => INF_CSS + CSS3 + CSS40 + CSSK;      // rasterizado (SVG foreignObject): las mismas reglas que en pantalla
  const _imp = ifHtmlImprimible;
  ifHtmlImprimible = () => _imp().replace("</style>", CSS3 + CSS40 + CSSK + "\n</style>");
})();
