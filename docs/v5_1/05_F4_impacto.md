# v5.1 · F4 · Impacto con la v5 en el prior del RAPM multiliga

Fecha: 13-11-2026 · Kerno Analytics · encargo v5.1 (`docs/v5_1/00_encargo_v5_1.md`).

**Código.** `bbnorm5/simulador51/impacto.py`. Envuelve sin modificarlos `bbequipo.rapm.tabla_prior` y
`bbequipo.sinergia.Rasgos` y redirige las salidas a `experimentos/v5_1/F4/`.

**Salidas.** `data/v5_1/impacto/meta_impacto.json`.

```bash
python -m bbnorm5.v51 --config configs/v5_1/f2.yaml --pasos impacto      # ≈ 30 min, con las cachés de la F0
```

Etiquetas: **DATO**, **LECTURA**, **SUPUESTO**, **RIESGO**, **VERIFICAR**.

---

## Informe de auditoría · v5.1 · Fase F4 · Impacto

### Resumen ejecutivo

**El Impacto se queda como está: meter la v5 en el prior del RAPM multiliga no lo mejora.**
- **Examen de equipo (ΔNet):** error +0,009 [IC 95 % −0,004, +0,022].
- **Impacto frente al on/off del fichaje:** −0,005 [−0,009, −0,002], algo peor.
- **En quienes cambian de liga, donde la F10 veía la ganancia:** −0,007 [−0,014, −0,001].
- **Las β del RAPM apenas cambian** (correlación 0,998).

**Por qué.** El RAPM multiliga ya estima un intercepto por liga y temporada: es la traducción entre ligas. Su prior ya
lleva el perfil de la v3.2. La ganancia de la F10 (de 0,02 a 0,29 en quienes cambian de liga) se medía contra el RAPM
**por liga**, que no tiene ninguna de las dos cosas. Por la regla del encargo (§3.2) no se sustituye nada.

---

## 1. Qué se hizo

1. **Bloque v5 en el prior.** El nivel de carrera filtrado de la F4 de la v5 en 13 métricas de producción, de la liga
   principal de cada persona-temporada, más una máscara. Entra en g(x̃) junto a los bloques vigentes.
   - Cobertura: el 72 % de los registros del corte 2022.
   - Sin perfil v5: la BBL antes de 2023-24; la LNB y la VTB, a medias.
2. **Sólo en el prior.** Las redes de sinergia y de conjunto (F2 y F3 de la v4.0, versionadas) se entrenaron con 44
   rasgos y siguen recibiendo esos. El primer intento falló justo por eso: les llegaban 58.
3. **Ajustes F1 por corte (2021–2024)** con la rejilla reducida del producto (τ ∈ {1, 2, 3}, α = 1). Eligen lo mismo
   que en la F0: τ* = 1 en el bayes empírico y 2–3 tras el GBM, α* = 1.
4. **Exámenes.** Equipo F4 (ΔNet de la temporada siguiente) e Impacto (Nivel Kerno y anclas de la v4.0), con el mismo
   simulador reproducido en la F0. Se comparan con la F0 en los mismos equipos y fichajes, y por pares.

## 2. Resultados (DATO)

| Examen | F0 (prior vigente) | v5.1 (con bloque v5) | Diferencia pareada |
|---|---|---|---|
| Equipo F4: MAE del ΔNet (933 equipos) | 4,037 | 4,046 | +0,009 [−0,004, +0,022] |
| Equipo F4: cobertura del 80 % | 0,763 | 0,758 | — |
| Impacto frente al on/off de t+1 (examen vigente, 3.599) | 0,141 [0,110, 0,174] | 0,137 [0,107, 0,170] | — |
| Impacto frente al on/off, pareado por fichaje (3.605) | 0,154 | 0,148 | −0,005 [−0,009, −0,002] |
| — quienes cambian de liga (1.211) | 0,150 | 0,143 | −0,007 [−0,014, −0,001] |
| — quienes siguen en su liga (2.394) | 0,153 | 0,148 | −0,005 [−0,009, −0,001] |
| Impacto por paquete (ΔNet del equipo) | 0,134 | 0,133 | — |
| Puerta del Impacto | no pasa | no pasa | — |

## 3. Interpretación (LECTURA)

1. **El RAPM multiliga ya tiene la traducción.** Los interceptos c_{ℓ,t} recogen la fuerza de cada liga en cada
   temporada con los partidos entre ligas y los jugadores que se mueven. La «traducción» de la v5 no añade nada.
2. **El perfil de la v5 duplica información que el prior ya tiene.** Los rasgos de la v3.2 (θ por rasgo), el perfil
   latente y el RAPM de la temporada anterior ya ordenan a los jugadores. Más rasgos parecidos sólo añaden ruido de
   estimación al prior: de ahí la pequeña pérdida.
3. **Lo que la F10 midió es real, pero para otro objeto.** Sirve para traducir un RAPM **por liga** (el de
   `data/modelos/pista/`, que usan el Atlas y las vistas por liga). Al Impacto, que ya usa el multiliga, no le aporta.
4. **El prior de los interceptos de liga desde los puentes no se hace.** Los interceptos ya se estiman con muchos
   partidos y los puentes no los mejorarían. Cambiarlo exigiría tocar el ajuste interno del RAPM, sin beneficio
   esperable.
5. **El punto débil del Impacto vigente es su rango, no la v5.** La banda del Δ̂Net del fichaje cubre el ΔNet del
   equipo en el 47 %. La puerta del Impacto falla por eso, en la versión vigente y en esta. Es una calibración entre
   objetos distintos (fichaje frente a equipo) que conviene resolver en el propio Impacto. **VERIFICAR**, fuera de la v5.

## 4. Decisión

Por la regla del encargo v5.1 §3.2 (sustituir sólo si mejora su examen con IC que no cruza 0):
- **El Impacto mantiene el prior vigente.**
- El bloque v5 queda documentado y desactivado. El módulo permite reactivarlo para examinarlo de nuevo con más
  temporadas.

## 5. Supuestos y riesgos

1. **SUPUESTO · el nivel filtrado de la v5 en la temporada t** entra en el prior de β en t. Es el mismo trato que los
   rasgos de la v3.2 de la misma temporada en el diseño vigente.
2. **SUPUESTO · rejilla reducida en los cuatro cortes.** La F0 usó la completa en 2021–2023. Ambas eligen los mismos τ
   y α, así que la comparación es equivalente.
3. **RIESGO · el Impacto sigue sin pasar su puerta,** por la calibración del rango (§3.5). No lo causa la v5.1, pero
   condiciona cómo se publica en la F6.

## 6. Verificación de no regresión

- `bbequipo/` no se modifica: las funciones se envuelven en memoria.
- Las salidas van a `experimentos/v5_1/F4/`.
- Nada de `data/modelos/` ni de los artifacts cambia.

## 7. Siguiente fase

**F5 · Landing** (con la ampliación del usuario):
- δ₁ y δ₂ jerárquicos por grupo de la Landing vigente, contraídos a través del perfil latente;
- «Adaptación EE. UU. → Europa» como lectura con sello;
- NK₂ (sin adaptación) frente a NK₁ con la contribución de la v5.1;
- examen de publicación fuera de tiempo.

Esperando GO.
