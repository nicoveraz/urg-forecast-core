# Modelos

`urg-forecast` trae ocho modelos. Cuatro se comparan por defecto y se usa el
que tenga menor error en el backtest. Los otros cuatro están para experimentar
y se activan con `-m`. Todos son aproximaciones iniciales: ninguno está ajustado
a un establecimiento en particular.

```bash
urg-forecast modelos                                   # lista con descripción
urg-forecast pronosticar 24-105 -m TBATS -m Ensamble   # compara solo esos
urg-forecast pronosticar 24-105 -m Armonico            # usa uno sin comparar
```

Los nombres no distinguen mayúsculas ni tildes. Cuando indicas un solo modelo
igual se hace el backtest, para que veas su error, pero no hay elección.

## Cómo se comparan

Cada modelo se ajusta en tres ventanas de backtest tan largas como el horizonte
(máximo 26 semanas), separadas por 8 semanas (`--ventanas` y `--paso` lo cambian; ver
[Ventanas del backtest](#ventanas-del-backtest)). Por defecto gana el de menor **pérdida por
cuantil P80** promedio: una medida que castiga más quedarse corto que pasarse,
que es lo que importa al planificar dotación. Luego el ganador se reajusta con
toda la historia y sus intervalos se ensanchan si en el backtest resultaron
estrechos (ver `--sin-calibrar`).

Combinar modelos en vez de elegir uno también es posible: agrega `Ensamble` (la mediana de
AutoARIMA, Armónico y MSTL) a los modelos y compite en el mismo backtest. Si un modelo falla
al ajustarse, se omite y el resumen lo informa.

### Elegir el criterio

El P80 es una elección, no un dato: equivale a decir que quedarse corto cuesta 4 veces más
que pasarse. Quien usa el paquete puede elegir otro con `--criterio` (o `select_by` en
`run_forecast` y `metric` en `compare_models`). Si quedarse corto cuesta *k* veces más que
pasarse, el cuantil que corresponde es *k* / (*k* + 1) (Gneiting, 2011; las fuentes de esta
página están en [Referencias](referencias.md)):

| `--criterio` | Mide | Úsalo si quedarse corto cuesta… |
|---|---|---|
| `p50` | pérdida en el P50 | lo mismo que pasarse |
| `p80` (por defecto) | pérdida en el P80 | 4 veces más |
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
`--criterio wis` esos cuantiles aparecen también en el pronóstico y en el CSV, calibrados
igual que los de arriba. Un modelo propio que no los entregue queda fuera de la elección
con este criterio (su WIS sale vacío).

`media` se le parece, pero solo mira de la mediana hacia arriba: mide bien la parte que
importa para planificar con margen, no castiga un piso mal puesto y su valor no se puede
comparar con el de esos centros.

Fuentes: Bracher y otros (2021), que define el WIS, y la evaluación de FluSight (Mathis y
otros, 2024); citas completas en [Referencias](referencias.md).

### Ventanas del backtest

Por defecto el modelo se elige, y sus intervalos se calibran, con 3 ventanas tan largas como
el horizonte, cada 8 semanas. Con el horizonte de 26 semanas eso implica:

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
  2010; ver [Referencias](referencias.md)).
- **La calibración tampoco mejoró en esas fechas.** Sin calibrar, lo real quedó bajo el
  P80 el 83 % de las semanas (se busca el 80 %). Calibrar lo subió a 85 % sin bajar la
  pérdida P80 (mediana 0,0 %; en total, +3 %). La [hoja de ruta](roadmap.md) propone una
  calibración mejor.

Son 5 fechas en 8 meses y 40 hospitales: alcanza para ver que más ventanas no traen una
mejora clara, no para descartar una pequeña.

**Qué se decidió.** Se mantienen 3 ventanas por defecto. Más ventanas no eligen mejor,
tardan más (cada ventana ajusta todos los modelos de nuevo: 6 ventanas, el doble de
tiempo) y miran más atrás. En la demo, que actualiza 602 establecimientos cada semana en
unos 45 minutos, duplicarían ese tiempo. Si te importa que el modelo no cambie de una
actualización a otra, por ejemplo en un informe periódico, usa 6.

**Cambiarlas.** `--ventanas N` y `--paso SEMANAS` en `pronosticar` y `demo`; `origins` y
`step` en `run_forecast`. Cada ventana necesita 104 semanas de historia antes de ella, así
que caben las que permita la historia: con datos desde 2022, en noviembre de 2026 caben 16
de 26 semanas cada 8. El resumen dice cuántas se usaron.

```bash
urg-forecast pronosticar 24-105 --ventanas 6
```

## Modelos por defecto

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

### Ensamble

Ajusta AutoARIMA, Armónico y MSTL y toma la mediana de sus pronósticos, cuantil
por cuantil. Código en `src/urgencias_core/models/ensemble.py`.

- **Para qué probarlo:** combinar modelos razonables suele reducir el error
  promedio, porque la mediana descarta al que se desvía. No siempre gana una
  ventana en particular, pero suele ser más estable.
- **Costo:** el de los tres modelos juntos (unos pocos segundos).
- **Para experimentar:** `MedianEnsemble` acepta cualquier conjunto de modelos.

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
urg-forecast pronosticar 24-105 -m mi_modelo:MiClase -m AutoARIMA -m MSTL
```

El paso a paso, con un modelo completo y cómo leer el resultado, está en
[Extender](https://github.com/nicoveraz/urg-forecast-core/blob/main/README.md#extender).

## Ideas para seguir

- Modelar por separado las causas respiratorias o la urgencia pediátrica:
  `load_deis(..., source="deis")` las entrega por causa y grupo de edad.
- Sumar los feriados a los modelos por defecto, después de evaluarlos a 26 semanas y en
  establecimientos pequeños.
- Calibrar los intervalos por horizonte en vez de con un solo factor.

El detalle de cada punto está en la [hoja de ruta](roadmap.md).
