import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { Icon } from '../../components/Icon';
import type { EstadoCaso, ReporteRef, Usuario } from '../../types/auditor';
import type { Progreso } from '../../types/chat';
import { MessageText } from './MessageText';
import { ResultTable } from './ResultTable';
import { useChat } from './useChat';

interface ChatPanelProps {
  usuario: Usuario | null;
  reporteActivo: ReporteRef | null;
  onOpenReporte: (reporte: ReporteRef) => void;
  onVerBitacora: (casoId: string) => void;
  onLogout?: () => void;
}

/** Etapas del orquestador, en orden, con el estado del caso que deja cada una al terminar. */
const ETAPAS: { estado: EstadoCaso; nombre: string }[] = [
  { estado: 'consultado', nombre: 'Consulta: pregunta → SQL de solo lectura' },
  { estado: 'detectado', nombre: 'Calidad y detección de señales' },
  { estado: 'normado', nombre: 'Normativo: normas vigentes (RAG)' },
  { estado: 'reportado', nombre: 'Reporte verificado' },
];
const ORDEN: EstadoCaso[] = ['recibido', 'consultado', 'detectado', 'normado', 'reportado', 'en_revision'];

function Etapas({ progreso }: { progreso: Progreso }) {
  const hecho = ORDEN.indexOf(progreso.estado);
  return (
    <div className="etapas">
      <ol>
        {ETAPAS.map((etapa, i) => {
          const indice = ORDEN.indexOf(etapa.estado);
          const clase = indice <= hecho ? 'hecha' : i === Math.max(0, hecho) ? 'actual' : '';
          return (
            <li key={etapa.estado} className={clase}>
              {etapa.nombre}
            </li>
          );
        })}
      </ol>
      <small>
        El orquestador está trabajando… {progreso.segundos} s{progreso.resumen ? ` · ${progreso.resumen}` : ''}
      </small>
    </div>
  );
}

/** Preguntas que el Agente Consulta contesta bien con los datos actuales. */
const SUGERENCIAS = [
  'Lista hasta 10 contratos de 2026 con coincidencia en el listado 69-B',
  'Lista hasta 10 contratos de 2015 con coincidencia en el listado 69-B que requieran revisión humana',
  '¿Cuántos contratos de ComprasMX 2026 hay por institución?',
];

export function ChatPanel({ usuario, reporteActivo, onOpenReporte, onVerBitacora, onLogout }: ChatPanelProps) {
  const { messages, pending, send, cancel, reset } = useChat({ onReporte: onOpenReporte });
  const [draft, setDraft] = useState('');
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);


  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = '0px';
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [draft]);

  const submit = (text = draft) => {
    if (!text.trim() || pending) return;
    void send(text);
    setDraft('');
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };


  return (
    <section className="panel chat" aria-label="Conversación con el Agente Consulta">
      <header className="panel-header">
        <div className="panel-title">
          <span className="brand-dot" />
          <h1>Auditor de contrataciones</h1>
        </div>
        <div className="header-actions">
          <button className="btn ghost" onClick={reset} disabled={messages.length === 0 || pending} title="Nueva conversación">
            <Icon name="plus" size={16} /> Nueva
          </button>
          {usuario && onLogout && (
            <button className="btn ghost" onClick={onLogout} title={`Cerrar la sesión de ${usuario.usuario}`}>
              {usuario.usuario} · Salir
            </button>
          )}
        </div>
      </header>

      <div className="chat-messages" ref={listRef}>
        {messages.length === 0 ? (
          <div className="chat-empty">
            <div className="chat-empty-icon">
              <Icon name="sparkle" size={28} />
            </div>
            <h2>¿Qué contratos quieres revisar?</h2>
            <p>
              Pregunta en español. El Agente Consulta genera un SQL de solo lectura sobre los datos de ComprasMX y del
              listado 69-B; luego el orquestador revisa la calidad, detecta señales, busca la norma y genera el reporte.
            </p>
            <div className="suggestions">
              {SUGERENCIAS.map((s) => (
                <button key={s} className="suggestion" onClick={() => submit(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m) => (
            <article key={m.id} className={`message ${m.role} ${m.status ?? ''}`}>
              {m.status === 'pending' ? (
                m.progreso ? (
                  <Etapas progreso={m.progreso} />
                ) : (
                  <div className="typing" aria-label="Generando respuesta">
                    <span />
                    <span />
                    <span />
                  </div>
                )
              ) : (
                <MessageText text={m.content} />
              )}

              {m.consulta && m.consulta.filas.length > 0 && <ResultTable filas={m.consulta.filas} total={m.consulta.totalFilas} />}

              {/* Sin SQL en el chat (retroalimentación del 2026-11-26): expone tablas y columnas. Queda en la
                  bitácora, visible solo para el rol admin. Aquí: supuestos y quién respondió. */}
              {m.consulta && m.consulta.supuestos.length > 0 && (
                <details className="sql">
                  <summary>Supuestos de la consulta</summary>
                  <ul className="supuestos">
                    {m.consulta.supuestos.map((s) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ul>
                </details>
              )}
              {m.consulta?.modelo && (
                <small className="caso-id">
                  Respondió {m.consulta.modelo}
                  {m.consulta.equipo ? ` en ${m.consulta.equipo}` : ''}
                </small>
              )}

              {m.reporte && (
                <button
                  className={`report-card ${reporteActivo?.casoId === m.reporte.ref.casoId ? 'active' : ''}`}
                  onClick={() => m.reporte && onOpenReporte(m.reporte.ref)}
                >
                  <span className="report-card-icon">
                    <Icon name="file" size={20} />
                  </span>
                  <span className="report-card-body">
                    <strong>Reporte v{m.reporte.ref.version}</strong>
                    <small>{m.reporte.resumen || 'Abrir en el visor'}</small>
                  </span>
                </button>
              )}
              {m.casoId && (
                <small className="caso-id">
                  Caso {m.casoId} ·{' '}
                  <button className="link" onClick={() => m.casoId && onVerBitacora(m.casoId)}>
                    Ver bitácora
                  </button>
                </small>
              )}
            </article>
          ))
        )}
      </div>

      <footer className="composer">
        <div className="composer-box">
          <textarea
            ref={inputRef}
            rows={1}
            value={draft}
            placeholder="Escribe tu pregunta sobre los contratos…"
            title="Enter para enviar · Mayús+Enter para salto de línea"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
          />
          {pending ? (
            <button className="btn icon danger" onClick={cancel} title="Cancelar">
              <Icon name="stop" size={16} />
            </button>
          ) : (
            <button className="btn icon primary" onClick={() => submit()} disabled={!draft.trim()} title="Enviar">
              <Icon name="send" size={16} />
            </button>
          )}
        </div>
        <p className="composer-note">Las respuestas son señales para revisión humana, no determinaciones de fraude.</p>
      </footer>
    </section>
  );
}
