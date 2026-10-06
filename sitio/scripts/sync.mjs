// Generates the site's pages from the repo's own docs, so there is a single
// source: README.md (sections between <!-- sitio:... --> markers), docs/*.md
// and CHANGELOG.md. Output goes to src/content/docs/ (git-ignored).
import { copyFileSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, "..", "..");
const out = join(here, "..", "src", "content", "docs");
const BASE = "/urg-forecast-core";
const BLOB = "https://github.com/nicoveraz/urg-forecast-core/blob/main/docs/";

const read = (p) => readFileSync(join(repo, p), "utf8");
const readme = read("README.md");

function section(name, next) {
  const start = readme.indexOf(`<!-- sitio:${name} -->`);
  const end = readme.indexOf(`<!-- sitio:${next} -->`);
  if (start < 0 || end < 0) throw new Error(`missing README marker sitio:${name}/${next}`);
  return readme.slice(start, end).replace(/<!-- sitio:\w+ -->\n?/g, "").trim();
}

// README anchor -> page where that section lives on the site.
const ANCHORS = {
  "una-base-no-un-producto": "uso/#una-base-no-un-producto",
  "referencia-de-comandos": "uso/#referencia-de-comandos",
  modelos: "modelos/",
  extender: "extender/",
};

const README = "https://github.com/nicoveraz/urg-forecast-core/blob/main/README.md#";

// Repo files that are also site pages (community docs, changelog).
const PAGES = {
  "CONTRIBUTING.md": "contribuir/",
  "CODE_OF_CONDUCT.md": "conducta/",
  "SECURITY.md": "seguridad/",
  "CHANGELOG.md": "cambios/",
};
const BLOB_ROOT = "https://github.com/nicoveraz/urg-forecast-core/blob/main/";

function fixLinks(md, page) {
  for (const [file, target] of Object.entries(PAGES)) {
    md = md.split(`](${BLOB_ROOT}${file})`).join(`](${BASE}/${target})`);
    md = md.split(`](${file})`).join(`](${BASE}/${target})`);
  }
  // README.md#section links (from docs/*.md) -> the site page holding that section.
  md = md.split(README).join("#");
  md = md.replace(new RegExp(BLOB.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&") + "([\\w-]+)\\.md", "g"),
    (_, slug) => `${BASE}/${slug}/`);
  md = md.replace(/\]\(([\w-]+)\.md(#[\w-]+)?\)/g, (_, slug, hash = "") => `](${BASE}/${slug}/${hash})`);
  md = md.replace(/\]\(#([\w-]+)\)/g, (m, anchor) => {
    const target = ANCHORS[anchor];
    if (!target || target.split("/")[0] === page) return m;
    return `](${BASE}/${target})`;
  });
  return md;
}

const stripH1 = (md) => md.replace(/^# .*\n+/, "");
const stripH2 = (md, title) => md.replace(new RegExp(`^## ${title}\\n+`), "");
const front = (fields) =>
  "---\n" + Object.entries(fields).map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join("\n") + "\n---\n\n";

function write(slug, fields, body) {
  writeFileSync(join(out, `${slug}.md`), front(fields) + fixLinks(body, slug) + "\n");
}

rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });

// Home: the README's lead sentence becomes the hero tagline, next to the
// live forecast figure from docs/img.
// Served as a plain file: Starlight's hero <Image> would crop it to a square.
mkdirSync(join(here, "..", "public"), { recursive: true });
copyFileSync(join(repo, "docs", "img", "pronostico_puerto_montt.png"), join(here, "..", "public", "pronostico.png"));
let inicio = section("inicio", "uso");
const lead = inicio.match(/^\*\*(.+?)\*\*/s)[1].replace(/\s+/g, " ");
inicio = inicio.replace(/^\*\*.+?\*\*\s*/s, "");
writeFileSync(
  join(out, "index.md"),
  `---
title: urg-forecast
description: ${JSON.stringify(lead)}
template: splash
hero:
  tagline: ${JSON.stringify(lead)}
  image:
    html: '<img class="hero-figura" src="${BASE}/pronostico.png" width="940" height="420" alt="Pronóstico semanal a 26 semanas para el Hospital de Puerto Montt, con bandas P80 y P95">' 
  actions:
    - text: Ver la demo
      link: ${BASE}/demo/
      icon: right-arrow
    - text: Empezar
      link: ${BASE}/uso/
      variant: secondary
    - text: GitHub
      link: https://github.com/nicoveraz/urg-forecast-core
      icon: github
      variant: minimal
---

` + fixLinks(inicio, "index") + "\n",
);

write("uso", { title: "Uso", description: "Comandos, opciones y qué revisar antes de usar un pronóstico." },
  section("uso", "modelos"));
write("extender", { title: "Extender", description: "La API en Python y cómo agregar tus propios modelos." },
  stripH2(section("extender", "acerca"), "Extender"));
write("acerca", { title: "Acerca de", description: "Datos, estado del proyecto, cita y licencia." },
  section("acerca", "fin"));
write("modelos", { title: "Modelos", description: "Los modelos incluidos, cuándo conviene cada uno y cómo agregar el tuyo." },
  stripH1(read("docs/modelos.md")));
write("seleccion-de-modelos", { title: "Por qué estos modelos", description: "La comparación con datos DEIS en vivo detrás de los modelos por defecto." },
  stripH1(read("docs/seleccion-de-modelos.md")));
write("roadmap", { title: "Hoja de ruta", description: "Brechas conocidas y primeras contribuciones." },
  stripH1(read("docs/roadmap.md")));
write("cambios", { title: "Registro de cambios", description: "Cambios de cada versión." },
  stripH1(read("CHANGELOG.md")));

write("contribuir", { title: "Cómo contribuir", description: "Reportar problemas, proponer cambios y preparar el entorno de desarrollo." },
  stripH1(read("CONTRIBUTING.md")));
write("conducta", { title: "Código de conducta", description: "Cómo nos tratamos en la comunidad del proyecto." },
  stripH1(read("CODE_OF_CONDUCT.md")));
write("seguridad", { title: "Seguridad", description: "Versiones con soporte y cómo reportar una vulnerabilidad." },
  stripH1(read("SECURITY.md")));

console.log("sync: pages written to src/content/docs/");
