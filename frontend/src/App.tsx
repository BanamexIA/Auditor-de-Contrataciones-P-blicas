import { useCallback, useState } from 'react';
import { SplitPane } from './components/SplitPane';
import { ChatPanel } from './features/chat/ChatPanel';
import { PdfWorkspace } from './features/pdf/PdfWorkspace';
import { config } from './config';
import type { ReportRef } from './types/chat';
import type { DocumentInfo } from './types/documents';

export default function App() {
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [docInfo, setDocInfo] = useState<DocumentInfo | null>(null);

  const openReport = useCallback((report: ReportRef) => setDocumentId(report.documentId), []);

  return (
    <div className="app">
      {config.useMock && (
        <div className="mock-banner" role="status">
          Modo simulación: el LLM y el almacenamiento S3 son ficticios y viven en el navegador. Configura{' '}
          <code>VITE_USE_MOCK=false</code> para usar el backend FastAPI.
        </div>
      )}
      <SplitPane
        left={<ChatPanel activeDocumentId={documentId ?? undefined} activeDocumentTitle={docInfo?.title} onOpenReport={openReport} />}
        right={<PdfWorkspace documentId={documentId} onDocumentInfo={setDocInfo} onOpenDocument={setDocumentId} />}
      />
    </div>
  );
}
