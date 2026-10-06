# deis_demo_snapshot.parquet

Lo usan `urg-forecast demo --offline`, el respaldo cuando el DEIS no responde y
los tests. Los comandos en línea siempre descargan los datos DEIS más recientes.

Snapshot congelado de los datos abiertos *Atenciones de Urgencia* del DEIS
MINSAL, filtrado a los dos hospitales de demostración de la región de Los Lagos:

- `24-105`: Hospital de Puerto Montt (también conocido como Hospital Base de
  Puerto Montt). Alta complejidad. Servicio de Salud Reloncaví.
- `24-115`: Hospital de Frutillar. Baja complejidad. Servicio de Salud
  Reloncaví.

## Generación

- Descargado con `urgencias_core.data.deis.fetch_demo_hospitals(start_year=2021,
  end_year=2026)` el **13 de abril de 2026**.
- Patrón de URL de origen:
  `https://repositoriodeis.minsal.cl/SistemaAtencionesUrgencia/AtencionesUrgencia{AÑO}.zip`
- Formato: CSV separado por punto y coma, codificación latin-1.

## Cobertura

| Año | Filas | Nota |
|------|------|------|
| 2021 | 27.760 | Año completo |
| 2022 | 28.720 | Año completo |
| 2023 | 28.760 | Año completo |
| 2024 | 28.960 | Año completo |
| 2025 | 28.749 | Año completo |
| 2026 | 8.159 | Año parcial, hasta el 11-04-2026 (el archivo se actualiza semanalmente en la campaña de invierno) |

Total: 151.108 filas, una por (hospital, fecha, grupo de causa).

## Años no incluidos

- **2017–2019:** el DEIS los publicó como `.xlsx` + `.mdb` dentro del ZIP
  anual, y el lector CSV de `deis.py` los omite. Ver `docs/roadmap.md`.
- **2020:** el archivo trae una fila de cabecera corrupta. Se excluye por
  defecto por la pandemia, y el lector lo omitiría de todas formas.

## Regenerar

```bash
rm src/urgencias_core/data/_fixtures/deis_demo_snapshot.parquet
uv run python -c "
from urgencias_core.data.deis import fetch_demo_hospitals
df = fetch_demo_hospitals(start_year=2021)
df.to_parquet('src/urgencias_core/data/_fixtures/deis_demo_snapshot.parquet', index=False, compression='zstd')
print(len(df), 'filas')
"
```

## Atribución

DEIS, Departamento de Estadísticas e Información de Salud, Ministerio de Salud
de Chile, <https://deis.minsal.cl/>. Datos abiertos bajo el marco de datos
abiertos de Chile. Este repositorio redistribuye un subconjunto filtrado con
fines de enseñanza y reproducibilidad; para cualquier uso de investigación u
operacional del dataset completo, descárgalo directamente desde la fuente.
