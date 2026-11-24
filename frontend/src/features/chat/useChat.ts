import { useCallback, useRef, useState } from 'react';
import { auditor } from '../../api/auditor';
import type { EstadoCaso, EventoBitacora, ReporteRef } from '../../types/auditor';
import type { ChatMessage, ResultadoConsulta } from '../../types/chat';
import { newId, nowIso } from '../../lib/id';

interface UseChatOptions {
  onReporte?: (reporte: ReporteRef) => void;
}

const CADA_MS = 2500;
/** El orquestador tiene su propio límite (ORQ_TIEMPO_MAX_S); esto solo evita seguir para siempre. */
const SEGUIR_MAX_MS = 30 * 60 * 1000;
const FINALES: EstadoCaso[] = ['en_revision', 'bloqueado', 'cerrado'];

const plural = (n: number, uno: string, varios: string) => `${n} ${n === 1 ? uno : varios}`;
const esperar = (ms: number, signal: AbortSignal) =>
  new Promise<void>((ok, mal) => {
    const t = window.setTimeout(ok, ms);
    signal.addEventListener('abort', () => {
      window.clearTimeout(t);
      mal(new DOMException('cancelado', 'AbortError'));
    });
  });

/** Lo que dice la bitácora sobre señales y normas, para el resumen de la respuesta. */
function resumenDe(eventos: EventoBitacora[]): string | undefined {
  const ultimo = (tipo: string) => [...eventos].reverse().find((e) => e.evento === tipo)?.detalle;
  const reglas = ultimo('reglas_evaluadas');
  const normas = ultimo('normas_recuperadas');
  const partes: string[] = [];
  if (reglas) partes.push(plural(Number(reglas.senales ?? 0), 'señal', 'señales'));
  if (reglas && Number(reglas.no_evaluables)) partes.push(`${reglas.no_evaluables} no evaluable(s)`);
  if (normas)
    partes.push(
      normas.rag === false
        ? 'sin búsqueda normativa (no hay laptop para el RAG)'
        : plural(Array.isArray(normas.normas) ? normas.normas.length : 0, 'fragmento de norma', 'fragmentos de norma'),
    );
  return partes.length ? partes.join(' · ') : undefined;
}

export function useChat({ onReporte }: UseChatOptions = {}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const patch = (id: string, cambios: Partial<ChatMessage>) =>
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...cambios } : m)));

  /** Tabla y SQL de la consulta (una sola vez, en cuanto el caso pasa de 'consultado'). */
  const cargarConsulta = async (casoId: string, eventos: EventoBitacora[]): Promise<ResultadoConsulta | undefined> => {
    try {
      const r = await auditor.resultados(casoId);
      const llamada = eventos.find((e) => e.evento === 'llamada_llm');
      return {
        casoId,
        sql: r.sql,
        supuestos: r.supuestos,
        totalFilas: r.total_filas,
        filas: r.filas,
        modelo: llamada?.modelo ?? null,
        equipo: llamada?.equipo ?? null,
      };
    } catch {
      return undefined; // la tabla es un extra: si falla, el caso sigue mostrándose
    }
  };

  const send = useCallback(
    async (text: string) => {
      const content = text.trim();
      if (!content || pending) return;

      const msgId = newId('msg');
      setMessages((prev) => [
        ...prev,
        { id: newId('msg'), role: 'user', content, createdAt: nowIso() },
        { id: msgId, role: 'assistant', content: '', createdAt: nowIso(), status: 'pending', progreso: { estado: 'recibido', segundos: 0 } },
      ]);
      setPending(true);
      const controller = new AbortController();
      abortRef.current = controller;
      const inicio = Date.now();
      let casoId: string | undefined;

      try {
        casoId = (await auditor.crearCaso(content)).id;
        patch(msgId, { casoId });
        await auditor.orquestar(casoId, false);

        let consulta: ResultadoConsulta | undefined;
        for (;;) {
          await esperar(CADA_MS, controller.signal);
          const [caso, eventos] = await Promise.all([auditor.caso(casoId), auditor.bitacora(casoId)]);
          const avanzoConsulta = caso.estado !== 'recibido' && !(caso.estado === 'bloqueado' && caso.estado_previo === 'recibido');
          if (!consulta && avanzoConsulta && eventos.some((e) => e.evento === 'sql_ejecutado')) {
            consulta = await cargarConsulta(casoId, eventos);
          }
          const segundos = Math.round((Date.now() - inicio) / 1000);
          patch(msgId, { progreso: { estado: caso.estado, segundos, resumen: resumenDe(eventos) }, consulta });

          if (caso.estado === 'bloqueado') {
            patch(msgId, { status: 'aviso', progreso: undefined, content: caso.motivo_bloqueo ?? 'El caso quedó bloqueado.' });
            return;
          }
          if (FINALES.includes(caso.estado)) {
            const versiones = await auditor.reportes(casoId);
            const version = Math.max(...versiones.map((r) => r.version));
            const resumen = resumenDe(eventos) ?? '';
            const ref: ReporteRef = { casoId, version, titulo: content };
            const filas = consulta?.totalFilas;
            patch(msgId, {
              status: undefined,
              progreso: undefined,
              content: `${filas != null ? `Revisé **${plural(filas, 'fila', 'filas')}**. ` : ''}El caso está listo para tu revisión.`,
              reporte: Number.isFinite(version) ? { ref, resumen } : undefined,
            });
            if (Number.isFinite(version)) onReporte?.(ref);
            return;
          }
          if (Date.now() - inicio > SEGUIR_MAX_MS) {
            patch(msgId, { status: 'aviso', progreso: undefined, content: 'El caso sigue en proceso. Revísalo más tarde con su número de caso.' });
            return;
          }
        }
      } catch (err) {
        const aborted = (err as Error).name === 'AbortError';
        patch(msgId, {
          status: aborted ? 'aviso' : 'error',
          progreso: undefined,
          content: aborted
            ? 'Dejaste de seguir este caso; el orquestador continúa en el servidor.'
            : `No se pudo procesar la pregunta: ${(err as Error).message}`,
        });
      } finally {
        abortRef.current = null;
        setPending(false);
      }
    },
    [pending, onReporte],
  );

  const cancel = useCallback(() => abortRef.current?.abort(), []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
  }, []);

  return { messages, pending, send, cancel, reset };
}
