import { useCallback, useRef, useState } from 'react';
import { auditor } from '../../api/auditor';
import type { ReporteRef } from '../../types/auditor';
import type { ChatMessage } from '../../types/chat';
import { newId, nowIso } from '../../lib/id';

interface UseChatOptions {
  onReporte?: (reporte: ReporteRef) => void;
}

const plural = (n: number, uno: string, varios: string) => `${n} ${n === 1 ? uno : varios}`;

export function useChat({ onReporte }: UseChatOptions = {}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const patch = (id: string, cambios: Partial<ChatMessage>) =>
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...cambios } : m)));

  const send = useCallback(
    async (text: string) => {
      const content = text.trim();
      if (!content || pending) return;

      const placeholder: ChatMessage = { id: newId('msg'), role: 'assistant', content: '', createdAt: nowIso(), status: 'pending' };
      setMessages((prev) => [...prev, { id: newId('msg'), role: 'user', content, createdAt: nowIso() }, placeholder]);
      setPending(true);
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const r = await auditor.preguntar(content, controller.signal);
        if (r.tipo === 'sql') {
          const supuestos = r.supuestos.length ? `\n\n**Supuestos:** ${r.supuestos.join(' · ')}` : '';
          patch(placeholder.id, {
            status: undefined,
            casoId: r.caso_id,
            content:
              r.total_filas === 0
                ? `La consulta no devolvió filas.${supuestos}`
                : `Encontré **${plural(r.total_filas, 'fila', 'filas')}**.${supuestos}`,
            consulta: {
              casoId: r.caso_id,
              sql: r.sql,
              supuestos: r.supuestos,
              totalFilas: r.total_filas,
              filas: r.filas,
              modelo: r.modelo,
              equipo: r.equipo,
            },
          });
        } else {
          // Aclaración o sin datos: es una respuesta válida, no un error.
          patch(placeholder.id, { status: 'aviso', casoId: r.caso_id, content: r.motivo });
        }
      } catch (err) {
        const aborted = (err as Error).name === 'AbortError';
        patch(placeholder.id, {
          status: 'error',
          content: aborted ? 'Petición cancelada.' : `No se pudo obtener respuesta: ${(err as Error).message}`,
        });
      } finally {
        abortRef.current = null;
        setPending(false);
      }
    },
    [pending],
  );

  const analizar = useCallback(
    async (messageId: string, casoId: string, titulo: string) => {
      patch(messageId, { analisis: { estado: 'corriendo' } });
      try {
        const r = await auditor.analizar(casoId);
        if (r.estado === 'bloqueado') {
          patch(messageId, { analisis: { estado: 'error', mensaje: r.motivo } });
          return;
        }
        const reporte: ReporteRef = { casoId, version: r.reporte.version, titulo };
        const partes = [
          plural(r.senales, 'señal', 'señales'),
          r.no_evaluables ? `${r.no_evaluables} no evaluable${r.no_evaluables === 1 ? '' : 's'}` : null,
          r.rag ? plural(r.normas, 'fragmento de norma', 'fragmentos de norma') : 'sin búsqueda normativa (no hay laptop disponible)',
        ].filter(Boolean);
        patch(messageId, { analisis: { estado: 'listo', reporte, resumen: partes.join(' · ') } });
        onReporte?.(reporte);
      } catch (err) {
        patch(messageId, { analisis: { estado: 'error', mensaje: (err as Error).message } });
      }
    },
    [onReporte],
  );

  const cancel = useCallback(() => abortRef.current?.abort(), []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
  }, []);

  return { messages, pending, send, analizar, cancel, reset };
}
