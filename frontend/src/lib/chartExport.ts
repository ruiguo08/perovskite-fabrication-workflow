/**
 * Chart export: download an inline chart SVG as SVG, PNG, or TIFF.
 *
 * PNG and TIFF are rasterized at `scale` times the SVG size and tagged with
 * the requested DPI (300 by default), which is the common journal figure
 * requirement. PNG receives a pHYs chunk; TIFF carries XResolution/
 * YResolution/ResolutionUnit tags. Both are produced entirely client-side.
 *
 * The chart's webfont is embedded into every export (data-URI @font-face
 * rules plus a root font-family), because an SVG rendered as an image or
 * opened in an external viewer has no access to the page's stylesheets.
 */

import { CHART_FONT_FAMILY, chartFontFaceCss } from "./chartFonts";

const XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>\n';
const SVG_MIME = "image/svg+xml";

export type ChartExportFormat = "svg" | "png" | "tiff";

export interface ChartExportOptions {
  filename: string;
  /** Raster scale factor: exported pixels = SVG size x scale. */
  scale?: number;
  /** DPI metadata written into PNG (pHYs) and TIFF (resolution tags). */
  dpi?: number;
}

function chartDimensions(svg: SVGSVGElement): { width: number; height: number } {
  const viewBox = svg.viewBox.baseVal;
  const width = viewBox.width || svg.width.baseVal.value || 600;
  const height = viewBox.height || svg.height.baseVal.value || 400;
  return { width: Math.round(width), height: Math.round(height) };
}

export function serializeChartSvg(
  svg: SVGSVGElement,
  width: number,
  height: number,
  fontCss: string,
): string {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height));
  clone.setAttribute("font-family", CHART_FONT_FAMILY);
  if (fontCss) {
    const style = document.createElementNS("http://www.w3.org/2000/svg", "style");
    style.textContent = fontCss;
    clone.insertBefore(style, clone.firstChild);
  }
  const source = new XMLSerializer().serializeToString(clone);
  return source.startsWith("<?xml") ? source : `${XML_DECLARATION}${source}`;
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

async function rasterize(
  svg: SVGSVGElement,
  scale: number,
  fontCss: string,
): Promise<{ canvas: HTMLCanvasElement; width: number; height: number }> {
  const { width, height } = chartDimensions(svg);
  const rasterWidth = Math.round(width * scale);
  const rasterHeight = Math.round(height * scale);
  const source = serializeChartSvg(svg, width, height, fontCss);
  const dataUrl = `data:${SVG_MIME};charset=utf-8,${encodeURIComponent(source)}`;
  const image = new Image();
  await new Promise<void>((resolve, reject) => {
    image.onload = () => resolve();
    image.onerror = () => reject(new Error("Unable to rasterize the chart SVG."));
    image.src = dataUrl;
  });
  const canvas = document.createElement("canvas");
  canvas.width = rasterWidth;
  canvas.height = rasterHeight;
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("Canvas 2D context is unavailable in this browser.");
  }
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, rasterWidth, rasterHeight);
  context.drawImage(image, 0, 0, rasterWidth, rasterHeight);
  return { canvas, width: rasterWidth, height: rasterHeight };
}

// ---------------------------------------------------------------------------
// PNG DPI metadata
// ---------------------------------------------------------------------------

