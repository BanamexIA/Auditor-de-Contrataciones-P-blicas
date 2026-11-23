import type { Rect } from '../../types/annotations';

export interface PageSelection {
  page: number;
  rects: Rect[];
}

/**
 * Convierte la selección de texto del navegador en rectángulos por página,
 * en coordenadas PDF (escala 1). Une los fragmentos de una misma línea.
 */
export function selectionToPageRects(container: HTMLElement, scale: number): { pages: PageSelection[]; text: string } | null {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) return null;
  const range = sel.getRangeAt(0);
  if (!container.contains(range.commonAncestorContainer)) return null;

  const pageEls = Array.from(container.querySelectorAll<HTMLElement>('.pdf-page'));
  const boxes = pageEls.map((el) => ({ page: Number(el.dataset.page), box: el.getBoundingClientRect() }));
  const byPage = new Map<number, Rect[]>();

  for (const r of Array.from(range.getClientRects())) {
    if (r.width < 1 || r.height < 1) continue;
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    const hit = boxes.find(({ box }) => cx >= box.left && cx <= box.right && cy >= box.top && cy <= box.bottom);
    if (!hit) continue;
    // Descarta rectángulos enormes (p. ej. contenedores completos seleccionados).
    if (r.height > hit.box.height * 0.2) continue;
    const rect: Rect = {
      x: (r.left - hit.box.left) / scale,
      y: (r.top - hit.box.top) / scale,
      width: r.width / scale,
      height: r.height / scale,
    };
    const list = byPage.get(hit.page) ?? [];
    list.push(rect);
    byPage.set(hit.page, list);
  }

  const pages = Array.from(byPage, ([page, rects]) => ({ page, rects: mergeLineRects(rects) }));
  if (pages.length === 0) return null;
  return { pages, text: sel.toString().replace(/\s+/g, ' ').trim() };
}

function mergeLineRects(rects: Rect[]): Rect[] {
  const sorted = [...rects].sort((a, b) => a.y - b.y || a.x - b.x);
  const out: Rect[] = [];
  for (const r of sorted) {
    const same = out.find((o) => {
      const overlap = Math.min(o.y + o.height, r.y + r.height) - Math.max(o.y, r.y);
      const sameLine = overlap > Math.min(o.height, r.height) * 0.5;
      const touching = r.x <= o.x + o.width + 3 && r.x + r.width >= o.x - 3;
      return sameLine && touching;
    });
    if (same) {
      const x = Math.min(same.x, r.x);
      const y = Math.min(same.y, r.y);
      same.width = Math.max(same.x + same.width, r.x + r.width) - x;
      same.height = Math.max(same.y + same.height, r.y + r.height) - y;
      same.x = x;
      same.y = y;
    } else {
      out.push({ ...r });
    }
  }
  return out;
}
