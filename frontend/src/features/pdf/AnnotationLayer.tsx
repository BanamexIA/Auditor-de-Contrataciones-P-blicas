import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from 'react';
import type {
  Annotation,
  MarkupAnnotation,
  NoteAnnotation,
  TextBoxAnnotation,
  TextEditAnnotation,
} from '../../types/annotations';
import { Icon } from '../../components/Icon';
import { useEditor } from './editorContext';
import { newId } from '../../lib/id';

interface AnnotationLayerProps {
  page: number;
  annotations: Annotation[];
}

export function AnnotationLayer({ page, annotations }: AnnotationLayerProps) {
  const { tool, scale, createAt, select } = useEditor();
  const placing = tool === 'note' || tool === 'text';

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.target !== e.currentTarget) return;
    if (!placing) {
      select(null);
      return;
    }
    const box = e.currentTarget.getBoundingClientRect();
    createAt(page, (e.clientX - box.left) / scale, (e.clientY - box.top) / scale, tool);
    e.preventDefault();
  };

  return (
    <div className={`annotation-layer ${placing ? 'placing' : ''}`} onPointerDown={onPointerDown}>
      {annotations.map((a) => {
        switch (a.type) {
          case 'highlight':
          case 'underline':
          case 'strike':
            return <Markup key={a.id} ann={a} />;
          case 'note':
            return <Note key={a.id} ann={a} />;
          case 'text':
            return <TextBox key={a.id} ann={a} />;
          case 'edit':
            return <TextEdit key={a.id} ann={a} />;
        }
      })}
    </div>
  );
}

/* ---------- utilidades ---------- */

/** Arrastre con el puntero; las coordenadas se entregan en puntos PDF. */
function useDrag(onMove: (dx: number, dy: number, key: string) => void) {
  const { scale } = useEditor();
  return (e: ReactPointerEvent) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    const startX = e.clientX;
    const startY = e.clientY;
    const key = newId('drag');
    const move = (ev: PointerEvent) => onMove((ev.clientX - startX) / scale, (ev.clientY - startY) / scale, key);
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };
}

function AutoTextarea(props: {
  value: string;
  onChange: (v: string) => void;
  onBlur?: () => void;
  autoFocus?: boolean;
  style?: CSSProperties;
  placeholder?: string;
  className?: string;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = '0px';
    el.style.height = `${el.scrollHeight}px`;
  }, [props.value, props.style?.fontSize]);
  useEffect(() => {
    if (props.autoFocus) {
      ref.current?.focus({ preventScroll: true });
      ref.current?.select();
    }
  }, [props.autoFocus]);
  return (
    <textarea
      ref={ref}
      rows={1}
      className={props.className}
      value={props.value}
      placeholder={props.placeholder}
      style={props.style}
      spellCheck
      onChange={(e) => props.onChange(e.target.value)}
      onBlur={props.onBlur}
      onPointerDown={(e) => e.stopPropagation()}
    />
  );
}

/* ---------- subrayado / resaltado / tachado ---------- */

function Markup({ ann }: { ann: MarkupAnnotation }) {
  const { scale, selectedId, select, tool } = useEditor();
  const selected = selectedId === ann.id;
  return (
    <>
      {ann.rects.map((r, i) => (
        <div
          key={i}
          className={`markup ${ann.type} ${selected ? 'selected' : ''} ${tool === 'select' ? 'interactive' : ''}`}
          title={ann.comment || ann.text}
          style={
            {
              left: r.x * scale,
              top: r.y * scale,
              width: r.width * scale,
              height: r.height * scale,
              '--ann-color': ann.color,
            } as CSSProperties
          }
          onPointerDown={(e) => {
            e.stopPropagation();
            select(ann.id);
          }}
        />
      ))}
      {ann.comment && ann.rects[0] && (
        <span
          className="markup-comment-dot"
          style={{ left: (ann.rects[0].x + ann.rects[0].width) * scale, top: ann.rects[0].y * scale - 6 }}
          title={ann.comment}
        />
      )}
    </>
  );
}

/* ---------- notas adhesivas ---------- */

