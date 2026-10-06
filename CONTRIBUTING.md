# Cómo contribuir

`urg-forecast-core` es una base abierta, mantenida en la medida de lo posible.
Haz un fork, adáptalo a tu establecimiento o úsalo dentro de tu propio producto.
Los issues y pull requests son bienvenidos; mientras esté en 0.x, la API puede
cambiar entre versiones menores. Si necesitas soporte comercial o un desarrollo
a medida sobre esta base, contacta al autor.

Toda participación se rige por el [Código de Conducta](CODE_OF_CONDUCT.md).

## Reportar problemas y pedir ayuda

- **Errores y propuestas:** abre un issue en
  <https://github.com/nicoveraz/urg-forecast-core/issues>. Si es un error,
  incluye la versión (`urg-forecast --version`), la versión de Python, el
  sistema operativo, el comando que corriste y el mensaje de error completo.
- **Preguntas de uso:** abre un issue con la etiqueta *question*.
- **Seguridad:** revisa [SECURITY.md](SECURITY.md); no abras un issue público
  por una posible vulnerabilidad.

No pegues datos de pacientes en issues ni pull requests.

## Proponer cambios

Haz un fork, crea una rama y abre un pull request contra `main`. Antes de
subirlo, revisa que pasen las verificaciones de abajo; el CI corre lo mismo
(lint, formato, tests en Python 3.11 y 3.12, build e instalación del wheel) en
cada pull request.

La documentación se escribe primero en español (`README.md`, `docs/`). La
traducción al inglés (`README.en.md`) se actualiza cuando corresponde. Los
docstrings y comentarios del código van en inglés.

El sitio (<https://nicoveraz.github.io/urg-forecast-core/>) se arma con MkDocs a
partir del README y de `docs/`: las páginas Inicio, Uso, Extender y
Acerca incluyen secciones del README marcadas con comentarios
`<!-- sitio:... -->`, así que se editan en el README. Para verlo localmente:

```bash
uv run --only-group docs mkdocs serve
```

## Desarrollo

```bash
uv sync --dev                # paquete + herramientas de desarrollo
uv run pytest -q             # tests
uv run ruff check .          # lint
uv run ruff format .         # formato (ruff es el único formateador)
pre-commit install           # opcional: lint y formato al hacer commit
```

El paquete usa estructura `src/` y una sola instalación, sin extras. La idea es
que siga siendo chico: el alcance es el pronóstico semanal con datos DEIS más lo
necesario para extenderlo. Los modelos nuevos van en
`src/urgencias_core/models/` y se registran en `pipeline.extra_models()` y
`MODEL_INFO`, con su sección en `docs/modelos.md`. El análisis por atención y la
simulación quedan fuera de este repositorio.

## Publicar una versión

Las versiones se publican en PyPI con
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC) desde
`.github/workflows/publish.yml`, sin tokens guardados como secretos.

Configuración única: en PyPI, agrega este repositorio y el entorno `pypi` como
publicador de confianza del proyecto `urg-forecast-core`.

En cada versión:

1. Sube `version` en `pyproject.toml` (semver) y en `CITATION.cff`.
2. Mueve las notas de `## [Sin publicar]` en `CHANGELOG.md` a un nuevo
   encabezado `## [X.Y.Z] - AAAA-MM-DD` y actualiza los enlaces de comparación.
3. Haz commit, crea el tag y súbelo:

   ```bash
   git tag vX.Y.Z
   git push origin main --tags
   ```

El workflow `publish` corre los tests, verifica que el tag coincida con la
versión del paquete, construye, publica en PyPI y crea el release en GitHub con
la sección del changelog como notas.

## Archivo en Zenodo (DOI para citar)

Cada release se archiva en [Zenodo](https://zenodo.org/). Los metadatos del
archivo salen de `.zenodo.json`; `CITATION.cff` define la cita que muestra
GitHub. La integración ya está activa: Zenodo detecta el release de GitHub y
genera un DOI de versión, además del DOI concepto
([10.5281/zenodo.21449610](https://doi.org/10.5281/zenodo.21449610)), que
siempre apunta a la última versión.

El ORCID y la afiliación del autor están en `CITATION.cff` y `.zenodo.json`;
mantenlos sincronizados si cambia la autoría.
