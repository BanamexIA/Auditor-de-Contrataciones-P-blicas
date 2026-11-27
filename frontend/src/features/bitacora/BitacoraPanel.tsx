import { useCallback, useEffect, useState } from 'react';
import { auditor } from '../../api/auditor';
import { Icon } from '../../components/Icon';
import type { Caso, EventoBitacora } from '../../types/auditor';

/** Nombre legible de cada tipo de evento (contrato 5: docs/contratos/evento_bitacora.md). */
const NOMBRE: Record<string, string> = {
  solicitud: 'Solicitud',
  transicion: 'Cambio de estado',
  llamada_llm: 'Llamada al modelo',
  sql_generado: 'SQL generado',
  sql_rechazado: 'SQL rechazado',
  sql_ejecutado: 'SQL ejecutado',
  calidad_evaluada: 'Calidad de datos',
  reglas_evaluadas: 'Reglas evaluadas',
  normas_recuperadas: 'Normas recuperadas',
  reporte_guardado: 'Reporte guardado',
  decision: 'Decisión del auditor',
  error: 'Error',
};

const FINALES = ['en_revision', 'cerrado', 'bloqueado'];
/** Quién descartó el intento del Agente Consulta (agents/consulta/agent.py). */
const ETAPA_RECHAZO: Record<string, string> = {
  validador: 'validador de SQL',
  base: 'PostgreSQL',
  formato: 'formato de la respuesta',
  cobertura: 'revisión de cobertura',
};
const CADA_MS = 4000;

const num = (v: unknown) => (typeof v === 'number' ? v : Number(v ?? 0)) || 0;
const lista = (v: unknown) => (Array.isArray(v) ? v : []);
const hora = (iso: string) =>
  new Date(iso).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

/** Una línea en español con lo importante de cada evento; el JSON completo va en «Detalle». */
function resumen(ev: EventoBitacora): string {
  const d = ev.detalle ?? {};
  switch (ev.evento) {
    case 'solicitud':
      return `“${d.texto ?? ''}”`;
    case 'transicion':
      return [
        `${d.de ?? 'nuevo'} → ${d.a}`,
        d.usuario ? `por ${d.usuario}` : '',
        d.motivo ? `· motivo: ${d.motivo}` : '',
        d.motivo_desbloqueado ? `· desbloqueado (antes: ${d.motivo_desbloqueado})` : '',
      ]
        .filter(Boolean)
        .join(' ');
    case 'llamada_llm': {
      const tokens = d.tokens_entrada != null ? ` · ${d.tokens_entrada} → ${d.tokens_salida} tokens` : '';
      return `${d.agente ?? 'agente'} · ${d.estado === 'ok' ? 'ok' : `error (${d.tipo_error ?? '?'})`} · ${(
        num(d.latencia_ms) / 1000
      ).toFixed(1)} s${tokens}`;
    }
    case 'sql_generado':
      return lista(d.supuestos).length ? `Supuestos: ${lista(d.supuestos).join('; ')}` : 'Propuesto por el Agente Consulta';
    case 'sql_rechazado':
      return `${d.intento ? `Intento ${d.intento}` : 'Rechazado'}${d.etapa ? ` (${ETAPA_RECHAZO[String(d.etapa)] ?? d.etapa})` : ''}: ${
        d.motivo ?? '—'
      }`;
    case 'sql_ejecutado':
      return `${num(d.filas)} fila(s) en ${Math.round(num(d.duracion_ms))} ms, en solo lectura${d.truncado ? ' · truncado al límite' : ''}`;
    case 'calidad_evaluada': {
      const problemas = Object.values((d.problemas as Record<string, unknown>) ?? {}).reduce<number>((a, b) => a + num(b), 0);
      return `${num(d.contratos)} contrato(s) revisados · ${problemas} problema(s)${
        num(d.contradicciones) ? ` · ${num(d.contradicciones)} contradicción(es)` : ''
      }`;
    }
    case 'reglas_evaluadas':
      return `${num(d.senales)} señal(es) · ${num(d.evaluadas)} evaluadas · ${num(d.no_evaluables)} no evaluables${
        d.version_reglas ? ` · reglas v${d.version_reglas}` : ''
      }`;
    case 'normas_recuperadas':
      return d.rag === false
        ? 'Sin búsqueda normativa (no había laptop para el RAG)'
        : `${lista(d.normas).length} fragmento(s) de norma · ${lista(d.sin_soporte).length} señal(es) sin norma`;
    case 'reporte_guardado':
      return `Versión ${d.version} · SHA-256 ${String(d.sha256 ?? '').slice(0, 12)}…`;
    case 'decision':
      return `${d.decision}${d.anterior ? ` (antes: ${d.anterior})` : ''}${d.comentario ? ` — “${d.comentario}”` : ''}`;
    case 'error':
      return `${d.tipo ?? 'Error'}: ${d.mensaje ?? ''}`;
    default:
      return '';
  }
}

function sqlDe(ev: EventoBitacora): string | null {
  return ['sql_generado', 'sql_rechazado'].includes(ev.evento) && typeof ev.detalle?.sql === 'string'
    ? (ev.detalle.sql as string)
    : null;
}

