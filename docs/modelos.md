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
automáticamente. Usa una búsqueda acotada (`FAST_ARIMA` en `pipeline.py`) que
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

### ArmónicoFeriados

El modelo Armónico más una variable con la cantidad de feriados que caen en día
hábil en cada semana, según el calendario chileno (biblioteca `holidays`). Los
feriados futuros se conocen, así que la variable sirve también para pronosticar.

- **Para qué probarlo:** las semanas con feriados (Fiestas Patrias, fin de año)
  suelen tener otra demanda. Es el ejemplo más simple de agregar una covariable.
- **Para experimentar:** `holidays_per_week()` está en
  `src/urgencias_core/models/harmonic.py`; sirve como plantilla para agregar
  otras variables (vacaciones escolares, campañas de vacunación, clima).

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
  temperatura, circulación viral.
- Un backtest con más ventanas para comparar con más confianza.
- Calibrar los intervalos por horizonte en vez de con un solo factor.
