const LEADING_SYSTEM_ALIASES = [
  "Nintendo Switch 2",
  "Nintendo Switch",
  "Nintendo 3DS",
  "Nintendo DS",
  "Nintendo Wii U",
  "Nintendo Wii",
  "Playstation 5",
  "PlayStation 5",
  "Playstation 4",
  "PlayStation 4",
  "Playstation 3",
  "PlayStation 3",
  "Playstation 2",
  "PlayStation 2",
  "Xbox Series X",
  "Xbox Series S",
  "Xbox One",
  "Xbox 360",
  "Gamecube",
  "Nintendo 64",
  "Super Nintendo",
  "PS Vita",
  "Switch 2",
  "Switch",
  "PS5",
  "PS4",
  "PS3",
  "PS2",
  "PSP",
  "NES",
  "DS",
  "PC",
  "Wii U",
  "Wii",
  "Xbox",
];

const NOISE_PHRASES = [
  "brand new factory sealed read",
  "brand new factory sealed",
  "complete with manual tested works",
  "brand new and sealed",
  "multiplayer music game",
  "brand new / sealed",
  "brand new/sealed",
  "brand new sealed",
  "complete video game",
  "free us shipping",
  "complete with manual",
  "action & adventure",
  "new and sealed",
  "new & sealed",
  "read description",
  "factory sealed",
  "fast shipping",
  "fast slipping",
  "still sealed",
  "sealed new",
  "new unopened",
  "1st printing",
  "first printing",
  "tested works",
  "video game",
  "electronic arts",
  "warner bros multiplayer",
  "free shipping",
  "please read",
  "new sealed",
  "ships fast",
  "dvd-rom",
  "dvd rom",
  "2k games",
  "firefly studios",
  "ea / dice",
  "ntsc-u/c",
  "ntsc u c",
  "action adventure",
  "us version",
  "us edition",
  "game esrb",
  "brand new",
  "unopened",
  "ea dice",
  "read a10",
  "slipping",
  "new:",
  "dvd",
  "esrb",
  "promo",
];

const NOISE_WORDS = new Set([
  "brand",
  "factory",
  "fast",
  "free",
  "read",
  "sealed",
  "shipping",
  "ships",
  "microsoft",
  "sony",
]);

const TRIM_NOISE_WORDS = NOISE_WORDS;

export function cleanMarketplaceTitleForSearch(title: string) {
  if (/\bwii\s+play\b/i.test(title)) return "Wii Play";

  const titleWithCleanParentheticals = removeParentheticalReleaseYears(title);
  const titleWithoutNoise = removeNoiseWords(
    trimNoiseWords(removeNoisePhrases(titleWithCleanParentheticals))
  );
  const { title: cleanedTitle, leadingSystems } =
    moveLeadingSystemTerms(titleWithoutNoise);
  const searchTerm = cleanupSearchText(
    [cleanedTitle, leadingSystems.join(" ")].join(" ")
  );

  return searchTerm;
}

function removeNoisePhrases(value: string) {
  return NOISE_PHRASES.reduce(
    (currentValue, phrase) =>
      currentValue.replace(
        new RegExp(`(^|\\b)${escapeRegExp(phrase)}(?=\\s|\\b|$)`, "gi"),
        " "
      ),
    value
  );
}

function removeParentheticalReleaseYears(value: string) {
  return value.replace(/\(([^)]*)\)/g, (_match, contents: string) => {
    const cleanedContents = cleanupSearchText(
      contents.replace(/\b(?:19|20)\d{2}\b/g, " ")
    );

    return cleanedContents ? ` ${cleanedContents} ` : " ";
  });
}

function trimNoiseWords(value: string) {
  const words = cleanupSearchText(value).split(" ");

  while (words.length > 0 && TRIM_NOISE_WORDS.has(words[0].toLowerCase())) {
    words.shift();
  }

  while (words.length > 0 && TRIM_NOISE_WORDS.has(words[words.length - 1].toLowerCase())) {
    words.pop();
  }

  return words.join(" ");
}

function removeNoiseWords(value: string) {
  return cleanupSearchText(value)
    .split(" ")
    .filter((word) => !NOISE_WORDS.has(word.toLowerCase()))
    .join(" ");
}

function moveLeadingSystemTerms(value: string) {
  const leadingSystems: string[] = [];
  let remainingTitle = cleanupSearchText(value);
  let matched = true;

  while (matched) {
    matched = false;

    for (const alias of LEADING_SYSTEM_ALIASES) {
      const pattern = new RegExp(`^${escapeRegExp(alias)}(?=\\s|[-:/|]|$)`, "i");
      const match = remainingTitle.match(pattern);

      if (!match) continue;

      leadingSystems.push(match[0]);
      remainingTitle = cleanupSearchText(
        remainingTitle.slice(match[0].length).replace(/^[-:/|\s]+/, "")
      );
      matched = true;
      break;
    }
  }

  return {
    title: remainingTitle,
    leadingSystems,
  };
}

function cleanupSearchText(value: string) {
  return value
    .replace(/[()[\]{}"]/g, " ")
    .replace(/[.,!?*]+/g, " ")
    .replace(/\s*[/|]\s*/g, " ")
    .replace(/\s*[-:\u2013\u2014\u2022]\s*/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
