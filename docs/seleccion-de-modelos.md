# Elección de modelos

El comando compara cuatro modelos y pronostica con el que tenga menor pérdida
por cuantil P80 en un backtest con varias ventanas. Esta nota resume por qué
son esos cuatro. El experimento completo está en
[`experiments/model_comparison.py`](../experiments/model_comparison.py).

## Datos y método

- DEIS en vivo, descargado el 5 de octubre de 2026: siete hospitales
  (Puerto Montt, Frutillar, Osorno, Valdivia, Castro, Sótero del Río y Peumo),
  unas 245 semanas completas cada uno desde 2022.
- Backtest con 6 ventanas separadas por 8 semanas, para horizontes de 12 y 26
  semanas, de modo que cada modelo se evalúa en distintas épocas del año.
- Métrica principal: pérdida por cuantil promedio (P50, P80, P90, P95),
  dividida por la de SeasonalNaive en el mismo establecimiento. Menos es mejor.
- Cobertura P80: fracción de semanas en que el valor real quedó bajo el P80.
  Lo ideal es cerca de 80%.

## Resultados

**Horizonte 12 semanas**

| Modelo | Pérdida relativa | Rango medio | Cobertura P80 | s/ajuste |
|---|---:|---:|---:|---:|
| Harmonic_k6 | 0.51 | 2.9 | 76% | 0.2 |
| Harmonic_k3 | 0.51 | 3.0 | 76% | 0.3 |
| AutoARIMA_full | 0.51 | 3.6 | 88% | 19.0 |
| MSTL_arima | 0.51 | 3.6 | 79% | 0.2 |
| AutoARIMA_fast | 0.53 | 4.7 | 86% | 1.5 |
| MSTL_ets | 0.55 | 4.1 | 81% | 0.0 |
| AutoETS | 0.69 | 6.6 | 88% | 0.3 |
| SeasonalNaive | 1.00 | 7.6 | 48% | 0.0 |

**Horizonte 26 semanas**

| Modelo | Pérdida relativa | Rango medio | Cobertura P80 | s/ajuste |
|---|---:|---:|---:|---:|
| AutoARIMA_full | 0.54 | 2.9 | 84% | 17.4 |
| AutoARIMA_fast | 0.54 | 4.1 | 80% | 1.1 |
| Harmonic_k3 | 0.56 | 3.7 | 70% | 0.3 |
| Harmonic_k6 | 0.56 | 3.1 | 69% | 0.2 |
| MSTL_arima | 0.56 | 4.0 | 72% | 0.3 |
| MSTL_ets | 0.57 | 3.6 | 79% | 0.0 |
| AutoETS | 0.83 | 7.0 | 91% | 0.2 |
| SeasonalNaive | 1.00 | 7.6 | 45% | 0.0 |

## Ganador por establecimiento (entre AutoARIMA, Armónico y MSTL)

| Establecimiento | 12 semanas | 26 semanas |
|---|---|---|
| Sótero del Río (14-101) | MSTL | AutoARIMA |
| Peumo (15-103) | Armónico | Armónico |
| Valdivia (22-100) | Armónico | MSTL |
| Osorno (23-100) | Armónico | Armónico |
| Puerto Montt (24-105) | MSTL | MSTL |
| Frutillar (24-115) | Armónico | Armónico |
| Castro (33-150) | AutoARIMA | AutoARIMA |

## Conclusiones

1. **AutoETS sale.** Es el peor después del baseline en todos los casos. Con
   periodo de 52 semanas, statsforecast descarta la estacionalidad de ETS y el
   pronóstico queda plano: no anticipa la baja de verano.
2. **Ningún modelo gana en todos lados.** AutoARIMA, Armónico y MSTL quedan a
   pocos puntos entre sí en promedio, y el ganador cambia según el
   establecimiento. Por eso se elige por establecimiento.
3. **El backtest usa varias ventanas** (3 por defecto, separadas por 8 semanas)
   para que la elección no dependa de calzar con una sola temporada.
4. **AutoARIMA usa una búsqueda acotada.** La búsqueda completa tarda unos 18 s
   por ajuste y mejora la pérdida en menos de 3%.
5. **Cobertura.** Armónico y MSTL cubren algo menos de lo nominal a 26 semanas
   (70–79%); AutoARIMA queda más cerca de 80%. Los intervalos son una
   referencia, no una garantía.

## Modelos extra

TBATS, Theta, Ensamble y ArmónicoFeriados se agregaron después para
experimentar y no forman parte de esta comparación. Se describen en
[`modelos.md`](modelos.md). Si en tu establecimiento alguno gana de forma
consistente, úsalo con `-m`.
