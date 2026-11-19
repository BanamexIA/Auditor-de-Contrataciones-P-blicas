import { useCallback, useRef, useState } from 'react';
import { llmApi } from '../../api';
import type { ChatMessage, ReportRef } from '../../types/chat';
import { newId, nowIso } from '../../lib/id';

interface UseChatOptions {
  onReport?: (report: ReportRef) => void;
}

export function useChat({ onReport }: UseChatOptions = {}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState(false);
  const conversationId = useRef<string | undefined>(undefined);
  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(
    async (text: string, contextDocumentId?: string) => {
      const content = text.trim();
      if (!content || pending) return;

      const userMsg: ChatMessage = { id: newId('msg'), role: 'user', content, createdAt: nowIso() };
      const placeholder: ChatMessage = {
        id: newId('msg'),
        role: 'assistant',
        content: '',
        createdAt: nowIso(),
        status: 'pending',
      };
      // El historial va sin los mensajes fallidos ni el que se está esperando.
      const history = messages
        .filter((m) => !m.status)
        .map(({ role, content: c }) => ({ role, content: c }));

      setMessages((prev) => [...prev, userMsg, placeholder]);
      setPending(true);
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const res = await llmApi.sendMessage(
          { conversationId: conversationId.current, message: content, history, contextDocumentId },
          controller.signal,
        );
        conversationId.current = res.conversationId;
        setMessages((prev) => prev.map((m) => (m.id === placeholder.id ? res.message : m)));
        if (res.report) onReport?.(res.report);
      } catch (err) {
        const aborted = (err as Error).name === 'AbortError';
        setMessages((prev) =>
          prev.map((m) =>
            m.id === placeholder.id
              ? {
                  ...m,
                  status: 'error',
                  content: aborted ? 'Petición cancelada.' : `No se pudo obtener respuesta: ${(err as Error).message}`,
                }
              : m,
          ),
        );
      } finally {
        abortRef.current = null;
        setPending(false);
      }
    },
    [messages, pending, onReport],
  );

  const cancel = useCallback(() => abortRef.current?.abort(), []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    conversationId.current = undefined;
    setMessages([]);
  }, []);

  return { messages, pending, send, cancel, reset };
}
