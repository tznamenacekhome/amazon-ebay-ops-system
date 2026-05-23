import { cleanMarketplaceTitleForSearch } from "./titleCleaning";

const SYSTEM_ALIASES: Record<string, string[]> = {
  "Switch 2": ["nintendo switch 2", "switch 2"],
  Switch: ["nintendo switch", "switch"],
  "3DS": ["nintendo 3ds", "3ds"],
  DS: ["nintendo ds", "ds"],
  "Wii U": ["nintendo wii u", "wii u"],
  Wii: ["nintendo wii", "wii"],
  Gamecube: ["gamecube", "game cube", "nintendo gamecube"],
  "Nintendo 64": ["nintendo 64", "n64"],
  "Super Nintendo": ["super nintendo", "snes"],
  NES: ["nes", "nintendo entertainment system"],
  "PS 5": ["playstation 5", "ps5", "ps 5"],
  "PS 4": ["playstation 4", "ps4", "ps 4"],
  "PS 3": ["playstation 3", "ps3", "ps 3"],
  "PS 2": ["playstation 2", "ps2", "ps 2"],
  PS: ["playstation", "ps1", "psx"],
  PSP: ["psp", "playstation portable"],
  "PS Vita": ["playstation vita", "ps vita", "vita"],
  "Xbox Series X": ["xbox series x", "series x"],
  "Xbox Series S": ["xbox series s", "series s"],
  "Xbox One": ["xbox one", "xbone"],
  "Xbox 360": ["xbox 360", "360"],
  Xbox: ["original xbox", "xbox"],
  PC: ["pc", "windows pc", "windows", "mac"],
};

const GENERIC_TITLE_WORDS = new Set([
  "brand",
  "sealed",
  "factory",
  "nib",
  "complete",
  "cib",
  "disc",
  "disk",
  "cartridge",
  "cart",
  "case",
  "manual",
  "game",
  "video",
  "edition",
  "standard",
]);

export function normalizeMatchTitle(title?: string | null) {
  if (!title) return "";

  const cleanedTitle = cleanMarketplaceTitleForSearch(title).toLowerCase();
  const withoutBrackets = cleanedTitle
    .replace(/\([^)]*\)/g, " ")
    .replace(/\[[^\]]*\]/g, " ");
  const withoutSystems = removeSystemTerms(withoutBrackets);
  const words = withoutSystems
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .split(/\s+/)
    .filter((word) => word && !GENERIC_TITLE_WORDS.has(word));

  return normalizeSpaces(words.join(" "));
}

export function compactMatchTitle(title?: string | null) {
  return (title || "").replace(/[^a-z0-9]+/gi, "").toLowerCase();
}

export function normalizeSystem(value?: string | null) {
  if (!value) return null;

  const text = normalizeAlias(value);

  for (const [canonical, aliases] of Object.entries(SYSTEM_ALIASES)) {
    if (aliases.some((alias) => text === normalizeAlias(alias))) {
      return canonical;
    }
  }

  for (const [canonical, aliases] of Object.entries(SYSTEM_ALIASES)) {
    if (
      aliases.some((alias) =>
        new RegExp(`\\b${escapeRegExp(normalizeAlias(alias))}\\b`).test(text)
      )
    ) {
      return canonical;
    }
  }

  return null;
}

function removeSystemTerms(value: string) {
  return Object.values(SYSTEM_ALIASES)
    .flat()
    .sort((left, right) => right.length - left.length)
    .reduce(
      (text, alias) =>
        text.replace(
          new RegExp(`(?<![a-z0-9])${escapeRegExp(alias.toLowerCase())}(?![a-z0-9])`, "g"),
          " "
        ),
      value
    );
}

function normalizeAlias(value: string) {
  return normalizeSpaces(value.toLowerCase().replace(/[^a-z0-9]+/g, " "));
}

function normalizeSpaces(value: string) {
  return value.replace(/\s+/g, " ").trim();
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
