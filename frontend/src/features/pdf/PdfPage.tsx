import { memo, useEffect, useRef, useState, type CSSProperties, type MouseEvent } from 'react';
import { pdfjs, type PDFDocumentProxy, type PageSize } from './pdfjs';
import type { Annotation } from '../../types/annotations';
import { AnnotationLayer } from './AnnotationLayer';
import { useEditor } from './editorContext';

interface PdfPageProps {
  pdf: PDFDocumentProxy;
  pageNumber: number;
  size: PageSize;
  annotations: Annotation[];
}

function PdfPageImpl({ pdf, pageNumber, size, annotations }: PdfPageProps) {
  const { scale, tool, createEdit } = useEditor();
  const wrapperRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [rendered, setRendered] = useState(false);

  // Solo se renderizan las páginas cercanas a la vista.
  useEffect(() => {
    const el = wrapperRef.current;
    if (!el) return;
    const io = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { rootMargin: '800px 0px' });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    let renderTask: ReturnType<Awaited<ReturnType<PDFDocumentProxy['getPage']>>['render']> | null = null;
    let textLayer: InstanceType<typeof pdfjs.TextLayer> | null = null;

    (async () => {
      const page = await pdf.getPage(pageNumber);
      if (cancelled) return;
      const viewport = page.getViewport({ scale });
      const canvas = canvasRef.current!;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.floor(viewport.width * dpr);
      canvas.height = Math.floor(viewport.height * dpr);
      const ctx = canvas.getContext('2d')!;
      renderTask = page.render({
        canvasContext: ctx,
        viewport,
        transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined,
      });
      try {
        await renderTask.promise;
      } catch {
        return; // render cancelado por cambio de zoom
      }
      if (cancelled) return;

      const container = textRef.current!;
      container.replaceChildren();
      textLayer = new pdfjs.TextLayer({ textContentSource: page.streamTextContent(), container, viewport });
      await textLayer.render().catch(() => undefined);
      if (!cancelled) setRendered(true);
    })();

    return () => {
      cancelled = true;
      renderTask?.cancel();
      textLayer?.cancel();
    };
  }, [pdf, pageNumber, scale, visible]);

  // Herramienta "editar texto": clic sobre un fragmento del PDF para reemplazarlo.
  const onTextClick = (e: MouseEvent<HTMLDivElement>) => {
    if (tool !== 'edit') return;
    const span = (e.target as HTMLElement).closest('span');
    if (!span || !textRef.current?.contains(span) || !span.textContent?.trim()) return;
    const pageBox = wrapperRef.current!.getBoundingClientRect();
    const r = span.getBoundingClientRect();
    // pdf.js escribe el tamaño real como calc(var(--scale-factor)*Npx).
    const match = /([\d.]+)px/.exec(span.style.fontSize);
    const fontSize = match ? parseFloat(match[1]) : (r.height / scale) * 0.85;
    createEdit(
      pageNumber,
      {
        x: (r.left - pageBox.left) / scale,
        y: (r.top - pageBox.top) / scale,
        width: r.width / scale,
        height: r.height / scale,
      },
      span.textContent,
      fontSize,
    );
  };

  // Igual que el visor de pdf.js: mejora la selección al arrastrar fuera del texto.
  const onMouseDown = () => textRef.current?.classList.add('selecting');
  useEffect(() => {
    const up = () => textRef.current?.classList.remove('selecting');
    document.addEventListener('mouseup', up);
    return () => document.removeEventListener('mouseup', up);
  }, []);

  const style = {
    width: size.width * scale,
    height: size.height * scale,
    '--scale-factor': scale,
  } as CSSProperties;

  return (
    <div className="pdf-page" ref={wrapperRef} style={style} data-page={pageNumber}>
      <canvas ref={canvasRef} style={{ width: size.width * scale, height: size.height * scale }} />
      {!rendered && <div className="page-loading">Cargando página {pageNumber}…</div>}
      <div className="textLayer" ref={textRef} onClick={onTextClick} onMouseDown={onMouseDown} />
      <AnnotationLayer page={pageNumber} annotations={annotations} />
      <span className="page-number">{pageNumber}</span>
    </div>
  );
}

export const PdfPage = memo(PdfPageImpl);
