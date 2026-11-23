import * as pdfjs from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

export { pdfjs };
export type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist';

export interface PageSize {
  width: number;
  height: number;
}

export async function loadPdf(bytes: Uint8Array) {
  // pdf.js transfiere el buffer al worker; se le pasa una copia.
  const pdf = await pdfjs.getDocument({ data: bytes.slice() }).promise;
  const sizes: PageSize[] = [];
  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i);
    const vp = page.getViewport({ scale: 1 });
    sizes.push({ width: vp.width, height: vp.height });
  }
  return { pdf, sizes };
}
