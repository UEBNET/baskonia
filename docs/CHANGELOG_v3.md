# CHANGELOG v3 — normalización cruzada con CVAE jerárquica

Regla suprema: **versionar, nunca sustituir**. La v1/v2 queda en `main` (y debía quedar congelada en la etiqueta
`v2-snapshot-20261029`; ver «Pendiente»). Todo lo de la v3 va en rutas nuevas.

## v3.0 (29-10-2026) — rama `claude/optimistic-pasteur-mlxi78` (sobre `datos/2026-27-actualizacion-20261029`)

### Nuevo
* `bbnorm3/`: paquete de la v3 (CLI `python -m bbnorm3 {elegir-k, f0, validar, lolo, ajustar}`).
  * `datos.py`: capa de medida reutilizada (identidades, pos3, transformaciones y ruido σ²/n del proyecto), sin fuga.
  * `modelo.py`: CVAE jerárquica (latente común u, niveles μ_c con jerarquía y gauge en la media, escala por liga,
    codificador amortizado con producto de expertos, decodificador con FiLM y cabezal residual por liga, efecto
    equipo-temporada y factor específico persona × métrica, IPW de los puentes, consistencia de ciclo).
  * `niveles.py`: posterior gaussiana exacta y conjunta de niveles y latentes (covarianza completa).
  * `prediccion.py`, `traduccion.py`: traducción con la posterior completa; niveles por métrica; matriz cruzada
    T_m(a → b) con Var = Σ_aa + Σ_bb − 2Σ_ab; residuo de ciclo.
  * `examen.py`, `f0.py`, `flujo.py`: examen sin fuga, líneas base (mismo percentil, `<m>_am`, F0), recalibración
    conforme, bootstrap por persona y puerta de control.
  * `exportar.py`, `salidas.py`: salidas en `data/modelos/v3/`.
* `configs/normalization_v3.yaml` (todo hiperparámetro y semilla), `configs/version.yaml` (`version_activa: v1`).
* `tests/test_bbnorm3.py`: gauge, invariancia, varianza de pares, ciclo, esquema y determinismo.
* `docs/normalizacion_v3_cvae.md`.
* `requirements-v3.txt`: `torch==2.5.1` (CPU). En un fichero aparte para que el workflow de extracción (que instala
  `requirements.txt`) no descargue PyTorch.

### Resultado de la puerta de control: NO SE CUMPLE (29-10-2026)
* Examen 2023 → 24 y 2024 → 25: v3 +12,6 % de MAE frente a `<m>_am` (IC 95 % +8,2 % a +16,9 %). Por corte: 2023
  +29,6 % (fallo de la Tercera FEB: escala latente degenerada, s = 15,6) y 2024 −5,0 % (IC −6,5 % a −3,4 %).
* Por tanto, **no** se ejecutan las fases 4 (aguas abajo) y 5 (datos del artifact), ni el ajuste final, ni dejar
  fuera una liga. `configs/version.yaml` sigue en `v1`. Detalle en `docs/normalizacion_v3_cvae.md` §5-6.
* Añadida la opción de diagnóstico `prior.escala_por_liga` (por defecto `true` = v3.0 tal como se examinó).
* `config/ESTILOS_VADE_OBSOLETOS.md`: deja constancia de que E01–E06 quedan desestimados en la v3 (sin tocar
  `config/estilos.json`).

### Sin cambios
* `bbstats/`, `bbmodel/`, `bbfit/`, `bbestilo/`, `artifact/` y todas las salidas en `data/modelos/` de la v1/v2.

### Pendiente (requiere aprobación del CEO)
* Etiqueta `v2-snapshot-20261029`: esta sesión no tenía permiso para subir etiquetas (HTTP 403). Comando para
  crearla: `git tag -a v2-snapshot-20261029 150e814 -m "…" && git push origin v2-snapshot-20261029`.
* Activar la v3 (`configs/version.yaml → version_activa: v3`) y la regeneración aguas abajo (fase 4), sólo si la v3 pasa
  la puerta de control.
