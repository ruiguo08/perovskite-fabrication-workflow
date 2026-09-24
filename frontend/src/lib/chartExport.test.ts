import { describe, expect, it } from "vitest";
import { encodeTiff, injectPngPhysicalDpi, serializeChartSvg } from "./chartExport";

/** Minimal well-formed PNG: signature + IHDR chunk (13-byte data) only. */
function minimalPng(): Uint8Array {
  const bytes = new Uint8Array(8 + 25);
  const signature = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
  bytes.set(signature, 0);
  const view = new DataView(bytes.buffer);
  view.setUint32(8, 13); // IHDR data length
  bytes.set([0x49, 0x48, 0x44, 0x52], 12); // "IHDR"
  // 13 bytes of IHDR data + 4 bytes of CRC follow; content is irrelevant here.
  return bytes;
}

describe("injectPngPhysicalDpi", () => {
  it("inserts a pHYs chunk directly after IHDR with the requested density", () => {
    const original = minimalPng();
    const result = injectPngPhysicalDpi(original, 300);

    expect(result.length).toBe(original.length + 21); // 12-byte chunk header/CRC + 9-byte payload
    expect(result.subarray(0, 33)).toEqual(original.subarray(0, 33));

    const view = new DataView(result.buffer);
    // Chunk inserted at offset 33: length (4) + "pHYs" (4) + payload (9) + CRC (4).
    const chunkType = new TextDecoder().decode(result.subarray(37, 41));
    expect(chunkType).toBe("pHYs");
    const pHYsData = 41;
    const pixelsPerMeter = Math.round(300 / 0.0254);
    expect(view.getUint32(pHYsData)).toBe(pixelsPerMeter);
    expect(view.getUint32(pHYsData + 4)).toBe(pixelsPerMeter);
    expect(result[pHYsData + 8]).toBe(1); // unit: meter
  });
});

describe("encodeTiff", () => {
  const width = 4;
  const height = 3;
  const rgba = new Uint8Array(width * height * 4);
  for (let index = 0; index < width * height; index++) {
    rgba[index * 4] = (index * 7) % 256;
    rgba[index * 4 + 1] = (index * 13) % 256;
    rgba[index * 4 + 2] = (index * 29) % 256;
    rgba[index * 4 + 3] = 255;
  }

  function readTags(bytes: Uint8Array) {
    const view = new DataView(bytes.buffer);
    const ifdOffset = view.getUint32(4, true);
    const tagCount = view.getUint16(ifdOffset, true);
    const tags = new Map<number, { type: number; count: number; value: number }>();
    for (let index = 0; index < tagCount; index++) {
      const entry = ifdOffset + 2 + index * 12;
      const tag = view.getUint16(entry, true);
      const type = view.getUint16(entry + 2, true);
      const count = view.getUint32(entry + 4, true);
      const value = type === 3 && count === 1 ? view.getUint16(entry + 8, true) : view.getUint32(entry + 8, true);
      tags.set(tag, { type, count, value });
    }
    return { tagCount, tags };
  }

  it("writes a little-endian baseline TIFF header", () => {
    const bytes = encodeTiff({ width, height, rgba, dpi: 300 });
    const view = new DataView(bytes.buffer);
    expect(view.getUint8(0)).toBe(0x49);
    expect(view.getUint8(1)).toBe(0x49);
    expect(view.getUint16(2, true)).toBe(42);
    expect(view.getUint32(4, true)).toBe(8);
  });

  it("declares an uncompressed RGB image with resolution metadata", () => {
    const bytes = encodeTiff({ width, height, rgba, dpi: 300 });
    const { tagCount, tags } = readTags(bytes);

    expect(tagCount).toBe(12);
    expect(tags.get(256)?.value).toBe(width); // ImageWidth
    expect(tags.get(257)?.value).toBe(height); // ImageLength
    expect(tags.get(258)?.count).toBe(3); // BitsPerSample (3 samples)
    expect(tags.get(259)?.value).toBe(1); // Compression: none
    expect(tags.get(262)?.value).toBe(2); // Photometric: RGB
    expect(tags.get(277)?.value).toBe(3); // SamplesPerPixel
    expect(tags.get(278)?.value).toBe(height); // RowsPerStrip
    expect(tags.get(279)?.value).toBe(width * height * 3); // StripByteCounts

    const view = new DataView(bytes.buffer);
    const xResOffset = tags.get(282)!.value;
    expect(view.getUint32(xResOffset, true)).toBe(300);
    expect(view.getUint32(xResOffset + 4, true)).toBe(1);
    const yResOffset = tags.get(283)!.value;
    expect(view.getUint32(yResOffset, true)).toBe(300);
    expect(tags.get(296)?.value).toBe(2); // ResolutionUnit: inch
  });

  it("converts RGBA pixels to packed RGB strips, dropping alpha", () => {
    const bytes = encodeTiff({ width, height, rgba, dpi: 300 });
    const { tags } = readTags(bytes);
    const pixelOffset = tags.get(273)!.value;

    expect(bytes.length).toBe(pixelOffset + width * height * 3);
    for (let index = 0; index < width * height; index++) {
      expect(bytes[pixelOffset + index * 3]).toBe(rgba[index * 4]);
      expect(bytes[pixelOffset + index * 3 + 1]).toBe(rgba[index * 4 + 1]);
      expect(bytes[pixelOffset + index * 3 + 2]).toBe(rgba[index * 4 + 2]);
    }
  });
});

describe("serializeChartSvg", () => {
  function makeSvg(): SVGSVGElement {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg") as SVGSVGElement;
    svg.setAttribute("viewBox", "0 0 100 50");
    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.textContent = "Voc";
    svg.appendChild(text);
    return svg;
  }

  it("injects the embedded-font style block and root font-family", () => {
    const source = serializeChartSvg(makeSvg(), 100, 50, "@font-face { src: url(x); }");

    expect(source).toContain('font-family="IBM Plex Sans, sans-serif"');
    expect(source).toContain("@font-face");
    // The style block must precede the chart content so the font rules load
    // before any text renders in viewers that process sequentially.
    expect(source.indexOf("<style")).toBeLessThan(source.indexOf("<text"));
  });

  it("omits the style block when no font CSS is available", () => {
    const source = serializeChartSvg(makeSvg(), 100, 50, "");

    expect(source).not.toContain("<style");
    expect(source).toContain('font-family="IBM Plex Sans, sans-serif"');
  });

  it("keeps the XML declaration off the SVG content itself", () => {
    const source = serializeChartSvg(makeSvg(), 100, 50, "");

    expect(source.startsWith("<?xml")).toBe(true);
  });
});
