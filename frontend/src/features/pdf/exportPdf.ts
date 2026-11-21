import {
  BlendMode,
  PDFDocument,
  PDFHexString,
  PDFString,
  StandardFonts,
  rgb,
  type PDFFont,
  type PDFPage,
} from 'pdf-lib';
import type { Annotation, Rect } from '../../types/annotations';
import { hexToRgb, sanitizeForFont, wrapText } from '../../lib/pdfText';

/** Proporciones de Helvetica/Arial para colocar la línea base igual que en pantalla. */
const ASCENT = 0.905;
const CONTENT_HEIGHT = 1.117;
const baselineOffset = (fontSize: number, lineHeight: number) =>
  fontSize * ((lineHeight - CONTENT_HEIGHT) / 2 + ASCENT);

/**
 * Genera un PDF nuevo con las anotaciones "aplanadas": resaltados, cuadros de
 * texto y reemplazos se dibujan en la página; las notas y comentarios se añaden
 * como anotaciones PDF nativas (se ven como notas adhesivas en Acrobat, etc.).
 */
export async function exportAnnotatedPdf(original: Uint8Array, annotations: Annotation[]): Promise<Uint8Array> {
  const doc = await PDFDocument.load(original);
  const font = await doc.embedFont(StandardFonts.Helvetica);
  const pages = doc.getPages();

  for (const ann of annotations) {
    const page = pages[ann.page - 1];
    if (!page) continue;
    const box = page.getCropBox();
    // Coordenadas de pantalla (origen arriba-izquierda) → PDF (origen abajo-izquierda).
    const toPdf = (r: Rect) => ({ x: box.x + r.x, y: box.y + box.height - r.y - r.height, width: r.width, height: r.height });

    switch (ann.type) {
      case 'highlight':
        for (const r of ann.rects) {
          page.drawRectangle({ ...toPdf(r), color: hexToRgb(ann.color), opacity: 0.4, blendMode: BlendMode.Multiply });
        }
        break;
      case 'underline':
      case 'strike':
        for (const r of ann.rects) {
          const p = toPdf(r);
          const y = ann.type === 'underline' ? p.y + p.height * 0.06 : p.y + p.height * 0.45;
          page.drawLine({
            start: { x: p.x, y },
            end: { x: p.x + p.width, y },
            thickness: Math.max(0.8, p.height * 0.07),
            color: hexToRgb(ann.color),
          });
        }
        break;
      case 'note':
        addStickyNote(doc, page, box.x + ann.x, box.y + box.height - ann.y, ann.text, ann.color);
        break;
      case 'text': {
        const lineHeight = 1.2;
        const lines = wrapText(sanitizeForFont(ann.text, font), font, ann.fontSize, ann.rect.width);
        drawLines(page, font, lines, box.x + ann.rect.x, box.y + box.height - ann.rect.y, ann.fontSize, lineHeight, ann.color);
        break;
      }
      case 'edit': {
        const lineHeight = 1.15;
        const lines = sanitizeForFont(ann.text, font).split('\n');
        const textWidth = Math.max(0, ...lines.map((l) => font.widthOfTextAtSize(l, ann.fontSize)));
        const cover = {
          ...ann.rect,
          width: Math.max(ann.rect.width, textWidth + 2),
          height: Math.max(ann.rect.height, lines.length * ann.fontSize * lineHeight),
        };
        page.drawRectangle({ ...toPdf(cover), color: rgb(1, 1, 1) });
        drawLines(page, font, lines, box.x + ann.rect.x, box.y + box.height - ann.rect.y, ann.fontSize, lineHeight, ann.color);
        break;
      }
    }

    if ((ann.type === 'highlight' || ann.type === 'underline' || ann.type === 'strike') && ann.comment.trim() && ann.rects[0]) {
      const r = ann.rects[0];
      addStickyNote(doc, page, box.x + r.x + r.width, box.y + box.height - r.y, ann.comment, ann.color);
    }
  }

  return doc.save();
}

function drawLines(
  page: PDFPage,
  font: PDFFont,
  lines: string[],
  x: number,
  top: number,
  fontSize: number,
  lineHeight: number,
  color: string,
) {
  const first = top - baselineOffset(fontSize, lineHeight);
  lines.forEach((line, i) => {
    if (!line) return;
    page.drawText(line, { x, y: first - i * fontSize * lineHeight, size: fontSize, font, color: hexToRgb(color) });
  });
}

function addStickyNote(doc: PDFDocument, page: PDFPage, x: number, top: number, text: string, color: string) {
  const c = hexToRgb(color);
  const annot = doc.context.obj({
    Type: 'Annot',
    Subtype: 'Text',
    Rect: [x, top - 18, x + 18, top],
    Contents: PDFHexString.fromText(text),
    T: PDFHexString.fromText('LLM Report Studio'),
    M: PDFString.fromDate(new Date()),
    Name: 'Comment',
    C: [c.red, c.green, c.blue],
    F: 4,
    Open: false,
  });
  page.node.addAnnot(doc.context.register(annot));
}
