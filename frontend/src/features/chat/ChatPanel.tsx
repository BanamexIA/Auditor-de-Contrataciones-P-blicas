import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { Icon } from '../../components/Icon';
import type { ReportRef } from '../../types/chat';
import { MessageText } from './MessageText';
import { useChat } from './useChat';

interface ChatPanelProps {
  activeDocumentId?: string;
  activeDocumentTitle?: string;
  onOpenReport: (report: ReportRef) => void;
}

const SUGGESTIONS = [
  'Elabora un informe de ventas del tercer trimestre con hallazgos y recomendaciones',
  'Resume los riesgos operativos del proyecto y propone un plan de mitigación',
  'Prepara un análisis comparativo de proveedores de almacenamiento en la nube',
];

export function ChatPanel({ activeDocumentId, activeDocumentTitle, onOpenReport }: ChatPanelProps) {
  const { messages, pending, send, cancel, reset } = useChat({ onReport: onOpenReport });
  const [draft, setDraft] = useState('');
  const [useContext, setUseContext] = useState(true);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  // El textarea crece con el contenido hasta un máximo.
  useEffect(() => {
    const fit = () => {
      const el = inputRef.current;
      if (!el) return;
      el.style.height = '0px';
      el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
    };
    fit();
    window.addEventListener('resize', fit);
    return () => window.removeEventListener('resize', fit);
  }, [draft]);

  const submit = (text = draft) => {
    if (!text.trim() || pending) return;
    void send(text, useContext ? activeDocumentId : undefined);
    setDraft('');
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <section className="panel chat" aria-label="Conversación con el LLM">
      <header className="panel-header">
        <div className="panel-title">
          <span className="brand-dot" />
          <h1>Asistente</h1>
        </div>
        <button className="btn ghost" onClick={reset} disabled={messages.length === 0} title="Nueva conversación">
          <Icon name="plus" size={16} /> Nueva
        </button>
      </header>

      <div className="chat-messages" ref={listRef}>
        {messages.length === 0 ? (
          <div className="chat-empty">
            <div className="chat-empty-icon">
              <Icon name="sparkle" size={28} />
            </div>
            <h2>¿Qué informe necesitas?</h2>
            <p>Describe lo que quieres analizar. La respuesta llegará como un PDF en el visor de la derecha.</p>
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
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
                <div className="typing" aria-label="Generando respuesta">
                  <span />
                  <span />
                  <span />
                </div>
              ) : (
                <MessageText text={m.content} />
              )}
              {m.report && (
                <button
                  className={`report-card ${m.report.documentId === activeDocumentId ? 'active' : ''}`}
                  onClick={() => onOpenReport(m.report!)}
                >
                  <span className="report-card-icon">
                    <Icon name="file" size={20} />
                  </span>
                  <span className="report-card-body">
                    <strong>{m.report.title}</strong>
                    <small>{m.report.documentId === activeDocumentId ? 'Abierto en el visor' : 'Abrir en el visor'}</small>
                  </span>
                </button>
              )}
            </article>
          ))
        )}
      </div>

      <footer className="composer">
        {activeDocumentId && (
          <label className="context-toggle" title="El LLM recibirá el documento abierto como contexto">
            <input type="checkbox" checked={useContext} onChange={(e) => setUseContext(e.target.checked)} />
            <Icon name="link" size={14} />
            <span>
              Usar como contexto: <em>{activeDocumentTitle ?? 'documento abierto'}</em>
            </span>
          </label>
        )}
        <div className="composer-box">
          <textarea
            ref={inputRef}
            rows={1}
            value={draft}
            placeholder="Escribe tu petición…"
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
      </footer>
    </section>
  );
}
