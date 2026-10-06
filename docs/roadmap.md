# Roadmap / Hoja de ruta

Known gaps, deliberately left out of the base. Each one is a good first
contribution. / Brechas conocidas que quedaron fuera de la base a propósito.
Cada una sirve como primera contribución.

## Datos

- **Archivos DEIS 2017–2019.** Vienen como `.xlsx` + `.mdb` dentro del ZIP
  anual; el lector actual solo parsea CSV y los salta con una advertencia.
- **Archivo DEIS 2020.** Tiene una cabecera corrupta en la fuente. Está excluido
  por defecto (COVID), así que el valor es bajo.
- **Series por causa o edad.** `data.deis.fetch()` ya entrega conteos por causa
  y grupo de edad, pero el pronóstico usa solo el total. Modelar por separado
  las causas respiratorias o la urgencia pediátrica es el paso natural.

## Modelos

- **Backtest rolling.** Hoy el backtest es un único holdout al final de la
  serie. Varias ventanas darían una estimación del error más estable.
- **Variables exógenas.** El calendario chileno (`features.calendar`) está
  disponible pero no entra a los modelos por defecto; tampoco el clima.
- **Granularidad diaria.** El pipeline es semanal. Pasar a diario exige revisar
  el rezago de reporte del DEIS.

## Operación

- **Actualización del snapshot.** Un workflow programado que regenere el
  snapshot y las figuras del README y abra un PR para revisión.
