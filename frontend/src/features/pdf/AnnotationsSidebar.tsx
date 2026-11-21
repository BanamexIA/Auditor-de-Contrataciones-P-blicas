import { Icon, type IconName } from '../../components/Icon';
import type { Annotation, AnnotationType } from '../../types/annotations';
import type { AnnotationsAction } from './annotationsReducer';
import { INK_COLORS, MARK_COLORS } from './PdfToolbar';

const META: Record<AnnotationType, { label: string; icon: IconName }> = {
  highlight: { label: 'Resaltado', icon: 'highlight' },
  underline: { label: 'Subrayado', icon: 'underline' },
  strike: { label: 'Tachado', icon: 'strike' },
  note: { label: 'Nota', icon: 'note' },
  text: { label: 'Texto', icon: 'text' },
  edit: { label: 'Edición', icon: 'edit' },
};

function topOf(a: Annotation) {
  if (a.type === 'note') return a.y;
  if (a.type === 'text' || a.type === 'edit') return a.rect.y;
  return a.rects[0]?.y ?? 0;
}

function preview(a: Annotation) {
  switch (a.type) {
    case 'edit':
      return `“${a.originalText}” → “${a.text}”`;
    case 'note':
    case 'text':
      return a.text || '(vacío)';
    default:
      return `“${a.text}”`;
  }
}

interface Props {
  annotations: Annotation[];
  selectedId: string | null;
  onSelect: (a: Annotation) => void;
  dispatch: (a: AnnotationsAction) => void;
  onClose: () => void;
}

export function AnnotationsSidebar({ annotations, selectedId, onSelect, dispatch, onClose }: Props) {
  const sorted = [...annotations].sort((a, b) => a.page - b.page || topOf(a) - topOf(b));

  return (
    <aside className="ann-sidebar" aria-label="Anotaciones">
      <header>
        <h3>Mis notas</h3>
        <span className="count">{annotations.length}</span>
        <button className="btn icon ghost" onClick={onClose} title="Ocultar panel">
          <Icon name="close" size={15} />
        </button>
      </header>
      {sorted.length === 0 ? (
        <p className="ann-empty">Aún no hay notas. Resalta, subraya o agrega notas; se guardan solo en este navegador y no cambian el reporte.</p>
      ) : (
        <ul>
          {sorted.map((a) => {
            const meta = META[a.type];
            const selected = a.id === selectedId;
            const isMarkup = a.type === 'highlight' || a.type === 'underline' || a.type === 'strike';
            const palette = a.type === 'text' || a.type === 'edit' ? INK_COLORS : MARK_COLORS;
            return (
              <li key={a.id} className={selected ? 'selected' : ''}>
                <button className="ann-item" onClick={() => onSelect(a)}>
                  <span className="ann-icon" style={{ color: a.type === 'text' || a.type === 'edit' ? a.color : undefined }}>
                    <span className="ann-color" style={{ background: a.color }} />
                    <Icon name={meta.icon} size={14} />
                  </span>
                  <span className="ann-body">
                    <span className="ann-meta">
                      {meta.label} · pág. {a.page}
                    </span>
                    <span className="ann-preview">{preview(a)}</span>
                    {isMarkup && a.comment && !selected && <span className="ann-comment">{a.comment}</span>}
                  </span>
                </button>
                {selected && (
                  <div className="ann-details">
                    {isMarkup ? (
                      <textarea
                        placeholder="Añadir comentario…"
                        value={a.comment}
                        rows={2}
                        onChange={(e) =>
                          dispatch({ type: 'update', id: a.id, patch: { comment: e.target.value }, coalesceKey: `comment-${a.id}` })
                        }
                      />
                    ) : (
                      <textarea
                        value={a.text}
                        rows={2}
                        onChange={(e) =>
                          dispatch({ type: 'update', id: a.id, patch: { text: e.target.value }, coalesceKey: `text-${a.id}` })
                        }
                      />
                    )}
                    <div className="ann-actions">
                      <div className="mini-swatches">
                        {palette.map((c) => (
                          <button
                            key={c}
                            className={`swatch small ${c === a.color ? 'active' : ''}`}
                            style={{ background: c }}
                            onClick={() => dispatch({ type: 'update', id: a.id, patch: { color: c } })}
                            title={c}
                          />
                        ))}
                      </div>
                      <button className="btn tiny danger-ghost" onClick={() => dispatch({ type: 'remove', id: a.id })}>
                        <Icon name="trash" size={13} /> Eliminar
                      </button>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
