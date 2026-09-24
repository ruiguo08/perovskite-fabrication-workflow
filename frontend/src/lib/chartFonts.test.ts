import { afterEach, describe, expect, it, vi } from "vitest";
import {
  CHART_FONT_FAMILY,
  chartFontFaceCss,
  resetChartFontCssForTests,
} from "./chartFonts";

/** Fake woff2 bytes: content is irrelevant, only size and fetchability matter. */
const FAKE_WOFF2 = new Uint8Array(16).fill(0x77);

function fakeFontFetch(): ReturnType<typeof vi.fn> {
  return vi.fn(async (url: string) => {
    if (!url.endsWith(".woff2")) {
      throw new Error(`unexpected url: ${url}`);
    }
    return new Response(FAKE_WOFF2, { status: 200 });
  });
}

describe("chartFontFaceCss", () => {
  afterEach(() => {
    resetChartFontCssForTests();
    vi.unstubAllGlobals();
  });

  it("embeds one data-URI @font-face rule per font with the right weights", async () => {
    vi.stubGlobal("fetch", fakeFontFetch());

    const css = await chartFontFaceCss();

    const rules = css.split("\n");
    expect(rules).toHaveLength(2);
    expect(rules[0]).toContain('font-family: "IBM Plex Sans"');
    expect(rules[0]).toContain("font-weight: 400");
    expect(rules[1]).toContain("font-weight: 600");
    for (const rule of rules) {
      expect(rule).toContain('url(data:font/woff2;base64,');
      expect(rule).toContain('format("woff2")');
    }
  });

  it("resolves to empty CSS when the font files cannot be fetched", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("offline");
      }),
    );

    const css = await chartFontFaceCss();

    expect(css).toBe("");
  });

  it("resolves to empty CSS when a font request returns an error status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("not found", { status: 404 })),
    );

    const css = await chartFontFaceCss();

    expect(css).toBe("");
  });

  it("serves repeat calls from the cache without re-fetching", async () => {
    const fetchMock = fakeFontFetch();
    vi.stubGlobal("fetch", fetchMock);

    await chartFontFaceCss();
    const second = await chartFontFaceCss();

    expect(second).not.toBe("");
    expect(fetchMock).toHaveBeenCalledTimes(2); // once per embedded font
  });

  it("exposes a font-family stack with a generic fallback", () => {
    expect(CHART_FONT_FAMILY).toBe("IBM Plex Sans, sans-serif");
  });
});
