"""Línea de comandos de los estilos de juego.

    python -m bbestilo entrenar                 # entrena IDEC y VaDE (5 semillas), evalúa y guarda (≈40 min)
    python -m bbestilo evaluar                  # reevalúa las redes guardadas sin reentrenar
    python -m bbestilo encaje --jugador "Nombre" [--club baskonia] [--competicion euroleague]
                              [--temporada 2025-26] [--red idec|vade|ambas] [--minutos 600] [--sustituye "Nombre"]
    python -m bbestilo analisis                 # análisis complementarios (data/modelos/estilos/analisis.json)
    python -m bbestilo exportar                 # JSON del mapa 3D (artifact/estilos/)
    python -m bbestilo articulo [--fuentes D]   # artículo científico en PDF (docs/articulo/)

Resultados en data/modelos/estilos/ (ver docs/estilos_de_juego.md).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C


def _json(obj, ruta):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=float), encoding="utf-8")


def entrenar(redes: list[str], semillas: list[int]) -> None:
    from . import datos, entrenar as E, evaluar as V, resultados as R

    t0 = time.time()
    cj = datos.construir()
    print(f"Datos: {len(cj.clubes)} clubes-competición-temporada ({(~cj.clubes.provisional).sum()} de entrenamiento), "
          f"{len(cj.jugadores)} filas jugador-equipo", flush=True)
    _json({"rasgos": [r.__dict__ for r in C.RASGOS], "nivel": C.NIVEL, "n_estilos": C.N_ESTILOS,
           "neutralizar_nivel": C.NEUTRALIZAR_NIVEL, "escala_club": cj.escala_club.a_dict(),
           "escala_jugador": cj.escala_jugador.a_dict(), "nivel_club": cj.nivel_club.a_dict(),
           "nivel_jugador": cj.nivel_jugador.a_dict(),
           "neutral_club": cj.neutral_club.a_dict() if cj.neutral_club else None,
           "neutral_jugador": cj.neutral_jugador.a_dict() if cj.neutral_jugador else None,
           "temporadas_entreno": C.TEMPORADAS_ENTRENO,
           "temporadas_provisionales": C.TEMPORADAS_PROVISIONALES}, C.DIR_SALIDA / "escalas.json")
    for tipo in redes:
        print(f"[{tipo}] {len(semillas)} semillas…", flush=True)
        res = E.entrenar_semillas(tipo, cj, semillas, log=lambda m: print(m, flush=True))
        todas, red, i = res["redes"], res["final"], res["indice_base"]
        semilla = semillas[i]
        print(f"[{tipo}] semilla final {semilla}; red de reserva (sin 2024-25 ni 2025-26)…", flush=True)
        M = E.muestras(cj, C.TEMPORADAS_ENTRENO[:4], semilla)
        reserva = E.ENTRENADORES[tipo](M, semilla)
        reserva.eval()
        E.orientar(reserva, M.Xc)
        d = C.DIR_SALIDA / tipo
        E.guardar(red, tipo, semilla, d / "modelo.pt")
        E.guardar(reserva, tipo, semilla, d / "reserva.pt")
        for s, r in zip(semillas, todas):
            E.guardar(r, tipo, s, d / "semillas" / f"{s}.pt")
        _json({"registro": res["registro_final"], "consenso": res.get("consenso")}, d / "registro.json")
        if "etiquetas_consenso" in res:
            np.save(d / "consenso.npy", res["etiquetas_consenso"])
        print(f"[{tipo}] entrenada ({time.time() - t0:.0f} s)", flush=True)
    evaluar(redes, cj)
    print(f"Hecho en {time.time() - t0:.0f} s", flush=True)


def evaluar(redes: list[str], cj=None) -> None:
    """Evalúa las redes guardadas (modelo, semillas y reserva) y escribe tablas y comparativa."""
    from . import datos, entrenar as E, evaluar as V, resultados as R

    cj = cj or datos.construir()
    ev = {}
    for tipo in redes:
        d = C.DIR_SALIDA / tipo
        red, info = E.cargar(d / "modelo.pt")
        semillas = sorted(int(p.stem) for p in (d / "semillas").glob("*.pt"))
        todas = [E.cargar(d / "semillas" / f"{s}.pt")[0] for s in semillas]
        reserva = E.cargar(d / "reserva.pt")[0]
        Xc = E.torch.tensor(cj.Xc[cj.clubes["temporada"].isin(C.TEMPORADAS_ENTRENO).to_numpy()], dtype=E.torch.float32)
        et = [E.etiquetas(r, Xc) for r in todas]
        ari = np.array([[E.adjusted_rand_score(a, b) for b in et] for a in et])
        print(f"[{tipo}] evaluando…", flush=True)
        ev[tipo] = V.evaluar(red, todas, ari, cj, reserva)
        ev[tipo].update({"semilla_final": info["semilla"], "semillas": semillas, "ari_matriz": ari.round(4).tolist(),
                         "hiperparametros": {**E.HIPER[tipo], "bootstrap_por_club": C.BOOTSTRAP_POR_CLUB,
                                             "k_gamma": C.K_GAMMA, "peso_jugadores": C.PESO_JUGADORES}})
        _json(E.exportar_pesos(red, tipo), d / "pesos.json")
        clubes, P = R.tabla_clubes(red, cj)
        clubes.to_csv(d / "clubes.csv", index=False, float_format="%.4f")
        R.tabla_estilos(red, cj, P).to_csv(d / "estilos.csv", index=False, float_format="%.4f")
        R.tabla_jugadores(red, cj).to_csv(d / "jugadores.csv", index=False, float_format="%.4f")
        _json(ev[tipo], d / "evaluacion.json")
        print(f"[{tipo}] listo", flush=True)
    if len(ev) == 2:
        comp = V.tabla_comparativa(ev)
        comp.to_csv(C.DIR_SALIDA / "comparativa.csv", index=False, float_format="%.4f")
        _json({"referencia_kmedias": V.referencia_kmedias(cj), **ev}, C.DIR_SALIDA / "evaluacion.json")
        with pd.option_context("display.width", 200, "display.max_colwidth", 60):
            print(comp.to_string(index=False))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bbestilo", description="Estilos de juego por club y temporada (IDEC y VaDE)")
    sub = ap.add_subparsers(dest="orden", required=True)
    e = sub.add_parser("entrenar", help="entrena, evalúa y guarda las dos redes")
    e.add_argument("--redes", nargs="+", default=["idec", "vade"], choices=["idec", "vade"])
    e.add_argument("--semillas", nargs="+", type=int, default=C.SEMILLAS)
    v = sub.add_parser("evaluar", help="reevalúa las redes guardadas (sin reentrenar)")
    v.add_argument("--redes", nargs="+", default=["idec", "vade"], choices=["idec", "vade"])
    f = sub.add_parser("encaje", help="encaje de un jugador en un club (distancias, cohesión y simulación)")
    f.add_argument("--jugador", required=True)
    f.add_argument("--club", default="baskonia")
    f.add_argument("--competicion", default="euroleague")
    f.add_argument("--temporada", default="2025-26")
    f.add_argument("--temporada-jugador", default=None, help="temporada del jugador (por defecto, la más reciente)")
    f.add_argument("--red", default="ambas", choices=["idec", "vade", "ambas"])
    f.add_argument("--minutos", type=float, default=None, help="minutos que tendría en el club (por defecto, su cuota actual)")
    f.add_argument("--sustituye", default=None, help="jugador de la plantilla cuyos minutos hereda")
    sub.add_parser("analisis", help="análisis complementarios (K, nivel, éxito, encaje, continuidad, ligas, Baskonia)")
    ar = sub.add_parser("articulo", help="artículo científico en PDF (docs/articulo/)")
    ar.add_argument("--fuentes", default=None, help="carpeta con fuentes woff/ttf y fuentes.css (opcional)")
    x = sub.add_parser("exportar", help="datos del mapa 3D para el Artifact")
    x.add_argument("--salida", default=str(C.RAIZ / "artifact" / "estilos"))
    for sp in (e, v):
        sp.add_argument("--estilos", type=int, default=C.N_ESTILOS, help="neuronas de salida (v2: 8; v1: 12)")
        sp.add_argument("--sin-neutralizar", action="store_true", help="no quitar el nivel (como la v1)")
        sp.add_argument("--salida", default=None, help="carpeta de resultados (por defecto data/modelos/estilos)")
    args = ap.parse_args(argv)
    if args.orden in ("entrenar", "evaluar"):
        C.N_ESTILOS = args.estilos
        C.NEUTRALIZAR_NIVEL = not args.sin_neutralizar
        if args.salida:
            C.DIR_SALIDA = Path(args.salida).resolve()

    if args.orden == "entrenar":
        entrenar(args.redes, args.semillas)
    elif args.orden == "evaluar":
        evaluar(args.redes)
    elif args.orden == "encaje":
        from . import encaje
        redes = ["idec", "vade"] if args.red == "ambas" else [args.red]
        print(encaje.informe(args.jugador, args.club, args.competicion, args.temporada, redes,
                             args.minutos, args.sustituye, args.temporada_jugador))
    elif args.orden == "analisis":
        from . import analisis
        analisis.main()
        print("escrito", C.DIR_SALIDA / "analisis.json")
    elif args.orden == "articulo":
        from . import articulo
        print("escrito", articulo.construir(Path(args.fuentes) if args.fuentes else None))
    elif args.orden == "exportar":
        from . import exportar
        exportar.main(args.salida)


if __name__ == "__main__":
    main()
