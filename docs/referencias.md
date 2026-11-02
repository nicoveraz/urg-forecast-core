# Referencias

Cada decisión de método del proyecto se apoya en literatura revisada por pares o en una
fuente oficial. Debajo de cada referencia está dónde se usa. Las citas y los DOI se
verificaron en noviembre de 2026 en PubMed, en las páginas de las revistas o en índices
bibliográficos (RePEc, JSTOR).

Lo que no está aquí son resultados propios, medidos con los datos del DEIS y documentados
con su fecha: la comparación de modelos ([Por qué estos modelos](seleccion-de-modelos.md)) y
la de regresores ([Regresores](regresores.md)). Son resultados, no literatura, y se pueden
reproducir con los comandos de cada página.

## Pronosticar la demanda de urgencias

- Wargon M, Guidet B, Hoang TD, Hejblum G. A systematic review of models for forecasting the
  number of emergency department visits. *Emerg Med J*. 2009;26(6):395–399.
  [doi:10.1136/emj.2008.062380](https://doi.org/10.1136/emj.2008.062380)
  — Punto de partida: los modelos revisados eran regresiones con variables de calendario o
  series de tiempo, y agregar datos meteorológicos no los mejoró. Por eso los modelos del
  paquete son simples y cada variable externa debe demostrar que ayuda.
- Jones SS, Thomas A, Evans RS, Welch SJ, Haug PJ, Snow GL. Forecasting daily patient volumes
  in the emergency department. *Acad Emerg Med*. 2008;15(2):159–170.
  [doi:10.1111/j.1553-2712.2007.00032.x](https://doi.org/10.1111/j.1553-2712.2007.00032.x)
  — Recomienda regresiones con variables de calendario, efectos de días especiales del lugar
  y autocorrelación de los residuos. Es la estructura del modelo Armónico (ciclo anual más
  errores ARIMA) y de `ArmónicoFeriados`.
- Silva E, Pereira MF, Vieira JT, Ferreira-Coimbra J, Henriques M, Rodrigues NF. Predicting
  hospital emergency department visits accurately: a systematic review. *Int J Health Plann
  Manage*. 2023;38(4):904–917.
  [doi:10.1002/hpm.3629](https://doi.org/10.1002/hpm.3629)
  — Las variables externas ayudaron solo en urgencias grandes y la elección del modelo
  dependió del tamaño. Por eso el modelo se elige establecimiento por establecimiento y los
  regresores se prueban en cada uno.

## Modelos

- Hyndman RJ, Athanasopoulos G. *Forecasting: Principles and Practice*. 3.ª ed. OTexts; 2021.
  <https://otexts.com/fpp3/>
  — SeasonalNaive como referencia, la regresión armónica dinámica (términos de Fourier con
  errores ARIMA) en que se basa el Armónico, y la evaluación con origen móvil.
- Hyndman RJ, Khandakar Y. Automatic time series forecasting: the forecast package for R.
  *J Stat Softw*. 2008;27(3):1–22.
  [doi:10.18637/jss.v027.i03](https://doi.org/10.18637/jss.v027.i03)
  — El algoritmo de AutoARIMA, que también modela los residuos del Armónico.
- Bandara K, Hyndman RJ, Bergmeir C. MSTL: a seasonal-trend decomposition algorithm for time
  series with multiple seasonal patterns. *Int J Oper Res*. 2025;52(1):79–98.
  [doi:10.1504/IJOR.2025.143957](https://doi.org/10.1504/IJOR.2025.143957)
  — El modelo MSTL.
- Garza A, Mergenthaler Canseco M, Challú C, Olivares KG. StatsForecast: lightning fast
  forecasting with statistical and econometric models. PyCon Salt Lake City; 2022.
  <https://github.com/Nixtla/statsforecast>
  — La implementación de AutoARIMA y MSTL que usa el paquete.
- Makridakis S, Spiliotis E, Assimakopoulos V. The M4 Competition: 100,000 time series and 61
  forecasting methods. *Int J Forecast*. 2020;36(1):54–74.
  [doi:10.1016/j.ijforecast.2019.04.014](https://doi.org/10.1016/j.ijforecast.2019.04.014)
  — Combinar métodos estuvo entre lo más preciso de la competencia, que también evaluó
  intervalos de predicción. Es la razón del modelo `Ensamble` y de comparar siempre contra
  una referencia simple.

## Evaluar pronósticos por cuantiles

- Koenker R, Bassett G. Regression quantiles. *Econometrica*. 1978;46(1):33–50.
  <https://www.jstor.org/stable/1913643>
  — La pérdida por cuantil (*pinball*) con que se miden P50, P80, P90 y P95.
- Gneiting T. Quantiles as optimal point forecasts. *Int J Forecast*. 2011;27(2):197–207.
  [doi:10.1016/j.ijforecast.2009.12.015](https://doi.org/10.1016/j.ijforecast.2009.12.015)
  — Cuando quedarse corto y pasarse tienen costos distintos, el mejor pronóstico es un
  cuantil, y la pérdida por cuantil es la que lo evalúa bien. Es la regla de `--criterio`: si
  quedarse corto cuesta *k* veces más, corresponde el cuantil *k* / (*k* + 1).
- Gneiting T, Raftery AE. Strictly proper scoring rules, prediction, and estimation. *J Am
  Stat Assoc*. 2007;102:359–378.
  [doi:10.1198/016214506000001437](https://doi.org/10.1198/016214506000001437)
  — Por qué estas medidas no se pueden engañar: un modelo obtiene su mejor puntaje
  pronosticando lo que realmente espera. También define el CRPS, del que la pérdida media y
  el WIS son aproximaciones.
- Gneiting T, Balabdaoui F, Raftery AE. Probabilistic forecasts, calibration and sharpness.
  *J R Stat Soc Series B Stat Methodol*. 2007;69:243–268.
  [doi:10.1111/j.1467-9868.2007.00587.x](https://doi.org/10.1111/j.1467-9868.2007.00587.x)
  — El principio de buscar el intervalo más angosto *siempre que esté calibrado*. Por eso
  un intervalo más angosto no es mejor por sí solo y por eso se muestra la cobertura del
  P80 (ver [Regresores](regresores.md)).
- Bracher J, Ray EL, Gneiting T, Reich NG. Evaluating epidemic forecasts in an interval
  format. *PLoS Comput Biol*. 2021;17(2):e1008618.
  [doi:10.1371/journal.pcbi.1008618](https://doi.org/10.1371/journal.pcbi.1008618)
  — El WIS (`--criterio wis`): qué mide, cómo se calcula y cómo se separa en ancho y multas.
- Mathis SM, Webber AE, León TM, et al. Evaluation of FluSight influenza forecasting in the
  2021–22 and 2022–23 seasons with a new target laboratory-confirmed influenza
  hospitalizations. *Nat Commun*. 2024;15:6289.
  [doi:10.1038/s41467-024-50601-9](https://doi.org/10.1038/s41467-024-50601-9)
  — El WIS y la cobertura como forma estándar de evaluar los pronósticos de influenza del CDC.

## Backtest y comparación de modelos

- Tashman LJ. Out-of-sample tests of forecasting accuracy: an analysis and review. *Int J
  Forecast*. 2000;16(4):437–450.
  <https://www.sciencedirect.com/science/article/pii/S0169-2070(00)00065-0>
  — El backtest con origen móvil: cada ventana se ajusta solo con lo anterior y se evalúa
  fuera de muestra, en varias ventanas para no depender de una sola temporada.
- Dixon WJ, Mood AM. The statistical sign test. *J Am Stat Assoc*. 1946;41:557–566.
  [doi:10.2307/2280577](https://doi.org/10.2307/2280577)
  — La prueba de signos de `compare_models`: cuenta en cuántas ventanas gana cada modelo,
  sin suponer cómo se distribuye el error.

## Calibración de intervalos

- Angelopoulos AN, Bates S. Conformal prediction: a gentle introduction. *Found Trends Mach
  Learn*. 2023;16(4):494–591.
  [doi:10.1561/2200000101](https://doi.org/10.1561/2200000101)
  — La idea detrás de la calibración: ensanchar los intervalos según los errores fuera de
  muestra. La del paquete es una versión simple (un factor por cuantil, sacado del
  backtest) y no tiene las garantías de la predicción conformal; por eso la
  [hoja de ruta](roadmap.md) propone una calibración por horizonte o conformal.

## Variables externas

- Satia I, Cusack R, Greene JM, O'Byrne PM, Killian KJ, Johnston N. Prevalence and
  contribution of respiratory viruses in the community to rates of emergency department
  visits and hospitalizations with respiratory tract infections, chronic obstructive
  pulmonary disease and asthma. *PLoS One*. 2020;15(2):e0228544.
  [doi:10.1371/journal.pone.0228544](https://doi.org/10.1371/journal.pone.0228544)
  — La circulación viral explicó buena parte de las consultas de urgencia por infecciones
  respiratorias (57 %), una serie específica, no el total. Es lo que se observó aquí con
  FluNet y el total de atenciones, y la razón de probarla con series respiratorias.
- Araz OM, Bentley D, Muelleman RL. Using Google Flu Trends data in forecasting
  influenza-like-illness related ED visits in Omaha, Nebraska. *Am J Emerg Med*.
  2014;32(9):1016–1023.
  [doi:10.1016/j.ajem.2014.05.052](https://doi.org/10.1016/j.ajem.2014.05.052)
  — Un indicador de vigilancia mejoró el pronóstico de consultas por enfermedad tipo
  influenza, otra vez una serie específica.

## Datos y software

- Departamento de Estadísticas e Información de Salud (DEIS), Ministerio de Salud de Chile.
  Atenciones de urgencia, datos abiertos. <https://deis.minsal.cl/#datosabiertos>
- Organización Mundial de la Salud. FluNet. <https://www.who.int/tools/flunet>
- *holidays*, paquete de Python: feriados de Chile. <https://python-holidays.readthedocs.io/>
