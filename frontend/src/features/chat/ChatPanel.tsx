import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { Icon } from '../../components/Icon';
import type { ReporteRef, Usuario } from '../../types/auditor';
import { MessageText } from './MessageText';
import { ResultTable } from './ResultTable';
import { useChat } from './useChat';

interface ChatPanelProps {
  usuario: Usuario | null;
  reporteActivo: ReporteRef | null;
  onOpenReporte: (reporte: ReporteRef) => void;
  onLogout?: () => void;
}

/** Preguntas que el Agente Consulta contesta bien con los datos actuales. */
const SUGERENCIAS = [
  'Lista hasta 10 contratos de 2026 con coincidencia en el listado 69-B',
  'Lista hasta 10 contratos de 2015 con coincidencia en el listado 69-B que requieran revisión humana',
  '¿Cuántos contratos de ComprasMX 2026 hay por institución?',
];

export function ChatPanel({ usuario, reporteActivo, onOpenReporte, onLogout }: ChatPanelProps) {
  const { messages, pending, send, analizar, cancel, reset } = useChat({ onReporte: onOpenReporte });
  const [draft, setDraft] = useState('');
  const [segundos, setSegundos] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  // El modelo corre en una laptop: puede tardar. Se muestra cuánto lleva.
  useEffect(() => {
    if (!pending) return;
    setSegundos(0);
    const t = window.setInterval(() => setSegundos((s) => s + 1), 1000);
    return () => window.clearInterval(t);
  }, [pending]);

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

  // Pregunta del usuario que originó cada respuesta (título del reporte).
  const preguntaDe = (i: number) => messages[i - 1]?.content ?? 'Reporte';

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
              listado 69-B, y después puedes analizar los contratos y generar el reporte de señales de riesgo.
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
          messages.map((m, i) => (
            <article key={m.id} className={`message ${m.role} ${m.status ?? ''}`}>
              {m.status === 'pending' ? (
                <div className="pending">
                  <div className="typing" aria-label="Generando respuesta">
                    <span />
                    <span />
                    <span />
                  </div>
                  <small>El agente está consultando… {segundos} s</small>
                </div>
              ) : (
                <MessageText text={m.content} />
              )}

              {m.consulta && m.consulta.filas.length > 0 && <ResultTable filas={m.consulta.filas} total={m.consulta.totalFilas} />}

              {m.consulta && (
                <details className="sql">
                  <summary>SQL generado · {m.consulta.modelo} en {m.consulta.equipo}</summary>
                  <pre>{m.consulta.sql}</pre>
                </details>
              )}

              {m.consulta && m.consulta.totalFilas > 0 && !m.analisis && (
                <button className="btn primary analizar" onClick={() => void analizar(m.id, m.consulta!.casoId, preguntaDe(i))}>
                  <Icon name="sparkle" size={16} /> Analizar y generar reporte
                </button>
              )}
              {m.analisis?.estado === 'corriendo' && (
                <p className="analisis-estado">Revisando calidad, detectando señales y generando el reporte…</p>
              )}
              {m.analisis?.estado === 'error' && <p className="analisis-estado error">{m.analisis.mensaje}</p>}
              {m.analisis?.estado === 'listo' && (
                <button
                  className={`report-card ${reporteActivo?.casoId === m.analisis.reporte.casoId ? 'active' : ''}`}
                  onClick={() => m.analisis?.estado === 'listo' && onOpenReporte(m.analisis.reporte)}
                >
                  <span className="report-card-icon">
                    <Icon name="file" size={20} />
                  </span>
                  <span className="report-card-body">
                    <strong>Reporte v{m.analisis.reporte.version}</strong>
                    <small>{m.analisis.resumen}</small>
                  </span>
                </button>
              )}
              {m.casoId && m.status !== 'pending' && <small className="caso-id">Caso {m.casoId}</small>}
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
