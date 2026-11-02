// @ts-check
import starlight from "@astrojs/starlight";
import { defineConfig } from "astro/config";

export default defineConfig({
  site: "https://nicoveraz.github.io",
  base: "/urg-forecast-core",
  // "API y recetas" was merged into the developer page.
  redirects: { "/extender": "/urg-forecast-core/desarrolladores/#extender" },
  integrations: [
    starlight({
      title: "urg-forecast",
      description:
        "Base abierta para pronosticar la demanda semanal de urgencias en Chile con datos públicos del DEIS MINSAL.",
      defaultLocale: "root",
      locales: { root: { label: "Español", lang: "es" } },
      social: [
        { icon: "github", label: "GitHub", href: "https://github.com/nicoveraz/urg-forecast-core" },
      ],
      customCss: ["./src/estilos.css"],
      favicon: "/favicon.svg",
      lastUpdated: false,
      pagination: true,
      sidebar: [
        { label: "Inicio", link: "/" },
        { label: "Demo", link: "/demo/", badge: { text: "nuevo", variant: "tip" } },
        { label: "Uso", slug: "uso" },
        {
          label: "Modelos",
          items: [
            { label: "Los modelos", slug: "modelos" },
            { label: "Regresores", slug: "regresores" },
            { label: "Por qué estos por defecto", slug: "seleccion-de-modelos" },
          ],
        },
        {
          label: "Extender",
          items: [
            { label: "Para desarrolladores", link: "/desarrolladores/" },
            { label: "Ejemplos", slug: "ejemplos" },
            { label: "Arquitectura", slug: "arquitectura" },
          ],
        },
        { label: "Referencias", slug: "referencias" },
        { label: "Hoja de ruta", slug: "roadmap" },
        {
          label: "Comunidad",
          items: [
            { label: "Cómo contribuir", slug: "contribuir" },
            { label: "Código de conducta", slug: "conducta" },
            { label: "Seguridad", slug: "seguridad" },
          ],
        },
        { label: "Cambios", slug: "cambios" },
        { label: "Acerca de", slug: "acerca" },
        {
          label: "English (README)",
          link: "https://github.com/nicoveraz/urg-forecast-core/blob/main/README.en.md",
          attrs: { target: "_blank" },
        },
      ],
    }),
  ],
});
