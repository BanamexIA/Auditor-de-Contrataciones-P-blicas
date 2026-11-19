import { apiRequest } from '../httpClient';
import { toChatResponse, type ChatRequestDTO, type ChatResponseDTO } from '../contracts';
import type { LlmApi } from '../types';

export const httpLlmApi: LlmApi = {
  async sendMessage(request, signal) {
    const body: ChatRequestDTO = {
      conversation_id: request.conversationId,
      message: request.message,
      history: request.history,
      context_document_id: request.contextDocumentId,
    };
    const dto = await apiRequest<ChatResponseDTO>('/chat', { method: 'POST', body, signal });
    return toChatResponse(dto);
  },
};
