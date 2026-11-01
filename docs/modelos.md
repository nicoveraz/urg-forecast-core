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
(máximo 26 semanas), separadas por 8 semanas. Gana el de menor **pérdida por
cuantil P80** promedio: una medida que castiga más quedarse corto que pasarse,
que es lo que importa al planificar dotación. Luego el ganador se reajusta con
toda la historia y sus intervalos se ensanchan si en el backtest resultaron
estrechos (ver `--sin-calibrar`).

Si un modelo falla al ajustarse, se omite y el resumen lo informa.

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

El modelo Armónico más variables del **calendario chileno** por semana DEIS, que se conocen
de antemano y sirven también para las semanas que se pronostican. Vienen del regresor
`calendar()` (`urgencias_core.regressors`, construido con
`features.calendar.weekly_calendar`):

- `ArmónicoFeriados`: cuántos feriados caen en día hábil esa semana.
- `ArmónicoCalendario`: además, los interferiados y la fracción de la semana en vacaciones
  escolares.

**Qué mostró con datos reales** (noviembre de 2026): en los 40 hospitales públicos con más
atenciones, hasta 36 ventanas de 4 semanas desde enero de 2024, comparando con el Armónico
en las mismas ventanas:

| Variante | Cambio mediano P80 | Ventanas ganadas | Veredicto por hospital |
|---|---|---|---|
| Feriados | −2,9% | 66% | mejora 19, empeora 0, sin diferencia 21 |
| Calendario completo | −3,4% | 62% | mejora 7, empeora 0, sin diferencia 33 |

**Los feriados sí mejoran el pronóstico.** La mediana por hospital es negativa en 39 de 40
y ningún hospital empeora. Si fuera azar, se esperaría que uno de los 40 saliera "mejora",
no 19. La ganancia es mayor en las ventanas de septiembre (−7,5%, gana en 88%: Fiestas
Patrias) y se mantiene el resto del año (−2,5%). Sumar interferiados y vacaciones
escolares no agrega: el cambio mediano es parecido, pero gana en menos ventanas y en
menos hospitales, y la pérdida total casi no baja (−0,4% contra −1,5% con solo feriados).
Las vacaciones son aproximadas (`_is_school_holiday`) y se parecen mucho al ciclo anual
que el Armónico ya modela.

- **Para experimentar:** `weekly_calendar(inicio, fin, CalendarConfig(...))` acepta eventos
  regionales propios (la Semana Musical de Frutillar viene como ejemplo) y fechas de
  vacaciones exactas si las tienes. `examples/04_regresor_externo.py` compara FluNet y el
  calendario en un establecimiento.

### ArmónicoFluNet y ArmónicoFluNetProy

El modelo Armónico más la **circulación viral**: la positividad semanal de influenza y de
virus respiratorio sincicial (VRS) que el ISP reporta a la OMS
([FluNet](https://www.who.int/tools/flunet)). Es el ejemplo de cómo sumar una fuente
externa con `HarmonicExogenous` (ver
[Agregar un regresor externo](https://github.com/nicoveraz/urg-forecast-core/blob/main/README.md#agregar-un-regresor-externo));
no son parte de los modelos por defecto.

- **De dónde salen los datos:** el workflow semanal copia la serie de Chile a la rama
  `datos` (`flunet_chl.csv`), así que el comando la lee desde el repositorio y no consulta
  a la OMS en cada uso. Es semanal desde 1997, separada en red centinela y no centinela,
  con unas dos semanas de atraso y **solo nacional**: no distingue regiones.
- **Backtest honesto:** en cada ventana usan solo las semanas de FluNet ya publicadas en
  ese momento. Se diferencian en cómo llenan las que faltan:
  - `ArmónicoFluNet` (rezago 3 semanas): con el promedio histórico de esa semana del
    año. La señal real llega solo a la primera semana del pronóstico.
  - `ArmónicoFluNetProy` (rezago 1 semana): con una proyección de la positividad desde la
    temporada en curso (Armónico sin tendencia y ARIMA), que arrastra si la temporada
    viene adelantada o atrasada.
- **Qué mostró con datos reales** (noviembre de 2026): en los 40 hospitales públicos con
  más atenciones, hasta 36 ventanas de 4 semanas desde enero de 2024 (inviernos 2024, 2025 y
  2026), comparando con el Armónico en las mismas ventanas:

  | Variante | Cambio mediano P80 | Ventanas ganadas | Veredicto por hospital |
  |---|---|---|---|
  | Promedio histórico, rezago 3 | +1,0% | 45% | mejora 0, empeora 7, sin diferencia 33 |
  | Proyección, rezago 3 | +0,9% | 45% | mejora 0, empeora 2, sin diferencia 38 |
  | Proyección, rezago 1 | +1,8% | 44% | mejora 0, empeora 3, sin diferencia 37 |

  **Ningún hospital mejoró de forma consistente.** Los que ganan un invierno no son los
  que ganan el siguiente: la correlación entre inviernos del cambio por hospital es
  cercana a cero (−0,25 a 0,24). El daño se concentra en invierno, cuando el regresor
  suma variabilidad sin aportar información que el ciclo anual no tenga. Proyectar la
  positividad reduce los hospitales que empeoran, pero no hace que mejore. Lo más
  probable: la positividad nacional poco agrega a lo que el ciclo anual explica del
  **total** de atenciones. Puede rendir más pronosticando solo las atenciones
  respiratorias o pediátricas, o con vigilancia regional.
- **Para experimentar:** `HarmonicFluNet` (en `src/urgencias_core/models/exogenous.py`)
  acepta `lag_weeks`, `report_delay_weeks`, `future`, `viruses` y tu propia serie en
  `positivity`. `urgencias_core.data.flunet.weekly_positivity` convierte los datos crudos
  de FluNet a semanas DEIS. `urg-forecast comparar CODIGO -m ArmonicoFluNetProy` repite la
  comparación para un establecimiento.

## Agregar tu propio modelo

Cualquier clase con `fit(history, target_col)` y `predict(horizon)` que devuelva
`timestamp, q50, q80, q90, q95` sirve. Guárdala en un `.py` en la carpeta donde
corres el comando y compárala con los incluidos:

```bash
urg-forecast pronosticar 24-105 -m mi_modelo:MiClase -m AutoARIMA -m MSTL
```

El paso a paso, con un modelo completo y cómo leer el resultado, está en
[Extender](https://github.com/nicoveraz/urg-forecast-core/blob/main/README.md#extender).

## Ideas para seguir

- Modelar por separado causas respiratorias o urgencia pediátrica, que
  `load_deis` ya entrega por causa y grupo de edad.
- Agregar covariables: vacaciones escolares (`features.calendar_features`),
  temperatura, o circulación viral regional (FluNet es solo nacional).
- Calibrar los intervalos por horizonte en vez de con un solo factor.
