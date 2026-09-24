/**
 * Embedded webfonts for chart export.
 *
 * An SVG rasterized through an <img> data URL cannot load the page's
 * stylesheets or external font files, so exported figures would fall back to
 * the browser's default serif. The chart fonts (IBM Plex Sans; the chart SVGs
 * use weight 400, plus 600 for one box-plot title) are therefore fetched and
 * inlined as data-URI @font-face rules, which SVG-as-image contexts do allow.
 * The same rules ship inside exported .svg files so external viewers render
 * the text with the intended face. Fetch failures degrade to empty CSS — the
 * export still succeeds with fallback fonts.
 */

import sansRegularUrl from "../assets/fonts/IBMPlexSans-Regular.woff2";
import sansSemiBoldUrl from "../assets/fonts/IBMPlexSans-SemiBold.woff2";

const FONT_FAMILY = "IBM Plex Sans";

interface EmbeddedFont {
  url: string;
  weight: number;
}

const EMBEDDED_FONTS: EmbeddedFont[] = [
  { url: sansRegularUrl, weight: 400 },
  { url: sansSemiBoldUrl, weight: 600 },
];

let cachedCss: Promise<string> | null = null;

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  // btoa() rejects huge argument spreads only via the call stack, so encode
  // in chunks well below the argument-count limit.
  const chunkSize = 0x8000;
  for (let start = 0; start < bytes.length; start += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(start, start + chunkSize));
  }
  return btoa(binary);
}

async function fontFaceRules(): Promise<string> {
  const rules = await Promise.all(
    EMBEDDED_FONTS.map(async (font) => {
      try {
        const response = await fetch(font.url);
        if (!response.ok) {
          return null;
        }
        const base64 = arrayBufferToBase64(await response.arrayBuffer());
        return (
          `@font-face { font-family: "${FONT_FAMILY}"; font-weight: ${font.weight}; ` +
          `font-style: normal; src: url(data:font/woff2;base64,${base64}) format("woff2"); }`
        );
      } catch {
        return null;
      }
    }),
  );
  return rules.filter((rule): rule is string => rule !== null).join("\n");
}

/**
 * @font-face CSS embedding the chart fonts, cached after the first call.
 * Resolves to "" when the font files cannot be fetched (offline, blocked
 * asset routes), which keeps exports working with fallback fonts.
 */
export function chartFontFaceCss(): Promise<string> {
  if (!cachedCss) {
    cachedCss = fontFaceRules();
  }
  return cachedCss;
}

/** font-family for chart SVG roots: embedded face first, generic fallback. */
export const CHART_FONT_FAMILY = `${FONT_FAMILY}, sans-serif`;

export function resetChartFontCssForTests(): void {
  cachedCss = null;
}
