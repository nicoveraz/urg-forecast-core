# Política de seguridad

## Versiones con soporte

`urg-forecast-core` está en la serie 0.x; solo la última versión publicada en
PyPI recibe correcciones.

| Versión | Soporte |
|---|---|
| 0.2.x | ✅ |
| < 0.2 | ❌ |

## Reportar una vulnerabilidad

Por favor **no abras un issue público** por una posible vulnerabilidad.

Repórtala de forma privada con
["Report a vulnerability"](https://github.com/nicoveraz/urg-forecast-core/security/advisories/new)
de GitHub (Security → Advisories) o por correo a **nicovera@quetru.cl**.

Incluye una descripción, los pasos para reproducirla y la versión afectada. Es
un proyecto con un solo mantenedor: el primer acuse de recibo puede tardar un par
de semanas. Las correcciones se publican como una nueva versión en PyPI y se
anotan en `CHANGELOG.md`.

## Alcance

Es código de referencia para análisis y pronóstico; no maneja autenticación ni
procesa entradas de red no confiables. El cliente DEIS descarga desde una
dirección pública fija y el paquete nunca envía datos a ninguna parte.

`-m modulo:Clase` importa y ejecuta código Python desde la carpeta actual: usa
solo módulos que conozcas.
