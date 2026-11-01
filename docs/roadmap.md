# Hoja de ruta

Brechas conocidas que quedaron fuera de la base a propósito. Cada una sirve como
primera contribución. Para ideas de modelos, revisa también la sección final de
[`modelos.md`](modelos.md).

## Datos

- **Archivos DEIS 2017–2019.** Vienen como `.xlsx` + `.mdb` dentro del ZIP
  anual; el lector actual solo parsea CSV y los salta con una advertencia.
- **Archivo DEIS 2020.** Tiene una cabecera corrupta en la fuente. Está excluido
  por defecto (COVID), así que el valor es bajo.
- **Series por causa o edad.** `data.deis.fetch()` ya entrega conteos por causa
  y grupo de edad, pero el pronóstico usa solo el total. Modelar por separado
  las causas respiratorias o la urgencia pediátrica es el paso natural.

## Estructura

El reordenamiento en curso (ver [`arquitectura.md`](arquitectura.md)):

- **Análisis descriptivo** (`analysis/`): estacionalidad, tendencia, comparación
  interanual, semanas pico y día de la semana, sobre la misma serie semanal.
- **Regresores unificados:** el calendario chileno (`features.calendar`) y FluNet con el
  mismo formato de tabla, distinguiendo variables con futuro conocido (feriados,
  vacaciones) de las que se publican con atraso (virus). Hoy `ArmónicoFeriados` arma los
  feriados por su cuenta y `HarmonicExogenous` solo sirve con el Armónico.

## Modelos

- **Granularidad diaria.** Todo es semanal. Pasar a diario exige revisar el rezago de
  reporte del DEIS.
- **Calibración por horizonte.** Hoy los intervalos se ensanchan con un solo factor para
  todo el horizonte.

## Operación

- **Snapshot incluido.** El snapshot offline del paquete (dos hospitales) se
  actualiza a mano; podría regenerarse desde la copia semanal en cada versión.
- **Más series en la copia semanal.** Hoy la rama `datos` guarda solo el total
  diario; agregar causas respiratorias o grupos de edad permitiría modelarlos
  sin descargar el DEIS completo.
