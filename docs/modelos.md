# Modelos

`urg-forecast` trae once modelos. Por defecto pronostica **Ensamble**, la mediana de
AutoARIMA, Armónico y MSTL, y mide en el mismo backtest, como referencia, SeasonalNaive,
AutoARIMA, Armónico y MSTL. Los otros seis están para experimentar y se activan con `-m`.
Todos son aproximaciones iniciales: ninguno está ajustado a un establecimiento en
particular.

```bash
urg-forecast modelos                                   # lista con descripción
urg-forecast pronosticar 24-105 --criterio p80         # elige el de menor pérdida P80
urg-forecast pronosticar 24-105 -m TBATS -m Ensamble   # TBATS, como referencia
urg-forecast pronosticar 24-105 -m TBATS -m MSTL       # elige entre esos dos
urg-forecast pronosticar 24-105 -m Armonico            # usa uno sin comparar
```

Los nombres no distinguen mayúsculas ni tildes. Cuando indicas un solo modelo
igual se hace el backtest, para que veas su error, pero no hay elección. Si indicas
varios sin Ensamble, se usa el de menor pérdida P80.

## Cómo se comparan

Cada modelo se ajusta en tres ventanas de backtest tan largas como el horizonte
(máximo 26 semanas), separadas por 8 semanas (`--ventanas` y `--paso` lo cambian; ver
[Ventanas del backtest](#ventanas-del-backtest)), y la tabla del resumen muestra su error
promedio. La medida principal es la **pérdida por cuantil P80**, que castiga más quedarse
corto que pasarse, que es lo que importa al planificar dotación.

El pronóstico lo hace Ensamble, reajustado con toda la historia, aunque otro modelo haya
tenido menos error en esas ventanas: elegir así rindió peor (ver
[Combinar o elegir](#combinar-o-elegir)). Con `--criterio`, en cambio, se usa el de menor
error según ese criterio (ver [Elegir el criterio](#elegir-el-criterio)). Los intervalos son
los del modelo; `--calibrar` los ensancha si en el backtest resultaron estrechos (ver
[Calibrar los intervalos](#calibrar-los-intervalos)). Si un modelo falla al ajustarse, se omite y el resumen lo
informa.

### Combinar o elegir

Hasta noviembre de 2026, el paquete elegía en cada establecimiento el modelo de menor
pérdida P80 en el backtest. Ningún modelo gana en todos lados, así que elegir parecía
razonable. Se midió si rinde, en noviembre de 2026, con datos al 1 de noviembre, en los
mismos 40 hospitales del estudio de [regresores](regresores.md)
(`experiments/combinar_vs_elegir.py`). En 11 fechas entre octubre de 2024 y mayo de 2026,
cada estrategia se aplicó con lo que se sabía en esa fecha (3 ventanas de 24 semanas) y se
evaluó en las 24 semanas siguientes, sin calibrar.

| Estrategia | Pérdida P80 frente a elegir (mediana) | Hospitales mejor / peor | WIS frente a elegir (mediana) | Hospitales mejor / peor |
|---|---|---|---|---|
| Elegir el de menor pérdida P80 (antes) | — | — | — | — |
| **Siempre Ensamble (ahora)** | **−7,4 %** | **29 / 11** | **−9,3 %** | **33 / 7** |
| Elegir, con Ensamble compitiendo | −0,6 % | 23 / 12 | −0,7 % | 29 / 6 |
| Siempre Armónico | −0,6 % | 20 / 19 | −1,2 % | 22 / 17 |
| Siempre MSTL | −0,4 % | 20 / 20 | −1,4 % | 24 / 16 |
| Siempre AutoARIMA | +2,5 % | 17 / 23 | −1,8 % | 21 / 19 |
| Siempre SeasonalNaive | +11,9 % | 14 / 26 | +21,7 % | 6 / 34 |

- **Ensamble rinde más que elegir**, de forma consistente: con una prueba de signos sobre
  los hospitales, p = 0,01 para la pérdida P80 y p < 0,01 para el WIS. La ventaja aparece
  en las dos mitades del período (−7,1 % hasta junio de 2025, −5,0 % desde julio) y frente
  a cada modelo por separado: le gana al Armónico en 29 hospitales de 40, al MSTL en 32 y
  al AutoARIMA en 34.
- **Elegir no rinde más que fijar un modelo.** Con 3 ventanas el ganador es en buena parte
  azar (ver [Ventanas del backtest](#ventanas-del-backtest)): elegir terminó usando
  SeasonalNaive en el 18 % de los casos, y es el que peor rinde después. Que Ensamble
  compita en la elección casi no cambia nada: se elige solo una de cada cuatro veces.
- **Coincide con la literatura.** Combinar pronósticos estuvo entre lo más preciso de la
  competencia M4 (Makridakis y otros, 2020), y la mediana descarta al modelo que se desvía.

Por eso Ensamble pronostica por defecto. Elegir sigue disponible con `--criterio` (o
`select_by` en `run_forecast`), por ejemplo si tu criterio es otro que la pérdida P80.

### Calibrar los intervalos

Hasta noviembre de 2026, los intervalos también se ensanchaban por defecto según el error
del backtest: un factor por cuantil, que nunca los angosta. En la misma medición, calibrar
empeoró la pérdida P80 del modelo elegido en 30 de 38 hospitales (mediana +4,7 %) y la de
Ensamble en 30 de 33 (+6,1 %), y el WIS de Ensamble en 37 de 39. Sin calibrar, lo real ya
quedaba bajo el P80 el 80 % de las semanas con el modelo elegido y el 84 % con Ensamble;
calibrar lo llevaba a 83 y 86 %, más margen del que el P80 promete.

Calibrar solo ayudó en las ventanas en que el modelo se quedó muy corto (lo real sobre el
P80 en más de la mitad de las semanas, típicamente porque la demanda cambió de nivel): ahí
bajó la pérdida un 9 %. Pero eso no se sabe de antemano. Por eso quedó desactivado por
defecto: `--calibrar` (o `calibrate=True`) lo activa, y el resumen lo sugiere cuando el P80
quedó bajo lo real en mucho más de 1 de cada 5 semanas del backtest. La
[hoja de ruta](roadmap.md) propone una calibración que también angoste.

### Elegir el criterio

Si eliges el modelo con `--criterio` (o `select_by` en `run_forecast`), o comparas dos con
`comparar` (`metric` en `compare_models`, `p80` por defecto), el criterio es una elección,
no un dato. El P80 equivale a decir que quedarse corto cuesta 4 veces más que pasarse. Si
quedarse corto cuesta *k* veces más que pasarse, el cuantil que corresponde es *k* / (*k* +
1) (Gneiting, 2011; las fuentes de esta página están en [Referencias](referencias.md)):

| `--criterio` | Mide | Úsalo si quedarse corto cuesta… |
|---|---|---|
| `p50` | pérdida en el P50 | lo mismo que pasarse |
| `p80` | pérdida en el P80 | 4 veces más |
| `p90` | pérdida en el P90 | 9 veces más |
| `p95` | pérdida en el P95 | 19 veces más |
| `media` | promedio de las pérdidas de P50 a P95 | no quieres fijar un costo: evalúa el valor central y la parte alta juntos |
| `wis` | puntaje de intervalos ponderado, de P5 a P95 | quieres evaluar el pronóstico completo, también la parte baja, como los centros de pronóstico epidemiológico |
| `mae` | error del valor central | solo te importa el valor central |

En Python también puedes pasar una función que reciba la tabla del backtest (una fila por
modelo, con `coverage_80` además de los errores) y devuelva el nombre del modelo. Por
ejemplo, quedarse con el más angosto entre los que cubrieron al menos el 75 % de las
semanas y, si ninguno lo logra, con el que más se acercó:

```python
def calibrado_y_angosto(tabla):
    cubren = tabla[tabla["coverage_80"] >= 0.75]
    if cubren.empty:  # ninguno cubre lo que promete
        return tabla["coverage_80"].idxmax()
    return cubren["width_80"].idxmin()

res = run_forecast(semanal, 26, select_by=calibrado_y_angosto)
```

Tres cuidados. Fija el criterio **antes** de mirar los resultados: si pruebas varios y te
quedas con el que deja mejor a tu modelo, encuentras un ganador por azar. Los cuantiles
altos se miden con pocas semanas: de las 78 que pronostica el backtest (42 distintas), solo
unas 4 deberían superar el P95, así que la pérdida P95 es ruidosa. Y el criterio cambia la
elección más de lo que parece: con datos al 1 de noviembre de 2026, en los 602
establecimientos de la demo, el modelo elegido difiere del que elige `p80` en el 42 % de
los casos con `p50` o `mae`, el 33 % con `p95`, el 32 % con `wis`, el 20 % con `p90` y el
13 % con `media`. Parte es que cada criterio premia algo distinto; parte es que los
modelos quedan tan parejos en el backtest que el ganador depende de detalles (ver
[Ventanas del backtest](#ventanas-del-backtest)).

### El WIS

El puntaje de intervalos ponderado (WIS, *weighted interval score*) es la medida con que el
CDC evalúa los pronósticos de influenza de FluSight y la que usó el COVID-19 Forecast Hub.
Mira el pronóstico completo: el error del valor central más, para los intervalos centrales
de 60, 80 y 90 % (de P20 a P80, de P10 a P90 y de P5 a P95), su ancho y una multa por cada
atención que quede fuera. Un intervalo angosto que deja fuera lo real paga la multa; uno
ancho que siempre acierta paga el ancho. Menor es mejor, y se mide en atenciones por
semana, como el MAE: si el pronóstico fuera solo el valor central, el WIS sería el MAE.

Para calcularlo, los modelos entregan además P5, P10 y P20. Los incluidos lo hacen, y con
`--criterio wis` esos cuantiles aparecen también en el pronóstico y en el CSV (con
`--calibrar`, calibrados igual que los de arriba). Un modelo propio que no los entregue queda fuera de la elección
con este criterio (su WIS sale vacío).

`media` se le parece, pero solo mira de la mediana hacia arriba: mide bien la parte que
importa para planificar con margen, no castiga un piso mal puesto y su valor no se puede
comparar con el de esos centros.

Fuentes: Bracher y otros (2021), que define el WIS, y la evaluación de FluSight (Mathis y
otros, 2024); citas completas en [Referencias](referencias.md).

### Ventanas del backtest

El backtest usa 3 ventanas tan largas como el horizonte, cada 8 semanas. Con `--criterio` o
`--calibrar`, son las que eligen el modelo y calibran los intervalos. Con el horizonte de
26 semanas eso implica:

- **Menos semanas de las que parece.** Las ventanas se superponen: juntas cubren las
  últimas 42 semanas (unos 10 meses), no 78, y las del medio cuentan tres veces. Con 12
  semanas de horizonte cubren 28. Con 4 no se superponen: son 12 semanas repartidas en las
  últimas 20.
- **Solo lo reciente.** La elección mira el último invierno y los meses que siguen. Ayuda si
  el establecimiento cambió hace poco y perjudica si ese año fue atípico.
- **Ganadores por poco.** Los modelos quedan tan parejos que el ganador cambia con
  detalles: con el criterio (ver arriba) o con las semanas nuevas de cada actualización.

**¿Ayudan más ventanas?** Se midió en noviembre de 2026, con datos al 1 de noviembre, en
los mismos 40 hospitales del estudio de [regresores](regresores.md)
(`experiments/ventanas_backtest.py`). En 5 fechas entre septiembre de 2025 y mayo de 2026 se
eligió el modelo con las 3, 6 o 9 ventanas anteriores (de 24 semanas, cada 8), como lo
habría hecho `run_forecast` en esa fecha, y se evaluó esa elección en las 24 semanas
siguientes, que ninguna de esas ventanas vio.

| Ventanas | Cambio mediano de la pérdida P80 frente a 3 | Hospitales mejor / peor que con 3 | El modelo elegido cambia de una fecha a la siguiente |
|---|---|---|---|
| 3 (por defecto) | — | — | 33 % |
| 6 | 0,0 % | 16 / 17 | 18 % |
| 9 | 0,0 % | 17 / 19 | 16 % |

- **Más ventanas no eligen mejor.** La pérdida del modelo elegido no cambió, ni la pérdida
  P80 ni el WIS. Con la calibración incluida, 9 ventanas salieron algo peor (mediana
  +3,7 %, mejor en 14 hospitales y peor en 26), sin llegar a ser una diferencia consistente.
- **Sí eligen más estable.** Con 6 ventanas, el modelo elegido cambia la mitad de las veces.
- **Por qué.** El desempeño pasado anticipa poco qué modelo rendirá mejor después. El
  elegido con 3 ventanas fue el mejor de los cuatro en las semanas siguientes solo el 30 %
  de las veces (al azar sería 25 %). Usar siempre el Armónico rindió igual que elegir
  (mediana −2,7 %, mejor en 23 hospitales y peor en 13, sin diferencia consistente). Y
  elegir sabiendo qué pasó, el mejor en cada ventana de prueba, habría bajado la pérdida
  P80 un 21 %. Hay diferencias entre los modelos, pero este historial no permite
  anticiparlas: con una medida tan ruidosa, la elección se sobreajusta (Cawley y Talbot,
  2010; ver [Referencias](referencias.md)). Por eso el paquete ya no elige por defecto
  (ver [Combinar o elegir](#combinar-o-elegir)).
- **La calibración tampoco mejoró en esas fechas.** Sin calibrar, lo real quedó bajo el
  P80 el 83 % de las semanas (se busca el 80 %). Calibrar lo subió a 85 % sin bajar la
  pérdida P80 (mediana 0,0 %; en total, +3 %). Ver [Calibrar los intervalos](#calibrar-los-intervalos).

Son 5 fechas en 8 meses y 40 hospitales: alcanza para ver que más ventanas no traen una
mejora clara, no para descartar una pequeña.

**Qué se decidió.** Se mantienen 3 ventanas. Por defecto ya no se elige el modelo (ver
[Combinar o elegir](#combinar-o-elegir)), así que las ventanas solo muestran cómo le fue a
cada uno. Si eliges con `--criterio`, más ventanas no eligen mejor y tardan más (cada
ventana ajusta todos los modelos de nuevo: 6 ventanas, el doble de tiempo); úsalas si te
importa que el modelo no cambie de una actualización a otra, por ejemplo en un informe
periódico.

**Cambiarlas.** `--ventanas N` y `--paso SEMANAS` en `pronosticar` y `demo`; `origins` y
`step` en `run_forecast`. Cada ventana necesita 104 semanas de historia antes de ella, así
que caben las que permita la historia: con datos desde 2022, en noviembre de 2026 caben 16
de 26 semanas cada 8. El resumen dice cuántas se usaron.

```bash
urg-forecast pronosticar 24-105 --ventanas 6
```

## Modelos por defecto

### Ensamble

Ajusta AutoARIMA, Armónico y MSTL y toma la mediana de sus pronósticos, cuantil
por cuantil. Es el que pronostica por defecto. Código en
`src/urgencias_core/models/ensemble.py`.

- **Para qué sirve:** combinar modelos razonables reduce el error promedio, porque la
  mediana descarta al que se desvía. No siempre gana una ventana en particular, pero en
  40 hospitales rindió mejor que elegir el mejor modelo de cada uno (ver
  [Combinar o elegir](#combinar-o-elegir)).
- **Costo:** el de los tres modelos juntos (unos pocos segundos). En el backtest no se
  ajustan de nuevo: se combinan los pronósticos que ya hicieron.
- **Para experimentar:** `MedianEnsemble` acepta cualquier conjunto de modelos. Pásalo
  como `partial(MedianEnsemble, miembros)`: si los miembros están en el mismo backtest,
  se combinan sus pronósticos en vez de ajustarlos dos veces.

### SeasonalNaive

Para cada semana del año toma lo que pasó esa misma semana en los años
anteriores y usa sus cuantiles. No tiene parámetros ni tendencia.

- **Para qué sirve:** es la vara mínima. Un modelo que no le gana a este no
  aporta nada.
- **Limitación:** si el nivel cambió (por ejemplo, una temporada respiratoria
  mucho más alta que las anteriores), queda corto y sus intervalos quedan muy
  estrechos.

### AutoARIMA

ARIMA estacional con periodo de 52 semanas, eligiendo los órdenes
automáticamente. Usa una búsqueda acotada (`FAST_ARIMA` en `models/registry.py`) que
tarda cerca de 1 s por ajuste; la búsqueda completa tarda unos 18 s y en la
comparación con datos en vivo mejoró el error en menos de 3%.

- **Para qué sirve:** captura bien la dinámica de corto plazo y, en la
  comparación, fue el mejor calibrado a 26 semanas.
- **Limitación:** con estacionalidad larga el ajuste es sensible y a veces no
  converge del todo (se ve en advertencias internas que la CLI oculta).

### Armónico

Regresión lineal sobre una tendencia y tres pares de senos y cosenos que
describen el ciclo anual (términos de Fourier). Lo que la regresión no explica
se modela con un ARIMA sin estacionalidad, que aporta la dinámica de corto plazo
y los intervalos. Código en `src/urgencias_core/models/harmonic.py`.

- **Para qué sirve:** representa el ciclo anual con pocos parámetros y es
  rápido. Ganó en varios hospitales.
- **Limitación:** la tendencia es lineal; un cambio brusco de nivel la arrastra.
  Sus intervalos tienden a quedar estrechos a horizontes largos.
- **Para experimentar:** `HarmonicRegression(k=6)` usa más términos y permite
  formas estacionales más finas; `trend=False` quita la tendencia.

### MSTL

Separa la serie en estacionalidad anual y tendencia, pronostica la tendencia con
ETS y le suma la estacionalidad.

- **Para qué sirve:** robusto y muy rápido; buen desempeño general.
- **Limitación:** necesita al menos dos años completos de historia.

## Modelos extra

### TBATS

Modela la estacionalidad con funciones trigonométricas, con transformación
Box-Cox y errores ARMA. Es un enfoque clásico para estacionalidades largas.

- **Para qué probarlo:** en pruebas con el snapshot quedó cerca de los mejores.
- **Costo:** tarda unos 15 s por ajuste, y el backtest hace varios. Con
  horizonte de 26 semanas y un establecimiento, cuenta con cerca de un minuto
  más.

### Theta

Método Theta con detección automática de estacionalidad. Con datos semanales y
periodo de 52, la prueba no detecta el ciclo anual y el modelo queda como una
tendencia suavizada.

- **Para qué probarlo:** como contraste. Muestra cuánto aporta modelar la
  estacionalidad. Si Theta le gana a los demás en tu establecimiento, la serie
  probablemente tiene poco ciclo anual.

### ArmónicoFeriados y ArmónicoCalendario

El Armónico más variables del **calendario chileno** por semana DEIS, que se conocen de
antemano y sirven también para las semanas que se pronostican (regresor `calendar()`):

- `ArmónicoFeriados`: cuántos feriados caen en día hábil esa semana.
- `ArmónicoCalendario`: además, los interferiados y la fracción de la semana en vacaciones
  escolares.

**Los feriados sí mejoran el pronóstico:** en 39 de los 40 hospitales con más atenciones
baja la pérdida P80 (−2,9 % en la mediana), y en 19 la mejora es consistente por sí sola.
El calendario completo no agrega más. Detalle y método en [Regresores](regresores.md).

### ArmónicoFluNet y ArmónicoFluNetProy

El Armónico más la **circulación viral**: la positividad semanal nacional de influenza y
VRS que el ISP reporta a la OMS ([FluNet](https://www.who.int/tools/flunet)), publicada con
unas dos semanas de atraso (regresor `flunet()`). Se diferencian en cómo llenan las
semanas que aún no se publican:

- `ArmónicoFluNet` (rezago 3): con el promedio histórico de esa semana del año.
- `ArmónicoFluNetProy` (rezago 1): con una proyección de la positividad desde la temporada
  en curso.

**No mejoran el total de atenciones** en ningún hospital de forma consistente. Detalle,
posibles razones y cómo probar otras fuentes en [Regresores](regresores.md).

## Agregar tu propio modelo

Cualquier clase con `fit(history, target_col)` y `predict(horizon)` que devuelva
`timestamp` y los cuantiles de `horizon.quantiles` (`q50, q80, q90, q95`; con
`--criterio wis` también `q5, q10, q20`) sirve. Guárdala en un `.py` en la carpeta donde
corres el comando y compárala con los incluidos:

```bash
urg-forecast pronosticar 24-105 -m mi_modelo:MiClase -m AutoARIMA -m MSTL   # gana el mejor
urg-forecast pronosticar 24-105 -m mi_modelo:MiClase -m Ensamble            # frente al de por defecto
```

El paso a paso, con un modelo completo y cómo leer el resultado, está en
[Extender](https://github.com/nicoveraz/urg-forecast-core/blob/main/README.md#extender).

## Ideas para seguir

- Modelar por separado las causas respiratorias o la urgencia pediátrica:
  `load_deis(..., source="deis")` las entrega por causa y grupo de edad.
- Sumar los feriados a los modelos por defecto, después de evaluarlos a 26 semanas y en
  establecimientos pequeños.
- Una calibración que también angoste los intervalos, por horizonte o conformal, y que
  rinda mejor que no calibrar.

El detalle de cada punto está en la [hoja de ruta](roadmap.md).
