// @ts-check
import starlight from "@astrojs/starlight";
import { defineConfig } from "astro/config";

export default defineConfig({
  site: "https://nicoveraz.github.io",
  base: "/urg-forecast-core",
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
        { label: "Uso", slug: "uso" },
        {
          label: "Modelos",
          items: [
            { label: "Los modelos", slug: "modelos" },
            { label: "Por qué estos por defecto", slug: "seleccion-de-modelos" },
          ],
        },
        { label: "Extender", slug: "extender" },
        { label: "Hoja de ruta", slug: "roadmap" },
        { label: "Cambios", slug: "cambios" },
        { label: "Acerca del proyecto", slug: "acerca" },
        {
          label: "English (README)",
          link: "https://github.com/nicoveraz/urg-forecast-core/blob/main/README.en.md",
          attrs: { target: "_blank" },
        },
      ],
    }),
  ],
});
