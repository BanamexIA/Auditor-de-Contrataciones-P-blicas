import type { LlmApi } from '../types';
import type { ChatResponse } from '../../types/chat';
import { newId, nowIso } from '../../lib/id';
import { mockStorePdf } from './mockDocumentsApi';
import { renderReportPdf, type ReportContent } from './reportGenerator';

/**
 * LLM simulado: responde con un texto breve y genera un informe PDF de ejemplo
 * a partir de la petición. Sirve para desarrollar el front sin backend.
 */
function wait(ms: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => {
      clearTimeout(t);
      reject(new DOMException('Cancelado', 'AbortError'));
    });
  });
}

function titleFrom(prompt: string): string {
  const clean = prompt.replace(/\s+/g, ' ').trim().replace(/[.?!¿¡]+$/g, '').replace(/^[¿¡]/, '');
  const short = clean.length > 70 ? `${clean.slice(0, 67).trimEnd()}…` : clean;
  return short.charAt(0).toUpperCase() + short.slice(1);
}

function buildContent(prompt: string, hasContext: boolean): ReportContent {
  const date = new Date().toLocaleDateString('es-MX', { dateStyle: 'long' });
  return {
    title: titleFrom(prompt),
    subtitle: `Generado el ${date} · Borrador automático (LLM simulado)`,
    sections: [
      {
        heading: '1. Resumen ejecutivo',
        paragraphs: [
          'Este documento resume el análisis solicitado. El contenido es un ejemplo producido por el ' +
            'modo de simulación del front-end; cuando el backend FastAPI esté conectado, este texto ' +
            'lo redactará el modelo de lenguaje y el PDF se guardará en S3.',
          hasContext
            ? 'Se tomó como contexto el documento que estaba abierto en el visor al momento de la petición.'
            : 'No se adjuntó ningún documento de contexto; el análisis parte únicamente de la petición.',
        ],
      },
      {
        heading: '2. Solicitud',
        paragraphs: [`“${prompt.trim()}”`],
      },
      {
        heading: '3. Análisis',
        paragraphs: [
          'Se identificaron los factores principales relacionados con la solicitud y se ordenaron según ' +
            'su impacto estimado. La información disponible permite establecer tendencias generales, ' +
            'aunque algunos datos deberán validarse con fuentes primarias antes de tomar decisiones.',
          'El escenario base supone condiciones similares a las del último periodo. Un escenario ' +
            'conservador reduce las estimaciones en un 15 %, mientras que el optimista las aumenta en un 10 %.',
        ],
      },
      {
        heading: '4. Hallazgos clave',
        bullets: [
          'La mayor parte del efecto se concentra en un número reducido de variables.',
          'Existen dependencias entre áreas que conviene revisar en conjunto.',
          'Los riesgos operativos son moderados y pueden mitigarse con controles simples.',
          'Hay oportunidades de mejora rápida con bajo costo de implementación.',
        ],
      },
      {
        heading: '5. Recomendaciones',
        bullets: [
          'Priorizar las acciones de mayor impacto y menor esfuerzo durante el primer mes.',
          'Definir indicadores de seguimiento y una revisión quincenal de resultados.',
          'Documentar supuestos y validar las cifras críticas con el área responsable.',
        ],
      },
      {
        heading: '6. Próximos pasos',
        paragraphs: [
          'Revise este informe en el visor: puede subrayar, añadir notas, insertar cuadros de texto y ' +
            'corregir fragmentos del documento. Los cambios se guardan como anotaciones y pueden ' +
            'exportarse a un PDF nuevo o subirse como nueva versión.',
        ],
      },
    ],
  };
}

let conversationCounter = 0;

export const mockLlmApi: LlmApi = {
  async sendMessage(request, signal): Promise<ChatResponse> {
    await wait(900 + Math.random() * 700, signal);
    const content = buildContent(request.message, Boolean(request.contextDocumentId));
    const bytes = await renderReportPdf(content);
    const fileName = `informe-${new Date().toISOString().slice(0, 10)}-${Date.now().toString(36)}.pdf`;
    const doc = mockStorePdf(bytes, content.title, fileName);
    const report = { documentId: doc.documentId, title: doc.title, fileName: doc.fileName };

    return {
      conversationId: request.conversationId ?? `conv_${++conversationCounter}`,
      report,
      message: {
        id: newId('msg'),
        role: 'assistant',
        createdAt: nowIso(),
        content:
          `Listo. Preparé el informe **${content.title}** con resumen ejecutivo, análisis, ` +
          'hallazgos clave y recomendaciones. Lo abrí en el visor de la derecha para que lo revises y anotes.',
        report,
      },
    };
  },
};