function Note({ ann }: { ann: NoteAnnotation }) {
  const { scale, selectedId, select, dispatch, focusId, clearFocus } = useEditor();
  const [open, setOpen] = useState(focusId === ann.id);
  const rootRef = useRef<HTMLDivElement>(null);
  const moved = useRef(false);
  // Si la nota está cerca del borde derecho, la ventana se abre hacia la izquierda.
  const [flip, setFlip] = useState(false);
  useLayoutEffect(() => {
    const layerWidth = rootRef.current?.parentElement?.clientWidth ?? Infinity;
    setFlip(ann.x * scale + 250 > layerWidth);
  }, [open, ann.x, scale]);
  const origin = useRef({ x: ann.x, y: ann.y });
  const selected = selectedId === ann.id;

  useEffect(() => {
    if (focusId === ann.id) setOpen(true);
  }, [focusId, ann.id]);
  useEffect(() => {
    if (!selected) setOpen(false);
  }, [selected]);

  const startDrag = useDrag((dx, dy, key) => {
    if (Math.abs(dx) + Math.abs(dy) > 2) moved.current = true;
    dispatch({
      type: 'update',
      id: ann.id,
      patch: { x: origin.current.x + dx, y: origin.current.y + dy },
      coalesceKey: key,
    });
  });

  return (
    <div ref={rootRef} className={`note ${selected ? 'selected' : ''}`} style={{ left: ann.x * scale, top: ann.y * scale }}>
      <button
        className="note-icon"
        style={{ '--ann-color': ann.color } as CSSProperties}
        title={ann.text || 'Nota'}
        onPointerDown={(e) => {
          moved.current = false;
          origin.current = { x: ann.x, y: ann.y };
          select(ann.id);
          startDrag(e);
        }}
        onClick={() => {
          if (!moved.current) setOpen((o) => !o);
        }}
      >
        <Icon name="note" size={14} />
      </button>
      {open && (
        <div className={`note-popup ${flip ? 'flip' : ''}`} onPointerDown={(e) => e.stopPropagation()}>
          <AutoTextarea
            value={ann.text}
            placeholder="Escribe una nota…"
            autoFocus={focusId === ann.id}
            onChange={(text) => dispatch({ type: 'update', id: ann.id, patch: { text }, coalesceKey: `text-${ann.id}` })}
            onBlur={clearFocus}
          />
          <div className="note-actions">
            <button className="btn tiny ghost" onClick={() => setOpen(false)}>
              Cerrar
            </button>
            <button className="btn tiny danger-ghost" onClick={() => dispatch({ type: 'remove', id: ann.id })}>
              <Icon name="trash" size={13} /> Eliminar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------- cuadros de texto libres ---------- */

function TextBox({ ann }: { ann: TextBoxAnnotation }) {
  const { scale, selectedId, select, dispatch, focusId, clearFocus } = useEditor();
  const selected = selectedId === ann.id;
  const origin = useRef(ann.rect);

  const startMove = useDrag((dx, dy, key) =>
    dispatch({
      type: 'update',
      id: ann.id,
      patch: { rect: { ...origin.current, x: origin.current.x + dx, y: origin.current.y + dy } },
      coalesceKey: key,
    }),
  );
  const startResize = useDrag((dx, _dy, key) =>
    dispatch({
      type: 'update',
      id: ann.id,
      patch: { rect: { ...origin.current, width: Math.max(40, origin.current.width + dx) } },
      coalesceKey: key,
    }),
  );

  return (
    <div
      className={`textbox ${selected ? 'selected' : ''}`}
      style={{ left: ann.rect.x * scale, top: ann.rect.y * scale, width: ann.rect.width * scale }}
      onPointerDown={(e) => {
        e.stopPropagation();
        select(ann.id);
      }}
    >
      <span
        className="drag-handle"
        title="Mover"
        onPointerDown={(e) => {
          origin.current = ann.rect;
          select(ann.id);
          startMove(e);
        }}
      />
      <AutoTextarea
        value={ann.text}
        placeholder="Escribe aquí…"
        autoFocus={focusId === ann.id}
        style={{ fontSize: ann.fontSize * scale, color: ann.color }}
        onChange={(text) => dispatch({ type: 'update', id: ann.id, patch: { text }, coalesceKey: `text-${ann.id}` })}
        onBlur={() => {
          clearFocus();
          if (!ann.text.trim()) dispatch({ type: 'remove', id: ann.id });
        }}
      />
      <span
        className="resize-handle"
        title="Cambiar ancho"
        onPointerDown={(e) => {
          origin.current = ann.rect;
          startResize(e);
        }}
      />
    </div>
  );
}

/* ---------- reemplazo de texto del PDF ---------- */

let measureCtx: CanvasRenderingContext2D | null = null;

/** Ancho del texto más largo (en puntos), con la misma fuente que se usa al exportar. */
export function measureLines(text: string, fontSize: number): number {
  measureCtx ??= document.createElement('canvas').getContext('2d');
  if (!measureCtx) return 0;
  measureCtx.font = `${fontSize}px Helvetica, Arial, sans-serif`;
  return Math.max(0, ...text.split('\n').map((l) => measureCtx!.measureText(l).width));
}

function TextEdit({ ann }: { ann: TextEditAnnotation }) {
  const { scale, selectedId, select, dispatch, focusId, clearFocus } = useEditor();
  const selected = selectedId === ann.id;
  // El reemplazo crece hacia la derecha si el texto nuevo es más largo que el original.
  const width = Math.max(ann.rect.width, measureLines(ann.text, ann.fontSize) + 2) * scale;
  return (
    <div
      className={`text-edit ${selected ? 'selected' : ''}`}
      title={`Original: ${ann.originalText}`}
      style={{
        left: ann.rect.x * scale,
        top: ann.rect.y * scale,
        width,
        minHeight: ann.rect.height * scale,
      }}
      onPointerDown={(e) => {
        e.stopPropagation();
        select(ann.id);
      }}
    >
      <AutoTextarea
        value={ann.text}
        autoFocus={focusId === ann.id}
        style={{ fontSize: ann.fontSize * scale, color: ann.color, lineHeight: 1.15 }}
        onChange={(text) => dispatch({ type: 'update', id: ann.id, patch: { text }, coalesceKey: `text-${ann.id}` })}
        onBlur={clearFocus}
      />
    </div>
  );
}
