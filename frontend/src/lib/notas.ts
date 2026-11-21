import type { Annotation } from '../types/annotations';

/**
 * Notas personales del auditor sobre un reporte (resaltados, notas, cuadros de texto).
 *
 * Se guardan en el navegador, aparte del reporte: el PDF oficial es inmutable (tiene SHA-256 y
 * pasó el verificador de citas), así que las marcas nunca se suben como una versión nueva.
 * Las decisiones que cuentan para el caso se registran en la pestaña Señales.
 */
const clave = (casoId: string, version: number) => `auditor.notas.${casoId}.v${version}`;

export function leerNotas(casoId: string, version: number): Annotation[] {
  try {
    const crudo = localStorage.getItem(clave(casoId, version));
    const datos = crudo ? JSON.parse(crudo) : [];
    return Array.isArray(datos) ? datos : [];
  } catch {
    return [];
  }
}

export function guardarNotas(casoId: string, version: number, notas: Annotation[]): void {
  try {
    localStorage.setItem(clave(casoId, version), JSON.stringify(notas));
  } catch {
    throw new Error('El navegador no permite guardar las notas.');
  }
}