const CRC32_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let value = 0; value < 256; value++) {
    let current = value;
    for (let bit = 0; bit < 8; bit++) {
      current = current & 1 ? 0xedb88320 ^ (current >>> 1) : current >>> 1;
    }
    table[value] = current >>> 0;
  }
  return table;
})();

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (let index = 0; index < bytes.length; index++) {
    crc = CRC32_TABLE[(crc ^ bytes[index]) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function pngChunk(type: string, data: Uint8Array): Uint8Array {
  const typeBytes = new TextEncoder().encode(type);
  const chunk = new Uint8Array(12 + data.length);
  const view = new DataView(chunk.buffer);
  view.setUint32(0, data.length);
  chunk.set(typeBytes, 4);
  chunk.set(data, 8);
  const crcInput = new Uint8Array(4 + data.length);
  crcInput.set(typeBytes, 0);
  crcInput.set(data, 4);
  view.setUint32(8 + data.length, crc32(crcInput));
  return chunk;
}

/**
 * Insert a pHYs chunk after IHDR so the PNG declares its physical pixel
 * density instead of the 72 dpi default. pixelsPerMeter = dpi / 0.0254.
 */
export function injectPngPhysicalDpi(bytes: Uint8Array, dpi: number): Uint8Array<ArrayBuffer> {
  const pixelsPerMeter = Math.round(dpi / 0.0254);
  const payload = new Uint8Array(9);
  const payloadView = new DataView(payload.buffer);
  payloadView.setUint32(0, pixelsPerMeter);
  payloadView.setUint32(4, pixelsPerMeter);
  payload[8] = 1; // unit: meter
  const chunk = pngChunk("pHYs", payload);
  // PNG signature (8) + IHDR length/type (8) + IHDR data (13) + IHDR CRC (4).
  const insertion = 33;
  const result = new Uint8Array(bytes.length + chunk.length);
  result.set(bytes.subarray(0, insertion), 0);
  result.set(chunk, insertion);
  result.set(bytes.subarray(insertion), insertion + chunk.length);
  return result;
}

// ---------------------------------------------------------------------------
// Baseline TIFF encoder (uncompressed 8-bit RGB, single strip)
// ---------------------------------------------------------------------------

export interface TiffEncodeInput {
  width: number;
  height: number;
  /** RGBA pixel data of length width * height * 4. */
  rgba: Uint8ClampedArray | Uint8Array;
  dpi: number;
}

/**
 * Encode RGBA pixels as a baseline TIFF 6.0 file: little-endian, uncompressed
 * RGB (8 bits per sample), one strip, resolution tagged in inches. The result
 * opens in ImageJ, ImageMagick, Photoshop, and Origin.
 */
export function encodeTiff({ width, height, rgba, dpi }: TiffEncodeInput): Uint8Array<ArrayBuffer> {
  const pixelBytes = width * height * 3;
  const headerSize = 8;
  const tagCount = 12;
  const ifdSize = 2 + tagCount * 12 + 4;
  const bitsOffset = headerSize + ifdSize;
  const xResolutionOffset = bitsOffset + 6;
  const yResolutionOffset = xResolutionOffset + 8;
  const pixelOffset = yResolutionOffset + 8;
  const buffer = new ArrayBuffer(pixelOffset + pixelBytes);
  const view = new DataView(buffer);
  const bytes = new Uint8Array(buffer);

  view.setUint8(0, 0x49); // "II" little endian
  view.setUint8(1, 0x49);
  view.setUint16(2, 42, true);
  view.setUint32(4, headerSize, true);

  let cursor = headerSize;
  view.setUint16(cursor, tagCount, true);
  cursor += 2;
  const writeTag = (tag: number, type: number, count: number, value: number) => {
    view.setUint16(cursor, tag, true);
    view.setUint16(cursor + 2, type, true);
    view.setUint32(cursor + 4, count, true);
    if (type === 3 && count === 1) {
      view.setUint16(cursor + 8, value, true);
    } else {
      view.setUint32(cursor + 8, value, true);
    }
    cursor += 12;
  };
  // Tags ascending by identifier; types: 3 = SHORT, 4 = LONG, 5 = RATIONAL.
  writeTag(256, 4, 1, width); // ImageWidth
  writeTag(257, 4, 1, height); // ImageLength
  writeTag(258, 3, 3, bitsOffset); // BitsPerSample -> external 8,8,8
  writeTag(259, 3, 1, 1); // Compression: none
  writeTag(262, 3, 1, 2); // PhotometricInterpretation: RGB
  writeTag(273, 4, 1, pixelOffset); // StripOffsets
  writeTag(277, 3, 1, 3); // SamplesPerPixel
  writeTag(278, 4, 1, height); // RowsPerStrip
  writeTag(279, 4, 1, pixelBytes); // StripByteCounts
  writeTag(282, 5, 1, xResolutionOffset); // XResolution
  writeTag(283, 5, 1, yResolutionOffset); // YResolution
  writeTag(296, 3, 1, 2); // ResolutionUnit: inch
  view.setUint32(cursor, 0, true); // no next IFD

  view.setUint16(bitsOffset, 8, true);
  view.setUint16(bitsOffset + 2, 8, true);
  view.setUint16(bitsOffset + 4, 8, true);
  view.setUint32(xResolutionOffset, Math.round(dpi), true);
  view.setUint32(xResolutionOffset + 4, 1, true);
  view.setUint32(yResolutionOffset, Math.round(dpi), true);
  view.setUint32(yResolutionOffset + 4, 1, true);

  let out = pixelOffset;
  const pixelCount = width * height;
  for (let index = 0; index < pixelCount; index++) {
    bytes[out++] = rgba[index * 4];
    bytes[out++] = rgba[index * 4 + 1];
    bytes[out++] = rgba[index * 4 + 2];
  }
  return bytes;
}

// ---------------------------------------------------------------------------

export async function exportChart(
  svg: SVGSVGElement,
  format: ChartExportFormat,
  options: ChartExportOptions,
): Promise<void> {
  const { filename, scale = 3, dpi = 300 } = options;
  const fontCss = await chartFontFaceCss();
  if (format === "svg") {
    const { width, height } = chartDimensions(svg);
    const source = serializeChartSvg(svg, width, height, fontCss);
    downloadBlob(new Blob([source], { type: `${SVG_MIME};charset=utf-8` }), `${filename}.svg`);
    return;
  }
  const { canvas, width, height } = await rasterize(svg, scale, fontCss);
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("Canvas 2D context is unavailable in this browser.");
  }
  if (format === "png") {
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
    if (!blob) {
      throw new Error("Unable to encode the chart as PNG.");
    }
    const raw = new Uint8Array(await blob.arrayBuffer());
    downloadBlob(new Blob([injectPngPhysicalDpi(raw, dpi)], { type: "image/png" }), `${filename}.png`);
    return;
  }
  const imageData = context.getImageData(0, 0, width, height);
  const tiff = encodeTiff({ width, height, rgba: imageData.data, dpi });
  downloadBlob(new Blob([tiff], { type: "image/tiff" }), `${filename}.tiff`);
}
