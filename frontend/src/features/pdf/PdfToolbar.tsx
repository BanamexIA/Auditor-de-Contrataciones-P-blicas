import { Icon, type IconName } from '../../components/Icon';
import type { Tool } from '../../types/annotations';

export const MARK_COLORS = ['#ffd43b', '#69db7c', '#74c0fc', '#f783ac', '#ffa94d'];
export const INK_COLORS = ['#111827', '#c92a2a', '#1864ab', '#2b8a3e'];

const TOOLS: Array<{ id: Tool; icon: IconName; label: string; key: string }> = [
  { id: 'select', icon: 'cursor', label: 'Seleccionar', key: 'V' },
  { id: 'highlight', icon: 'highlight', label: 'Resaltar', key: 'H' },
  { id: 'underline', icon: 'underline', label: 'Subrayar', key: 'U' },
  { id: 'strike', icon: 'strike', label: 'Tachar', key: 'K' },
  { id: 'note', icon: 'note', label: 'Nota', key: 'N' },
  { id: 'text', icon: 'text', label: 'Cuadro de texto', key: 'T' },
  // Sin 'Editar texto del PDF': el reporte oficial es inmutable (SHA-256 y verificador de citas).
];

export const TOOL_KEYS: Record<string, Tool> = Object.fromEntries(TOOLS.map((t) => [t.key.toLowerCase(), t.id]));

const HINTS: Record<Tool, string> = {
  select: 'Selecciona texto para marcarlo, o haz clic en una anotación para editarla.',
  highlight: 'Selecciona texto con el ratón para resaltarlo.',
  underline: 'Selecciona texto con el ratón para subrayarlo.',
  strike: 'Selecciona texto con el ratón para tacharlo.',
  note: 'Haz clic en la página para pegar una nota.',
  text: 'Haz clic en la página para escribir un cuadro de texto.',
  edit: 'Haz clic sobre un fragmento del PDF para reescribirlo.',
};

interface PdfToolbarProps {
  tool: Tool;
  onTool: (t: Tool) => void;
  markColor: string;
  inkColor: string;
  onColor: (c: string, kind: 'mark' | 'ink') => void;
  scale: number;
  onZoom: (s: number) => void;
  onFit: () => void;
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
  disabled: boolean;
}

export function PdfToolbar(p: PdfToolbarProps) {
  const inkTool = p.tool === 'text' || p.tool === 'edit';
  const colors = inkTool ? INK_COLORS : MARK_COLORS;
  const current = inkTool ? p.inkColor : p.markColor;

  return (
    <div className="pdf-toolbar-wrap">
      <div className="pdf-toolbar" role="toolbar" aria-label="Herramientas del editor">
        <div className="tool-group">
          {TOOLS.map((t) => (
            <button
              key={t.id}
              className={`tool ${p.tool === t.id ? 'active' : ''}`}
              onClick={() => p.onTool(t.id)}
              title={`${t.label} (${t.key})`}
              aria-pressed={p.tool === t.id}
              disabled={p.disabled}
            >
              <Icon name={t.icon} />
            </button>
          ))}
        </div>

        <div className="tool-group colors" aria-label="Color">
          {colors.map((c) => (
            <button
              key={c}
              className={`swatch ${c === current ? 'active' : ''}`}
              style={{ background: c }}
              onClick={() => p.onColor(c, inkTool ? 'ink' : 'mark')}
              title={c}
              disabled={p.disabled}
            />
          ))}
        </div>

        <div className="tool-group">
          <button className="tool" onClick={p.onUndo} disabled={!p.canUndo} title="Deshacer (Ctrl+Z)">
            <Icon name="undo" />
          </button>
          <button className="tool" onClick={p.onRedo} disabled={!p.canRedo} title="Rehacer (Ctrl+Y)">
            <Icon name="redo" />
          </button>
        </div>

        <div className="tool-group">
          <button className="tool" onClick={() => p.onZoom(p.scale / 1.2)} disabled={p.disabled} title="Alejar">
            <Icon name="zoomOut" />
          </button>
          <span className="zoom-label">{Math.round(p.scale * 100)}%</span>
          <button className="tool" onClick={() => p.onZoom(p.scale * 1.2)} disabled={p.disabled} title="Acercar">
            <Icon name="zoomIn" />
          </button>
          <button className="tool" onClick={p.onFit} disabled={p.disabled} title="Ajustar al ancho">
            <Icon name="fit" />
          </button>
        </div>
      </div>
      {!p.disabled && <div className="tool-hint">{HINTS[p.tool]}</div>}
    </div>
  );
}
