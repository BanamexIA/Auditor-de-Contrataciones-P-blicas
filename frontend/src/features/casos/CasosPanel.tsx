import { useCallback, useEffect, useState } from 'react';
import { auditor } from '../../api/auditor';
import { Icon } from '../../components/Icon';
import type { Caso, EstadoCaso, Usuario } from '../../types/auditor';

const ESTADO: Record<EstadoCaso, string> = {
  recibido: 'Recibido',
  consultado: 'Consultado',
  detectado: 'Detectado',
  normado: 'Normado',
  reportado: 'Reportado',
  en_revision: 'En revisión',
  cerrado: 'Cerrado',
  bloqueado: 'Bloqueado',
};

const fecha = (iso?: string) =>
  iso ? new Date(iso).toLocaleString('es-MX', { dateStyle: 'short', timeStyle: 'short' }) : '';

/** Casos recientes para volver a abrir uno (su reporte, señales o bitácora) aunque se haya recargado la página. */
export function CasosPanel({
  usuario,
  casoActivo,
  visible,
  onAbrir,
}: {
  usuario: Usuario | null;
  casoActivo: string | null;
  visible: boolean;
  onAbrir: (caso: Caso) => void;
}) {
  const [casos, setCasos] = useState<Caso[]>([]);
  const [soloMios, setSoloMios] = useState(true);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      setCasos(await auditor.listarCasos(100));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    if (visible) void cargar();
  }, [visible, cargar]);

  const lista = soloMios && usuario ? casos.filter((c) => c.creado_por === usuario.usuario) : casos;

  return (
    <div className="senales-panel casos-panel">
      <div className="senales-resumen">
        <div className="senales-acciones">
          <span className="muted">
            {lista.length} caso{lista.length === 1 ? '' : 's'}
            {soloMios && usuario ? ' tuyos' : ''} · los más recientes primero
          </span>
          {usuario && (
            <label className="casos-filtro">
              <input type="checkbox" checked={soloMios} onChange={(e) => setSoloMios(e.target.checked)} /> Solo míos
            </label>
          )}
          <button className="btn ghost" onClick={() => void cargar()} disabled={cargando}>
            Recargar
          </button>
        </div>
      </div>
      {error && <p className="senal-error">{error}</p>}
      {cargando && casos.length === 0 ? (
        <div className="viewer-status">Cargando casos…</div>
      ) : lista.length === 0 ? (
        <div className="viewer-empty">
          <div className="viewer-empty-art">
            <Icon name="folder" size={36} />
          </div>
          <h3>Sin casos</h3>
          <p>Haz una pregunta en el chat para crear el primero.</p>
        </div>
      ) : (
        <ul className="casos-lista">
          {lista.map((c) => (
            <li key={c.id}>
              <button className={`caso-item ${c.id === casoActivo ? 'active' : ''}`} onClick={() => onAbrir(c)}>
                <span className="caso-solicitud">{c.solicitud}</span>
                <span className="caso-meta">
                  <span className={`chip estado-${c.estado}`}>{ESTADO[c.estado] ?? c.estado}</span>
                  <span className="muted">
                    {fecha(c.created_at)}
                    {c.creado_por && (!soloMios || !usuario) ? ` · ${c.creado_por}` : ''}
                  </span>
                </span>
                {c.estado === 'bloqueado' && c.motivo_bloqueo && <span className="caso-motivo">{c.motivo_bloqueo}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
