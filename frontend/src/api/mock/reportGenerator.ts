import { PDFDocument, StandardFonts, rgb, type PDFFont, type PDFPage } from 'pdf-lib';
import { sanitizeForFont, wrapText } from '../../lib/pdfText';

export interface ReportSection {
  heading: string;
  paragraphs?: string[];
  bullets?: string[];
}

export interface ReportContent {
  title: string;
  subtitle: string;
  sections: ReportSection[];
}

const PAGE = { width: 595.28, height: 841.89 }; // A4
const MARGIN = 56;
const INK = rgb(0.12, 0.14, 0.18);
const MUTED = rgb(0.42, 0.45, 0.5);
const ACCENT = rgb(0.16, 0.36, 0.78);

/** Maqueta un informe sencillo (A4, varias páginas) con pdf-lib. */
export async function renderReportPdf(content: ReportContent): Promise<Uint8Array> {
  const doc = await PDFDocument.create();
  doc.setTitle(content.title);
  doc.setProducer('LLM Report Studio (simulado)');
  doc.setCreationDate(new Date());

  const regular = await doc.embedFont(StandardFonts.Helvetica);
  const bold = await doc.embedFont(StandardFonts.HelveticaBold);
  const maxWidth = PAGE.width - MARGIN * 2;

  let page: PDFPage = doc.addPage([PAGE.width, PAGE.height]);
  let y = PAGE.height - MARGIN;

  const newPage = () => {
    page = doc.addPage([PAGE.width, PAGE.height]);
    y = PAGE.height - MARGIN;
  };

  const ensure = (needed: number) => {
    if (y - needed < MARGIN + 24) newPage();
  };

  const write = (text: string, font: PDFFont, size: number, color = INK, indent = 0, gap = 0.45) => {
    const lineHeight = size * 1.45;
    for (const line of wrapText(sanitizeForFont(text, font), font, size, maxWidth - indent)) {
      ensure(lineHeight);
      page.drawText(line, { x: MARGIN + indent, y: y - size, size, font, color });
      y -= lineHeight;
    }
    y -= size * gap;
  };

  // Encabezado
  page.drawRectangle({ x: 0, y: PAGE.height - 8, width: PAGE.width, height: 8, color: ACCENT });
  write('INFORME', bold, 9, ACCENT, 0, 0.6);
  write(content.title, bold, 22, INK, 0, 0.3);
  write(content.subtitle, regular, 10, MUTED, 0, 1.2);
  page.drawLine({
    start: { x: MARGIN, y },
    end: { x: PAGE.width - MARGIN, y },
    thickness: 0.6,
    color: rgb(0.85, 0.87, 0.9),
  });
  y -= 20;

  for (const section of content.sections) {
    ensure(60);
    write(section.heading, bold, 14, ACCENT, 0, 0.5);
    for (const p of section.paragraphs ?? []) write(p, regular, 11, INK, 0, 0.8);
    for (const b of section.bullets ?? []) {
      ensure(16);
      page.drawCircle({ x: MARGIN + 6, y: y - 7.5, size: 1.8, color: INK });
      write(b, regular, 11, INK, 16, 0.35);
    }
    y -= 10;
  }

  // Pie de página con numeración
  const pages = doc.getPages();
  pages.forEach((p, i) => {
    const label = `Página ${i + 1} de ${pages.length}`;
    const w = regular.widthOfTextAtSize(label, 8);
    p.drawText(label, { x: PAGE.width - MARGIN - w, y: MARGIN / 2, size: 8, font: regular, color: MUTED });
    p.drawText(sanitizeForFont(content.title, regular).slice(0, 80), {
      x: MARGIN,
      y: MARGIN / 2,
      size: 8,
      font: regular,
      color: MUTED,
    });
  });

  return doc.save();
}
