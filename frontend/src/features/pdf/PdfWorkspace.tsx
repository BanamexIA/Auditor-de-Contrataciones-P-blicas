import { useCallback, useEffect, useMemo, useReducer, useRef, useState, type ChangeEvent } from 'react';
import { documentsApi } from '../../api';
import { config } from '../../config';
import { Icon } from '../../components/Icon';
import type { Annotation, MarkupKind, Tool } from '../../types/annotations';
import type { DocumentInfo } from '../../types/documents';
import { newId, nowIso } from '../../lib/id';
import { annotationsReducer, initialAnnotationsState } from './annotationsReducer';
import { AnnotationsSidebar } from './AnnotationsSidebar';
import { EditorContext, type EditorContextValue } from './editorContext';
import { exportAnnotatedPdf } from './exportPdf';
import { PdfPage } from './PdfPage';
import { INK_COLORS, MARK_COLORS, PdfToolbar, TOOL_KEYS } from './PdfToolbar';
import { loadPdf, type PDFDocumentProxy, type PageSize } from './pdfjs';
import { selectionToPageRects } from './selection';

type SaveStatus = 'idle' | 'pending' | 'saving' | 'saved' | 'error';

interface PdfWorkspaceProps {
  documentId: string | null;
  onDocumentInfo: (info: DocumentInfo | null) => void;
  onOpenDocument: (documentId: string) => void;
}

const MARKUP: MarkupKind[] = ['highlight', 'underline', 'strike'];
const clampScale = (s: number) => Math.min(4, Math.max(0.4, s));

