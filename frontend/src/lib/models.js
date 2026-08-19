export const QUANT_ORDER = ["q4", "q5", "q8"];
export const QUANT_PREFERENCE = ["q8", "q5", "q4"];

export function splitModelTag(name = "") {
  const index = name.lastIndexOf(":");
  if (index < 0) return { base: name, quant: "", full: name };
  return {
    base: name.slice(0, index),
    quant: name.slice(index + 1).toLowerCase(),
    full: name,
  };
}

export function buildCatalog(names) {
  return names.reduce((catalog, name) => {
    const { base, quant, full } = splitModelTag(name);
    if (!catalog[base]) {
      catalog[base] = { base, quants: {}, fallback: full };
    }
    if (quant) catalog[base].quants[quant] = full;
    else catalog[base].fallback = full;
    return catalog;
  }, {});
}

export function chooseQuant(entry, preferred = "") {
  const available = entry?.quants || {};
  if (preferred && available[preferred]) return preferred;
  return QUANT_PREFERENCE.find((quant) => available[quant]) || "";
}

export function modelTag(catalog, base, quant) {
  const entry = catalog[base];
  if (!entry) return base;
  const selected = chooseQuant(entry, quant);
  return entry.quants[selected] || entry.fallback || base;
}

export function displayModelName(base = "") {
  const name = base.toLowerCase();
  if (name.includes("ministral3-3b-instruct-translator-cp220")) return "Ministral 3 3B Instruct";
  if (name.includes("ministral3-3b-instruct-summarizer")) return "Ministral 3 3B Instruct";
  if (name.includes("translategemma-4b-it")) return "TranslateGemma 4B IT";
  if (name.includes("translator-legacy-v3-cp140")) return "LLaMA 3.2 Instruct";
  if (name.includes("translator-baseline150")) return "LLaMA 3.2 Instruct Base150";
  if (name.includes("summarizer-complete-clinical-v5")) return "LLaMA 3.2 Instruct";

  return base
    .replace(/^llama-3\.2-3b-instruct-/, "llama3.2-3b-")
    .replace("-summarizer-clinical-v4", "-sum-clinical-v4")
    .replace("-translator", "-trans")
    .replace("-summarizer", "-sum");
}

export function groupModels(bases, kind) {
  const isCurrent = (base) => {
    const name = base.toLowerCase();
    if (kind === "translator") {
      return (
        name.includes("translator-legacy-v3-cp140") ||
        name.includes("ministral3-3b-instruct-translator-cp220") ||
        name.includes("translategemma-4b-it")
      );
    }
    return (
      name.includes("summarizer-complete-clinical-v5") ||
      name.includes("translategemma-4b-it") ||
      name.includes("ministral3-3b-instruct-summarizer")
    );
  };

  return {
    current: bases.filter(isCurrent),
    legacy: bases.filter((base) => !isCurrent(base)),
  };
}

export function defaultSelection(defaultName, catalog) {
  const parsed = splitModelTag(defaultName);
  const bases = Object.keys(catalog);
  const base = catalog[parsed.base]
    ? parsed.base
    : catalog[defaultName]
      ? defaultName
      : bases[0] || "";
  const quant = chooseQuant(catalog[base], parsed.quant || "q8");
  return { base, quant };
}
