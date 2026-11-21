import { rgb, type PDFFont, type RGB } from 'pdf-lib';

/**
 * Las fuentes estándar de PDF (Helvetica, etc.) solo admiten WinAnsi.
 * Los acentos y la ñ sí entran; emojis u otros alfabetos se sustituyen.
 */
export function sanitizeForFont(text: string, font: PDFFont): string {
  let out = '';
  for (const ch of text.normalize('NFC')) {
    if (ch === '\n' || ch === '\t') {
      out += ch === '\t' ? '    ' : ch;
      continue;
    }
    try {
      font.encodeText(ch);
      out += ch;
    } catch {
      out += '?';
    }
  }
  return out;
}

/** Parte un texto en líneas que caben en maxWidth (respeta saltos de línea). */
export function wrapText(text: string, font: PDFFont, size: number, maxWidth: number): string[] {
  const lines: string[] = [];
  for (const paragraph of text.split('\n')) {
    const words = paragraph.split(/\s+/).filter(Boolean);
    if (words.length === 0) {
      lines.push('');
      continue;
    }
    let line = '';
    for (const word of words) {
      const candidate = line ? `${line} ${word}` : word;
      if (font.widthOfTextAtSize(candidate, size) <= maxWidth || !line) {
        line = candidate;
      } else {
        lines.push(line);
        line = word;
      }
    }
    lines.push(line);
  }
  return lines;
}

export function hexToRgb(hex: string): RGB {
  const clean = hex.replace('#', '');
  const full = clean.length === 3 ? clean.split('').map((c) => c + c).join('') : clean;
  const n = parseInt(full, 16);
  return rgb(((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255);
}