function isTyping(target: EventTarget | null) {
  const el = target as HTMLElement | null;
  return !!el && (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT' || el.isContentEditable);
}

export function PdfWorkspace({ documentId, onDocumentInfo, onOpenDocument }: PdfWorkspaceProps) {
  const [info, setInfo] = useState<DocumentInfo | null>(null);
  const [original, setOriginal] = useState<Uint8Array | null>(null);
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [sizes, setSizes] = useState<PageSize[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [state, dispatch] = useReducer(annotationsReducer, initialAnnotationsState);
  const [tool, setTool] = useState<Tool>('select');
  const [markColor, setMarkColor] = useState(MARK_COLORS[0]);
  const [inkColor, setInkColor] = useState(INK_COLORS[0]);
  const [scale, setScale] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [currentPage, setCurrentPage] = useState(1);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const [busy, setBusy] = useState<null | 'download' | 'upload' | 'open'>(null);
  const [toast, setToast] = useState<{ text: string; kind: 'ok' | 'error' } | null>(null);
  const [selectionMenu, setSelectionMenu] = useState<{ x: number; y: number } | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const latest = useRef({ documentId, items: state.items, revision: state.revision, savedRevision: 0 });
  latest.current.items = state.items;
  latest.current.revision = state.revision;

  const notify = useCallback((text: string, kind: 'ok' | 'error' = 'ok') => {
    setToast({ text, kind });
    window.setTimeout(() => setToast((t) => (t?.text === text ? null : t)), 3500);
  }, []);

  /* ---------- carga del documento ---------- */

  const fitWidth = useCallback(
    (pageSizes = sizes) => {
      const el = scrollRef.current;
      if (!el || pageSizes.length === 0) return;
      const maxWidth = Math.max(...pageSizes.map((s) => s.width));
      // 48 px de márgenes + reserva para la barra de desplazamiento vertical.
      setScale(clampScale((el.clientWidth - 48 - 18) / maxWidth));
    },
    [sizes],
  );

  useEffect(() => {
    if (!documentId) {
      setInfo(null);
      setPdf(null);
      setSizes([]);
      onDocumentInfo(null);
      return;
    }
    let cancelled = false;
    let loaded: PDFDocumentProxy | null = null;
    setLoading(true);
    setError(null);
    setSelectedId(null);
    setSaveStatus('idle');
    latest.current = { documentId, items: [], revision: 0, savedRevision: 0 };

    (async () => {
      try {
        const [docInfo, bytes, annotations] = await Promise.all([
          documentsApi.getDocument(documentId),
          documentsApi.downloadPdf(documentId),
          documentsApi.getAnnotations(documentId),
        ]);
        const result = await loadPdf(bytes);
        loaded = result.pdf;
        if (cancelled) return;
        setInfo(docInfo);
        onDocumentInfo(docInfo);
        setOriginal(bytes);
        setPdf(result.pdf);
        setSizes(result.sizes);
        dispatch({ type: 'load', items: annotations });
        setCurrentPage(1);
        scrollRef.current?.scrollTo({ top: 0 });
        requestAnimationFrame(() => fitWidth(result.sizes));
      } catch (err) {
        if (!cancelled) setError((err as Error).message || 'No se pudo abrir el documento.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      void loaded?.destroy();
      // Guarda lo pendiente del documento anterior antes de cambiar.
      const prev = latest.current;
      if (prev.documentId === documentId && prev.revision !== prev.savedRevision) {
        void documentsApi.saveAnnotations(documentId, prev.items).catch(() => undefined);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentId]);

  /* ---------- guardado automático de anotaciones ---------- */

  useEffect(() => {
    if (!documentId || state.revision === 0 || state.revision === latest.current.savedRevision) return;
    setSaveStatus('pending');
    const revision = state.revision;
    const items = state.items;
    const t = window.setTimeout(async () => {
      setSaveStatus('saving');
      try {
        await documentsApi.saveAnnotations(documentId, items);
        if (latest.current.documentId !== documentId) return;
        latest.current.savedRevision = revision;
        setSaveStatus(latest.current.revision === revision ? 'saved' : 'pending');
      } catch {
        setSaveStatus('error');
      }
    }, config.autosaveDelayMs);
    return () => window.clearTimeout(t);
  }, [documentId, state.revision, state.items]);

  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (latest.current.revision !== latest.current.savedRevision) e.preventDefault();
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, []);

  /* ---------- creación de anotaciones ---------- */

  const addMarkup = useCallback(
    (kind: MarkupKind) => {
      const container = scrollRef.current;
      if (!container) return false;
      const result = selectionToPageRects(container, scale);
      if (!result) return false;
      const now = nowIso();
      let lastId = '';
      for (const { page, rects } of result.pages) {
        lastId = newId('ann');
        dispatch({
          type: 'add',
          item: { id: lastId, type: kind, page, rects, color: markColor, text: result.text, comment: '', createdAt: now, updatedAt: now },
        });
      }
      window.getSelection()?.removeAllRanges();
      setSelectedId(lastId);
      return true;
    },
    [scale, markColor],
  );

  const onPagesMouseUp = () => {
    // Deja que el navegador termine de actualizar la selección.
    requestAnimationFrame(() => {
      if ((MARKUP as Tool[]).includes(tool)) {
        addMarkup(tool as MarkupKind);
        return;
      }
      if (tool !== 'select') return;
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed || !scrollRef.current?.contains(sel.anchorNode)) {
        setSelectionMenu(null);
        return;
      }
      const r = sel.getRangeAt(0).getBoundingClientRect();
      const box = scrollRef.current.getBoundingClientRect();
      setSelectionMenu({ x: r.left + r.width / 2 - box.left, y: r.top - box.top + scrollRef.current.scrollTop });
    });
  };

  const editor = useMemo<EditorContextValue>(
    () => ({
      tool,
      color: markColor,
      scale,
      selectedId,
      focusId,
      select: setSelectedId,
      clearFocus: () => setFocusId(null),
      dispatch,
      createAt: (page, x, y, kind) => {
        const now = nowIso();
        const id = newId('ann');
        const item: Annotation =
          kind === 'note'
            ? { id, type: 'note', page, x: x - 9, y: y - 9, text: '', color: markColor, createdAt: now, updatedAt: now }
            : {
                id,
                type: 'text',
                page,
                rect: { x, y: y - 8, width: 200, height: 20 },
                text: '',
                fontSize: 12,
                color: inkColor,
                createdAt: now,
                updatedAt: now,
              };
        dispatch({ type: 'add', item });
        setSelectedId(id);
        setFocusId(id);
        // Tras colocar una nota o un cuadro, se vuelve a la selección para no crear otro sin querer.
        setTool('select');
      },
      createEdit: (page, rect, text, fontSize) => {
        const now = nowIso();
        const id = newId('ann');
        dispatch({
          type: 'add',
          item: { id, type: 'edit', page, rect, originalText: text, text, fontSize, color: inkColor, createdAt: now, updatedAt: now },
        });
        setSelectedId(id);
        setFocusId(id);
      },
    }),
    [tool, markColor, inkColor, scale, selectedId, focusId],
  );

  /* ---------- atajos de teclado ---------- */

  useEffect(() => {
    if (!pdf) return;
    const onKey = (e: KeyboardEvent) => {
      if (isTyping(e.target)) return;
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === 'z') {
        e.preventDefault();
        dispatch({ type: e.shiftKey ? 'redo' : 'undo' });
      } else if (mod && e.key.toLowerCase() === 'y') {
        e.preventDefault();
        dispatch({ type: 'redo' });
      } else if ((e.key === 'Delete' || e.key === 'Backspace') && selectedId) {
        e.preventDefault();
        dispatch({ type: 'remove', id: selectedId });
        setSelectedId(null);
      } else if (e.key === 'Escape') {
        setTool('select');
        setSelectedId(null);
        setSelectionMenu(null);
      } else if (!mod && !e.altKey && TOOL_KEYS[e.key.toLowerCase()]) {
        setTool(TOOL_KEYS[e.key.toLowerCase()]);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [pdf, selectedId]);

  /* ---------- navegación ---------- */

  const onScroll = () => {
    setSelectionMenu(null);
    const el = scrollRef.current;
    if (!el) return;
    const middle = el.getBoundingClientRect().top + el.clientHeight / 3;
    const pages = el.querySelectorAll<HTMLElement>('.pdf-page');
    for (const p of Array.from(pages)) {
      const r = p.getBoundingClientRect();
      if (r.bottom >= middle) {
        setCurrentPage(Number(p.dataset.page));
        break;
      }
    }
  };

  const goToPage = (page: number, y = 0) => {
    const el = scrollRef.current?.querySelector<HTMLElement>(`.pdf-page[data-page="${page}"]`);
    if (!el || !scrollRef.current) return;
    scrollRef.current.scrollTo({ top: el.offsetTop + y * scale - 80, behavior: 'smooth' });
  };

  const focusAnnotation = (a: Annotation) => {
    setSelectedId(a.id);
    const y = a.type === 'note' ? a.y : a.type === 'text' || a.type === 'edit' ? a.rect.y : (a.rects[0]?.y ?? 0);
    goToPage(a.page, y);
  };

  /* ---------- exportar / subir / abrir ---------- */

  const exportBlob = async () => {
    const bytes = await exportAnnotatedPdf(original!, state.items);
    return new Blob([bytes], { type: 'application/pdf' });
  };

  const annotatedName = () => (info?.fileName ?? 'documento.pdf').replace(/\.pdf$/i, '') + '-anotado.pdf';

  const download = async () => {
    if (!original) return;
    setBusy('download');
    try {
      const url = URL.createObjectURL(await exportBlob());
      const a = document.createElement('a');
      a.href = url;
      a.download = annotatedName();
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch (err) {
      notify(`No se pudo exportar: ${(err as Error).message}`, 'error');
    } finally {
      setBusy(null);
    }
  };

  const upload = async () => {
    if (!original || !documentId) return;
    setBusy('upload');
    try {
      const updated = await documentsApi.uploadVersion(documentId, await exportBlob(), annotatedName());
      setInfo(updated);
      onDocumentInfo(updated);
      notify(`Versión ${updated.version} subida al almacenamiento.`);
    } catch (err) {
      notify(`No se pudo subir: ${(err as Error).message}`, 'error');
    } finally {
      setBusy(null);
    }
  };

  const openLocal = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setBusy('open');
    try {
      const doc = await documentsApi.createDocument(file, file.name.replace(/\.pdf$/i, ''), file.name);
      onOpenDocument(doc.documentId);
    } catch (err) {
      notify(`No se pudo abrir el archivo: ${(err as Error).message}`, 'error');
    } finally {
      setBusy(null);
    }
  };

  const applyColor = (c: string, kind: 'mark' | 'ink') => {
    if (kind === 'mark') setMarkColor(c);
    else setInkColor(c);
    if (selectedId) dispatch({ type: 'update', id: selectedId, patch: { color: c } });
  };

  const byPage = useMemo(() => {
    const map = new Map<number, Annotation[]>();
    for (const a of state.items) map.set(a.page, [...(map.get(a.page) ?? []), a]);
    return map;
  }, [state.items]);

  const saveLabel: Record<SaveStatus, string> = {
    idle: '',
    pending: 'Cambios sin guardar',
    saving: 'Guardando…',
    saved: 'Guardado',
    error: 'Error al guardar',
  };

  return (
    <section className="panel viewer" aria-label="Visor y editor de PDF">
      <header className="panel-header">
        <div className="panel-title doc-title">
          <Icon name="file" size={18} />
          <h2 title={info?.fileName}>{info?.title ?? 'Visor de informes'}</h2>
          {info && info.version > 0 && <span className="badge">v{info.version}</span>}
          {saveStatus !== 'idle' && <span className={`save-status ${saveStatus}`}>{saveLabel[saveStatus]}</span>}
        </div>
        <div className="header-actions">
          <input ref={fileInputRef} type="file" accept="application/pdf,.pdf" hidden onChange={openLocal} />
          <button className="btn ghost" onClick={() => fileInputRef.current?.click()} disabled={busy !== null} title="Abrir un PDF del equipo">
            <Icon name="folder" size={16} /> Abrir
          </button>
          <button className="btn ghost" onClick={download} disabled={!pdf || busy !== null} title="Descargar el PDF con las anotaciones">
            <Icon name="download" size={16} /> {busy === 'download' ? 'Exportando…' : 'Descargar'}
          </button>
          <button className="btn primary" onClick={upload} disabled={!pdf || busy !== null} title="Subir una versión anotada a S3">
            <Icon name="upload" size={16} /> {busy === 'upload' ? 'Subiendo…' : 'Subir versión'}
          </button>
          <button
            className={`btn icon ghost ${sidebarOpen ? 'active' : ''}`}
            onClick={() => setSidebarOpen((o) => !o)}
            disabled={!pdf}
            title="Panel de anotaciones"
          >
            <Icon name="sidebar" size={16} />
          </button>
        </div>
      </header>

      <PdfToolbar
        tool={tool}
        onTool={(t) => {
          setTool(t);
          setSelectionMenu(null);
        }}
        markColor={markColor}
        inkColor={inkColor}
        onColor={applyColor}
        scale={scale}
        onZoom={(s) => setScale(clampScale(s))}
        onFit={() => fitWidth()}
        canUndo={state.past.length > 0}
        canRedo={state.future.length > 0}
        onUndo={() => dispatch({ type: 'undo' })}
        onRedo={() => dispatch({ type: 'redo' })}
        disabled={!pdf}
      />

      <div className="viewer-body">
        <div className={`pdf-scroll tool-${tool}`} ref={scrollRef} onMouseUp={onPagesMouseUp} onScroll={onScroll}>
          {!documentId && !loading && (
            <div className="viewer-empty">
              <div className="viewer-empty-art">
                <Icon name="file" size={36} />
              </div>
              <h3>Aún no hay ningún informe abierto</h3>
              <p>Pide un informe al asistente de la izquierda, o abre un PDF de tu equipo para anotarlo.</p>
              <button className="btn" onClick={() => fileInputRef.current?.click()}>
                <Icon name="folder" size={16} /> Abrir un PDF
              </button>
            </div>
          )}
          {loading && <div className="viewer-status">Cargando documento…</div>}
          {error && <div className="viewer-status error">{error}</div>}
          {pdf && !loading && (
            <EditorContext.Provider value={editor}>
              <div className="pdf-pages">
                {sizes.map((size, i) => (
                  <PdfPage key={`${documentId}-${i}`} pdf={pdf} pageNumber={i + 1} size={size} annotations={byPage.get(i + 1) ?? []} />
                ))}
              </div>
            </EditorContext.Provider>
          )}
          {selectionMenu && (
            <div className="selection-menu" style={{ left: selectionMenu.x, top: selectionMenu.y }} onMouseDown={(e) => e.preventDefault()}>
              {MARKUP.map((k) => (
                <button
                  key={k}
                  onClick={() => {
                    addMarkup(k);
                    setSelectionMenu(null);
                  }}
                  title={{ highlight: 'Resaltar', underline: 'Subrayar', strike: 'Tachar' }[k]}
                >
                  <Icon name={k} size={16} />
                </button>
              ))}
            </div>
          )}
        </div>

        {pdf && sidebarOpen && (
          <AnnotationsSidebar
            annotations={state.items}
            selectedId={selectedId}
            onSelect={focusAnnotation}
            dispatch={dispatch}
            onClose={() => setSidebarOpen(false)}
          />
        )}
      </div>

      {pdf && (
        <footer className="viewer-footer">
          <span>
            Página{' '}
            <input
              type="number"
              min={1}
              max={sizes.length}
              value={currentPage}
              onChange={(e) => {
                const n = Number(e.target.value);
                if (n >= 1 && n <= sizes.length) {
                  setCurrentPage(n);
                  goToPage(n);
                }
              }}
            />{' '}
            de {sizes.length}
          </span>
          <span className="muted">{state.items.length} anotaciones</span>
        </footer>
      )}

      {toast && <div className={`toast ${toast.kind}`}>{toast.text}</div>}
    </section>
  );
}
