# deis_demo_snapshot.parquet

Lo usan `urg-forecast demo --offline`, `--offline` en los demás comandos, el respaldo
cuando el DEIS no responde, los tests, los ejemplos y la página para desarrolladores. Los
comandos en línea leen siempre los datos más recientes.

Snapshot de los datos abiertos *Atenciones de Urgencia* del DEIS MINSAL, con todas las
causas y grupos de edad, filtrado a los dos hospitales de demostración de la región de
Los Lagos (Servicio de Salud Reloncaví):

- `24-105`: Hospital de Puerto Montt.
- `24-115`: Hospital de Frutillar.

## Generación

- Generado el **13-04-2026** con `scripts/construir_snapshot.py`, desde los
  archivos anuales del DEIS. Datos hasta el **11-04-2026**.
- Se regenera antes de cada versión con el workflow `snapshot` (Actions → snapshot → Run
  workflow), que abre una rama con el cambio para revisarlo en un PR.
- Origen: `https://repositoriodeis.minsal.cl/SistemaAtencionesUrgencia/AtencionesUrgencia{AÑO}.zip`
  (CSV separado por punto y coma, codificación latin-1).

## Cobertura

| Año | Filas | Nota |
|------|------|------|
| 2021 | 27.760 | Año completo |
| 2022 | 28.720 | Año completo |
| 2023 | 28.760 | Año completo |
| 2024 | 28.960 | Año completo |
| 2025 | 28.749 | Año completo |
| 2026 | 8.159 | Año parcial, hasta el 11-04-2026 |

Total: 151.108 filas, una por (hospital, fecha, causa, grupo de edad).

## Años no incluidos

- **2017–2019:** el DEIS los publicó como `.xlsx` + `.mdb` dentro del ZIP anual y el
  lector de `deis.py` los omite. Ver `docs/roadmap.md`.
- **2020:** el archivo trae una fila de cabecera corrupta. Se excluye por la pandemia.

## Atribución

DEIS, Departamento de Estadísticas e Información de Salud, Ministerio de Salud de Chile,
<https://deis.minsal.cl/>. Datos abiertos bajo el marco de datos abiertos de Chile. Este
repositorio redistribuye un subconjunto filtrado con fines de enseñanza y
reproducibilidad; para cualquier uso de investigación u operacional del dataset completo,
descárgalo directamente desde la fuente.
