import { useCallback, useEffect, useState } from 'react';
import { auditor } from '../../api/auditor';
import { Icon } from '../../components/Icon';
import type { Caso, Decision, Senal } from '../../types/auditor';

const ETIQUETA: Record<Decision, string> = {
  relevante: 'Relevante',
  descartada: 'Descartada',
  pendiente: 'Pendiente',
};

const ESTADO: Record<string, string> = {
  en_revision: 'En revisión',
  cerrado: 'Cerrado',
  bloqueado: 'Bloqueado',
};

function texto(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

function SenalCard({ casoId, senal, cerrado, onCambio }: { casoId: string; senal: Senal; cerrado: boolean; onCambio: () => void }) {
  const d = senal.datos;
  const [comentario, setComentario] = useState(senal.decision?.comentario ?? '');
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const actual = senal.decision?.decision;

  const decidir = async (decision: Decision) => {
    if (decision === 'descartada' && !comentario.trim()) {
      setError('Para descartar una señal escribe por qué (queda en la bitácora).');
      return;
    }
    setGuardando(true);
    setError(null);
    try {
      await auditor.decidir(casoId, senal.id, decision, comentario);
      onCambio();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setGuardando(false);
    }
  };

  const valores = Object.entries(d.valores_calculados ?? {});

  return (
    <li className={`senal ${actual ?? 'sin-decidir'}`}>
      <header>
        <strong>{d.nombre ?? senal.tipo}</strong>
        <span className="chips">
          {d.estado === 'no_evaluable' && <span className="chip warn">No evaluable</span>}
          {d.nivel && <span className={`chip nivel-${d.nivel}`}>Nivel {d.nivel}</span>}
          {d.confianza && <span className="chip">Confianza {d.confianza}</span>}
        </span>
      </header>
      {d.criterio && <p className="criterio">{d.criterio}</p>}
      {d.estado === 'no_evaluable' && (
        <p className="criterio warn">
          {d.motivo ?? 'Faltan datos para evaluarla'}
          {d.campos_faltantes?.length ? `: ${d.campos_faltantes.join(', ')}` : ''}
        </p>
      )}
      {(valores.length > 0 || d.umbral != null) && (
        <dl className="valores">
          {d.umbral != null && (
            <div className="par">
              <dt>Umbral</dt>
              <dd>{texto(d.umbral)}</dd>
            </div>
          )}
          {valores.slice(0, 6).map(([k, v]) => (
            <div key={k} className="par">
              <dt>{k}</dt>
              <dd>{texto(v)}</dd>
            </div>
          ))}
        </dl>
      )}
      {d.contratos_ids?.length ? (
        <p className="contratos" title={d.contratos_ids.join(', ')}>
          Contratos: {d.contratos_ids.slice(0, 5).join(', ')}
          {d.contratos_ids.length > 5 ? ` y ${d.contratos_ids.length - 5} más` : ''}
        </p>
      ) : null}

      {senal.decision && (
        <p className="decision-actual">
          {ETIQUETA[senal.decision.decision]}
          {senal.decision.decidido_por ? ` por ${senal.decision.decidido_por}` : ''}
          {senal.decision.comentario ? ` — “${senal.decision.comentario}”` : ''}
        </p>
      )}

      {!cerrado && (
        <div className="decidir">
          <textarea
            rows={1}
            placeholder="Comentario (obligatorio para descartar)"
            value={comentario}
            onChange={(e) => setComentario(e.target.value)}
          />
          <div className="botones">
            {(['relevante', 'descartada', 'pendiente'] as Decision[]).map((dec) => (
              <button
                key={dec}
                className={`btn ${actual === dec ? 'primary' : 'ghost'} dec-${dec}`}
                disabled={guardando}
                onClick={() => void decidir(dec)}
              >
                {ETIQUETA[dec]}
              </button>
            ))}
          </div>
        </div>
      )}
      {error && <p className="senal-error">{error}</p>}
    </li>
  );
}

/** Revisión humana: decidir cada señal y cerrar el caso. Todo queda en la bitácora. */
export function SenalesPanel({ casoId }: { casoId: string | null }) {
  const [caso, setCaso] = useState<Caso | null>(null);
  const [senales, setSenales] = useState<Senal[]>([]);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cerrando, setCerrando] = useState(false);

  const cargar = useCallback(async () => {
    if (!casoId) return;
    setCargando(true);
    setError(null);
    try {
      const [c, s] = await Promise.all([auditor.caso(casoId), auditor.senales(casoId)]);
      setCaso(c);
      setSenales(s);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCargando(false);
    }
  }, [casoId]);

  useEffect(() => {
    setCaso(null);
    setSenales([]);
    void cargar();
  }, [cargar]);

  if (!casoId) {
    return (
      <div className="viewer-empty">
        <div className="viewer-empty-art">
          <Icon name="note" size={36} />
        </div>
        <h3>Sin caso abierto</h3>
        <p>Genera un reporte desde el chat para revisar sus señales.</p>
      </div>
    );
  }

  const cerrado = caso?.estado === 'cerrado';
  // Igual que el backend: 'pendiente' cuenta como decisión (queda registrada); sin decisión no.
  const sinDecidir = senales.filter((s) => !s.decision).length;
  const puedeCerrar = caso?.estado === 'en_revision' && sinDecidir === 0;

  const cerrar = async () => {
    setCerrando(true);
    setError(null);
    try {
      setCaso(await auditor.transitar(casoId, 'cerrado'));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCerrando(false);
    }
  };

  return (
    <div className="senales-panel">
      <div className="senales-resumen">
        <div>
          <strong>Caso</strong> <code>{casoId}</code>
          {caso && <span className={`chip estado-${caso.estado}`}>{ESTADO[caso.estado] ?? caso.estado}</span>}
        </div>
        <div className="senales-acciones">
          <span className="muted">
            {senales.length} señal{senales.length === 1 ? '' : 'es'} · {sinDecidir} sin decidir
          </span>
          <button className="btn ghost" onClick={() => void cargar()} disabled={cargando} title="Recargar">
            Recargar
          </button>
          {!cerrado && (
            <button
              className="btn primary"
              onClick={() => void cerrar()}
              disabled={!puedeCerrar || cerrando}
              title={puedeCerrar ? 'Cerrar el caso' : 'Registra una decisión en cada señal para cerrar el caso'}
            >
              {cerrando ? 'Cerrando…' : 'Cerrar caso'}
            </button>
          )}
        </div>
        <p className="aviso">
          Las señales son indicios para revisión humana; no constituyen una determinación de fraude ni de responsabilidad legal. Cada
          decisión queda registrada con tu usuario.
        </p>
      </div>
      {error && <p className="senal-error">{error}</p>}
      {cargando && senales.length === 0 ? (
        <div className="viewer-status">Cargando señales…</div>
      ) : senales.length === 0 ? (
        <p className="muted senales-vacio">Este caso no generó señales con las reglas actuales.</p>
      ) : (
        <ul className="senales-lista">
          {senales.map((s) => (
            <SenalCard key={s.id} casoId={casoId} senal={s} cerrado={cerrado} onCambio={() => void cargar()} />
          ))}
        </ul>
      )}
    </div>
  );
}
