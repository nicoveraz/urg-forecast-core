# Hoja de ruta

Lo que falta, ordenado por impacto dentro de cada área. Cada punto dice por qué importa y
por dónde empezar; los marcados como **primera contribución** son acotados y no requieren
conocer todo el paquete. Dónde va cada cosa está en [Arquitectura](arquitectura.md).

## Datos

- **Causas y grupos de edad en la copia semanal.** La rama `datos` guarda solo el total
  diario por establecimiento. `load_deis(..., source="deis")` sí trae causa y grupo de edad,
  pero descarga los archivos anuales completos (cientos de MB). Agregar a la copia semanal
  unas pocas series agregadas, como las causas respiratorias o la urgencia pediátrica,
  permitiría analizarlas y pronosticarlas desde el comando y la demo. Es la base de varios
  puntos de abajo. Dónde: `data/mirror.py` (`build_mirror`) y `data/series.py`.
- **Historia anterior a la pandemia.** La copia semanal parte en 2021 y 2020–2021 se
  excluyen, así que los modelos entrenan con unos cuatro años y medio. Más temporadas darían
  backtests más confiables y un año típico más estable. Los archivos DEIS 2017–2019 vienen
  como `.xlsx` + `.mdb` dentro del ZIP anual y el lector actual los salta con una
  advertencia. Hay que leer ese formato y revisar los años anteriores. Dónde:
  `data/deis.py` (`load_year`).
- **Archivo DEIS 2020.** Tiene una cabecera corrupta en la fuente. Como 2020 se excluye por
  la pandemia, el valor es bajo.

## Análisis

- **Por causa y grupo de edad.** `analysis/` describe el total. Con las series del primer
  punto de Datos, las mismas funciones sirven sin cambios para las atenciones respiratorias
  o pediátricas.
- **Comparar establecimientos.** Hoy todo es por establecimiento. Agregados por Servicio de
  Salud o región, y una tabla con el cambio interanual de cada uno, ayudarían a ver la red.
  **Primera contribución:** una función en `analysis/` que reciba varias series semanales.

## Modelos y evaluación

- **Intervalos que se quedan cortos cuando cambia el nivel.** Cuando la demanda sube de un
  año a otro, el P80 queda bajo lo real en muchas más semanas de lo esperado (en el Hospital
  de Puerto Montt, a octubre de 2026, cubrió el 26 % de las semanas del backtest). Hoy
  `eval/calibration.py` lo corrige ensanchando las bandas con un solo factor para todo el
  horizonte. Faltan una calibración por horizonte (o conformal) y medir la cobertura en
  muchos establecimientos, no solo en uno. Una primera medición, en 40 hospitales y 5 fechas
  entre septiembre de 2025 y mayo de 2026, dio que lo real quedó bajo el P80 el 83 % de las
  semanas y que calibrar lo subió a 85 % sin bajar la pérdida P80 (ver
  [Ventanas del backtest](modelos.md#ventanas-del-backtest)).
- **Elegir o combinar.** Elegir el modelo por establecimiento rindió igual que usar siempre
  el Armónico, y elegir con 6 o 9 ventanas tampoco eligió mejor (mismo enlace). Falta medir
  si combinar los modelos (`Ensamble`) rinde más que elegir uno.
- **Feriados en los modelos por defecto.** `ArmónicoFeriados` mejoró la pérdida P80 en 19 de
  los 40 hospitales con más atenciones y no empeoró en ninguno (ver
  [Regresores](regresores.md)), pero hoy es opcional. Antes de sumarlo a los modelos por
  defecto falta evaluarlo a 26 semanas (el horizonte por defecto), en establecimientos
  pequeños (SAPU, SUR) y en cómo cambia la elección del modelo.
- **Granularidad diaria.** Todo es semanal. Pasar a diario exige revisar el rezago con que
  el DEIS completa cada día.

## Regresores

- **Virus para lo que sí depende de los virus.** La positividad nacional de FluNet no mejoró
  el total de atenciones. Con las series por causa del primer punto de Datos, vale la pena
  probarla con las atenciones respiratorias o pediátricas, y con vigilancia regional si
  existe una fuente pública.
- **Otras variables.** Temperatura, contaminación o campañas de vacunación, con el mismo
  estándar (`Regressor` y `compare_models` en varios establecimientos). Hay que confirmar
  primero que la fuente es pública y cuánto tarda en publicarse, y cuidar que la variable
  no repita lo que el ciclo anual ya explica. **Primera contribución:** un `Regressor` nuevo
  con su comparación documentada, aunque el resultado sea negativo.

## Operación y mantenimiento

- **Quitar las rutas antiguas en 0.5.** `urgencias_core.pipeline`,
  `urgencias_core.eval.baselines` y `run_harness` siguen funcionando con un aviso desde 0.4
  y se eliminan en la próxima versión menor.
- **Demo.** La comparación de regresores cubre los 40 establecimientos con más atenciones
  (unos 30 minutos por semana en la CI). Si se amplía, conviene guardar los resultados y
  recalcular solo los establecimientos con datos nuevos.