/** Totales para el encabezado: cuántas veces se usó el modelo, cuánto tardó y en qué equipos. */
function totales(eventos: EventoBitacora[]) {
  const llamadas = eventos.filter((e) => e.evento === 'llamada_llm');
  return {
    llamadas: llamadas.length,
    fallidas: llamadas.filter((e) => e.detalle?.estado !== 'ok').length,
    segundos: llamadas.reduce((s, e) => s + num(e.detalle?.latencia_ms), 0) / 1000,
    modelos: [...new Set(eventos.map((e) => e.modelo).filter(Boolean))] as string[],
    equipos: [...new Set(eventos.map((e) => e.equipo).filter(Boolean))] as string[],
    errores: eventos.filter((e) => e.evento === 'error').length,
  };
}

function descargar(casoId: string, caso: Caso | null, eventos: EventoBitacora[]) {
  const datos = { caso_id: casoId, estado: caso?.estado ?? null, exportado: new Date().toISOString(), eventos };
  const url = URL.createObjectURL(new Blob([JSON.stringify(datos, null, 2)], { type: 'application/json' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = `bitacora-${casoId}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

/** Rastro del caso (HU-06): todo lo que pasó, en orden, tal como lo guardó el backend. Solo lectura. */
export function BitacoraPanel({ casoId, visible }: { casoId: string | null; visible: boolean }) {
  const [caso, setCaso] = useState<Caso | null>(null);
  const [eventos, setEventos] = useState<EventoBitacora[]>([]);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    if (!casoId) return;
    setCargando(true);
    setError(null);
    try {
      const [c, ev] = await Promise.all([auditor.caso(casoId), auditor.bitacora(casoId)]);
      setCaso(c);
      setEventos(ev);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCargando(false);
    }
  }, [casoId]);

  useEffect(() => {
    setCaso(null);
    setEventos([]);
  }, [casoId]);

  // Carga al abrir la pestaña y, mientras el caso siga corriendo, cada pocos segundos.
  const enCurso = !caso || !FINALES.includes(caso.estado);
  useEffect(() => {
    if (!visible || !casoId) return;
    void cargar();
    if (!enCurso) return;
    const t = window.setInterval(() => void cargar(), CADA_MS);
    return () => window.clearInterval(t);
  }, [visible, casoId, enCurso, cargar]);

  if (!casoId) {
    return (
      <div className="viewer-empty">
        <div className="viewer-empty-art">
          <Icon name="note" size={36} />
        </div>
        <h3>Sin caso abierto</h3>
        <p>Haz una pregunta en el chat o elige «Ver bitácora» en un mensaje para ver su rastro.</p>
      </div>
    );
  }

  const t = totales(eventos);

  return (
    <div className="senales-panel bitacora-panel">
      <div className="senales-resumen">
        <div>
          <strong>Caso</strong> <code>{casoId}</code>
          {caso && <span className={`chip estado-${caso.estado}`}>{caso.estado}</span>}
          {enCurso && caso && <span className="chip">en curso</span>}
        </div>
        <div className="senales-acciones">
          <span className="muted">
            {eventos.length} evento(s) · {t.llamadas} llamada(s) al modelo
            {t.fallidas ? ` (${t.fallidas} fallida(s))` : ''} · {t.segundos.toFixed(1)} s de modelo
            {t.errores ? ` · ${t.errores} error(es)` : ''}
          </span>
          <button className="btn ghost" onClick={() => void cargar()} disabled={cargando} title="Recargar">
            Recargar
          </button>
          <button className="btn ghost" onClick={() => descargar(casoId, caso, eventos)} disabled={!eventos.length} title="Descargar el rastro completo en JSON">
            <Icon name="download" size={14} /> JSON
          </button>
        </div>
        {(t.modelos.length > 0 || t.equipos.length > 0) && (
          <div className="chips">
            {t.modelos.map((m) => (
              <span key={m} className="chip">
                Modelo {m}
              </span>
            ))}
            {t.equipos.map((e) => (
              <span key={e} className="chip">
                Equipo {e}
              </span>
            ))}
          </div>
        )}
        <p className="aviso">
          La bitácora solo se agrega, nunca se edita ni se borra. Registra qué se pidió, qué SQL corrió, qué reglas y normas se
          usaron, qué modelo respondió y en qué equipo, y cada decisión del auditor.
        </p>
      </div>

      {error && <p className="senal-error">{error}</p>}
      {cargando && eventos.length === 0 ? (
        <div className="viewer-status">Cargando bitácora…</div>
      ) : (
        <ol className="bitacora-lista">
          {eventos.map((ev) => {
            const sql = sqlDe(ev);
            return (
              <li key={ev.id} className={`evento ev-${ev.evento}${ev.detalle?.estado === 'error' ? ' ev-error' : ''}`}>
                <header>
                  <strong>{NOMBRE[ev.evento] ?? ev.evento}</strong>
                  <span className="chips">
                    <span className="chip">{ev.etapa}</span>
                    {ev.modelo && <span className="chip">{ev.modelo}</span>}
                    {ev.equipo && <span className="chip">{ev.equipo}</span>}
                    <time dateTime={ev.created_at} className="muted">
                      {hora(ev.created_at)}
                    </time>
                  </span>
                </header>
                {resumen(ev) && <p className="criterio">{resumen(ev)}</p>}
                {sql && <pre className="bitacora-sql">{sql}</pre>}
                {ev.detalle?.sql_oculto === true && (
                  <p className="aviso">El texto del SQL solo es visible para el rol de administrador.</p>
                )}
                <details className="bitacora-detalle">
                  <summary>Detalle</summary>
                  <pre>{JSON.stringify(ev.detalle, null, 2)}</pre>
                </details>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
