# Datos de urg-forecast

Esta rama la genera automáticamente cada semana el workflow `datos.yml` del
repositorio. No la edites a mano: se reemplaza completa en cada actualización.

| Archivo | Contenido |
|---|---|
| `diario.parquet` | atenciones de urgencia totales por establecimiento y día (`facility_code`, `date`, `count`) |
| `establecimientos.csv` | código, nombre, tipo, región, comuna y servicio de salud de cada establecimiento, con el rango de fechas disponible |
| `meta.json` | fecha de generación, años DEIS incluidos y última fecha con datos |
| `flunet_chl.csv` | vigilancia de laboratorio de virus respiratorios de Chile reportada a la OMS (FluNet): muestras procesadas y detecciones por virus y semana, red centinela y no centinela. La usa el modelo de ejemplo `ArmónicoFluNet` |
| `demo/` | pronósticos precalculados para la página de demo |

`urg-forecast` lee estos archivos por defecto, para no descargar los archivos
anuales completos del DEIS en cada uso. Con `--fuente deis` se descargan
directo desde la fuente.

**Fuente y atribución.** DEIS, Departamento de Estadísticas e Información de
Salud, Ministerio de Salud de Chile: datos abiertos *Atenciones de Urgencia*
(<https://deis.minsal.cl/#datosabiertos>). Esta copia contiene solo los totales
diarios (sección 1) de los establecimientos de la red pública. Si usas estos
datos, mantén la atribución al DEIS.

`flunet_chl.csv`: Organización Mundial de la Salud, FluNet
(<https://www.who.int/tools/flunet>), con datos que reporta el Instituto de Salud Pública
de Chile. Se publica con unas dos semanas de rezago y solo a nivel nacional.
