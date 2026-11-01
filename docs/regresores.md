# Regresores

Un **regresor** es una variable semanal que no viene del DEIS y que podría ayudar a
pronosticar las atenciones, por ejemplo los feriados, la circulación de virus
respiratorios, la temperatura o una campaña de vacunación. Esta página explica cómo se
agregan sin hacer trampa, cuáles vienen incluidos, qué mostraron con datos reales y cómo
probar uno propio.

En la [demo](https://nicoveraz.github.io/urg-forecast-core/demo/) puedes agregarlos al
pronóstico con un botón y comparar las dos curvas.

## Cómo funcionan

El modelo `Armónico` describe cada semana con una tendencia y un ciclo anual. Un regresor
le agrega una o más columnas: por ejemplo "cuántos feriados caen en día hábil esa semana".
Si esa columna explica parte de lo que el ciclo anual no explica, el pronóstico mejora. Si
no, solo agrega ruido.

Cada regresor es una tabla con `timestamp` (el lunes que cierra cada semana DEIS) y una
columna por variable, más **las reglas de su fuente**:

- **Atraso de publicación** (`report_delay_weeks`). FluNet publica una semana unas dos
  semanas después. Al pronosticar desde una fecha, esas dos últimas semanas todavía no
  existen.
- **Futuro conocido** (`known_future`). Los feriados de 2027 ya se saben; la positividad
  de influenza de julio de 2027, no.

Y dos decisiones del modelo:

- **Rezago** (`lag_weeks`): la semana `t` usa el valor de la semana `t − rezago`.
- **Qué hacer con lo que aún no se publica** (`future`): el promedio histórico de esa
  semana del año (`"climatology"`) o una proyección de la propia serie desde la temporada
  en curso (`"forecast"`), que arrastra si la temporada viene adelantada o atrasada.

La regla que lo mantiene honesto: **en cada ventana del backtest el modelo solo ve lo que
estaba publicado en esa fecha.** Si se usaran los valores reales de las semanas
siguientes, el backtest se vería mejor de lo que el modelo puede rendir en la práctica.

## Los incluidos

| Regresor | Variables | Atraso | Futuro | Modelos (`-m`) |
|---|---|---|---|---|
| `calendar()` | feriados en día hábil, interferiados, fracción de la semana en vacaciones escolares | — | conocido | `ArmónicoFeriados` (solo feriados), `ArmónicoCalendario` (las tres) |
| `flunet()` | positividad nacional de influenza y VRS (OMS FluNet, reportada por el ISP) | 2 semanas | no | `ArmónicoFluNet` (promedio histórico, rezago 3), `ArmónicoFluNetProy` (proyección, rezago 1) |

El calendario sale de la biblioteca `holidays` y de un calendario escolar aproximado
(`features.calendar`). FluNet se copia cada semana a la rama `datos` del repositorio
(`flunet_chl.csv`). Es semanal desde 1997 y **solo nacional**: no distingue regiones.

## Qué mostraron con datos reales

Cada variante se comparó con el Armónico sin regresor en los 40 hospitales públicos con más
atenciones, con hasta 36 ventanas de 4 semanas desde enero de 2024 (tres inviernos), en
noviembre de 2026. Para cada hospital, una prueba de signos dice si la diferencia es
consistente (`mejora` o `empeora`) o ruido (`sin diferencia`).

| Variante | Cambio mediano de la pérdida P80 | Ventanas ganadas | Mejora / empeora / sin diferencia |
|---|---|---|---|
| Feriados | **−2,9 %** | **66 %** | **19** / 0 / 21 |
| Calendario completo | −3,4 % | 62 % | 7 / 0 / 33 |
| Virus, promedio histórico (rezago 3) | +1,0 % | 45 % | 0 / 7 / 33 |
| Virus, proyección (rezago 3) | +0,9 % | 45 % | 0 / 2 / 38 |
| Virus, proyección (rezago 1) | +1,8 % | 44 % | 0 / 3 / 37 |

**Los feriados sí ayudan.** La pérdida mediana baja en 39 de los 40 hospitales y ninguno
empeora. Por azar se esperaría que uno de 40 saliera "mejora", no 19. La ganancia es mayor
en septiembre (−7,5 %, gana en el 88 % de las ventanas: Fiestas Patrias), pero se mantiene
el resto del año. Sumar interferiados y vacaciones escolares no agrega: las vacaciones son
aproximadas y se parecen mucho al ciclo anual que el modelo ya tiene.

**La circulación viral no ayuda con el total de atenciones.** Ningún hospital mejora de
forma consistente, y los que ganan un invierno no son los que ganan el siguiente: la
correlación entre inviernos es cercana a cero. El daño se concentra en invierno, cuando
la positividad suma variabilidad sin aportar información que el ciclo anual no tenga.
Proyectarla reduce los hospitales que empeoran, pero no logra que mejoren. Puede rendir
más con series más específicas (atenciones respiratorias o pediátricas) o con vigilancia
regional.

Las dos conclusiones son útiles: un resultado negativo bien medido le ahorra trabajo a
quien venga después.

## Por qué un intervalo más angosto o más bajo puede ser peor

Al sumar un regresor, la banda hasta P80 a veces se angosta o baja. Eso no basta para que el
pronóstico sea mejor. La comparación usa la pérdida P80, que cobra distinto según el lado:

- si lo real supera el P80, **0,8** por cada atención de diferencia;
- si queda bajo el P80, **0,2** por cada atención.

Bajar el P80 en 10 atenciones ahorra 2 en cada semana que sigue bajo él y cuesta 8 en cada
semana que queda sobre él. Conviene solo si lo real lo sigue superando en menos de 1 de
cada 5 semanas, que es lo que promete un P80. Un ejemplo inventado, con cuatro semanas:

| Semana | Real | P80 A | Pérdida A | P80 B, 30 más abajo | Pérdida B |
|---|---|---|---|---|---|
| 1 | 1.000 | 1.050 | 0,2 × 50 = 10 | 1.020 | 0,2 × 20 = 4 |
| 2 | 980 | 1.050 | 0,2 × 70 = 14 | 1.020 | 0,2 × 40 = 8 |
| 3 | 1.040 | 1.050 | 0,2 × 10 = 2 | 1.020 | **0,8 × 20 = 16** |
| 4 | 1.035 | 1.050 | 0,2 × 15 = 3 | 1.020 | **0,8 × 15 = 12** |
| **Pérdida P80** (promedio) | | | **7,25** | | **10,0** |

B ahorra 12 en las dos semanas tranquilas y pierde 23 en las otras dos: es más angosto y
peor. En cuatro hospitales grandes revisados en noviembre de 2026, los regresores cambian
el ancho del intervalo apenas (entre 1 y 4 %). Cuando empeoran, es porque lo real supera
su P80 más seguido o por más, no por el ancho en sí.

La demo lo muestra con el backtest real de cada uno de los 40 establecimientos evaluados.
Hay un gráfico con el P80 de cada ventana y lo que pasó, la cuenta semana a semana de la
ventana que elijas, y una tabla con el ancho, las semanas sobre el P80 y las dos partes de
la pérdida. En Python, `backtest(...).scores()` trae esas columnas para cada ventana:
`width_80` (P80 menos P50), `qloss_80_short` (la parte por quedarse corto) y
`qloss_80_excess` (la parte por pasarse); las dos suman `qloss_80`.

```python
from urgencias_core import backtest
from urgencias_core.models.registry import available_models

modelos = available_models()
dos = {m: modelos[m] for m in ("Armónico", "ArmónicoFeriados")}
corrida = backtest(semanal, dos, length=4, origins=36, step=4)
cols = ["width_80", "qloss_80_short", "qloss_80_excess", "qloss_80"]
print(corrida.scores().groupby("model")[cols].mean())
```

## Probarlo

**En la demo.** Sobre el gráfico de cada establecimiento hay tres botones: "+ Feriados",
"+ Virus respiratorios" y "+ Virus, proyectados". Al activar uno, el gráfico compara el
Armónico solo (línea punteada) con el Armónico más ese regresor (línea de color y su banda
hasta P80), sin la calibración de intervalos, para que la única diferencia sea el
regresor. El texto bajo el gráfico dice cuánto cambian las próximas cuatro semanas y, si
el establecimiento está entre los 40 evaluados, el veredicto de su backtest. En el gráfico
y su detalle se ve qué supuso el modelo para cada semana: los feriados o la positividad
publicada o proyectada. Más abajo, en la misma página, está su backtest semana a semana
(ver la sección anterior).

**En la terminal.**

```bash
urg-forecast pronosticar 24-105 -m ArmonicoFeriados -m Armonico   # pronóstico con y sin
urg-forecast comparar 24-105 -m ArmonicoFeriados                  # ¿mejora acá? 36 ventanas
```

**En Python.** [`examples/04_regresor_externo.py`](https://github.com/nicoveraz/urg-forecast-core/blob/main/examples/04_regresor_externo.py)
compara las variantes en un establecimiento y grafica lo que supuso el modelo.

## Agregar uno propio

Un regresor propio se declara igual que los incluidos:

```python
import pandas as pd
from urgencias_core.eval.compare import compare_models
from urgencias_core.models.exogenous import HarmonicExogenous
from urgencias_core.models.harmonic import HarmonicRegression
from urgencias_core.regressors import Regressor

temperatura = Regressor(
    name="temperatura",
    load=lambda: pd.read_csv("temperatura_semanal.csv", parse_dates=["timestamp"]),
    columns=("temp_min",),        # una columna por variable
    report_delay_weeks=1,         # se publica con una semana de atraso
)
con_temp = lambda: HarmonicExogenous.from_regressor(
    temperatura, lag_weeks=0, future="forecast"
)
cmp = compare_models(semanal, ("Armónico", HarmonicRegression), ("ConTemp", con_temp))
print(cmp.text())
```

Antes de concluir que sirve:

- **Semanas DEIS.** `timestamp` es el lunes que cierra la semana (los 7 días que terminan
  ese lunes). Agrega tus datos diarios a esas semanas.
- **Un atraso realista.** Si en la práctica el dato llega tarde, decláralo. Si no, el
  backtest queda mejor de lo que el modelo puede rendir de verdad.
- **Muchos establecimientos, no uno.** Con 40 hospitales y un umbral de 5 %, unos dos
  saldrán "mejora" o "empeora" por azar. Un regresor útil mejora en muchos.
- **Lo que ya explica la estación.** Una variable que sube y baja cada año igual que las
  atenciones (temperatura, vacaciones) puede no agregar nada al ciclo anual.
- **Documenta el resultado**, aunque sea negativo.

Si gana, se registra como modelo opcional en `models/registry.py` y se suma a
`available_regressors()` en `regressors.py`. Dónde va cada cosa está en
[Arquitectura](arquitectura.md).
