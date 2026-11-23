import { useState } from 'react';
import type { Fila } from '../../types/auditor';

/** Columnas que se muestran primero si vienen en la respuesta (el modelo a veces trae todas). */
const CLAVE = [
  'codigo_contrato', 'proveedor', 'institucion', 'siglas_de_la_institucion', 'importe', 'moneda',
  'fecha_inicio', 'tipo_procedimiento_norm', 'nivel_confianza', 'nombre_del_contribuyente',
];
const MAX_COLUMNAS = 6;
const FILAS_INICIALES = 8;

const dinero = new Intl.NumberFormat('es-MX', { maximumFractionDigits: 2 });

function celda(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'number') return dinero.format(v);
  if (typeof v === 'boolean') return v ? 'sí' : 'no';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

export function ResultTable({ filas, total }: { filas: Fila[]; total: number }) {
  const [todas, setTodas] = useState(false);
  const [masFilas, setMasFilas] = useState(false);
  if (filas.length === 0) return null;

  const disponibles = Object.keys(filas[0]);
  const ordenadas = [...CLAVE.filter((c) => disponibles.includes(c)), ...disponibles.filter((c) => !CLAVE.includes(c))];
  const columnas = todas ? ordenadas : ordenadas.slice(0, MAX_COLUMNAS);
  const visibles = masFilas ? filas : filas.slice(0, FILAS_INICIALES);

  return (
    <div className="result">
      <div className="result-scroll">
        <table>
          <thead>
            <tr>
              {columnas.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibles.map((f, i) => (
              <tr key={i}>
                {columnas.map((c) => (
                  <td key={c} className={typeof f[c] === 'number' ? 'num' : undefined}>
                    {celda(f[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="result-meta">
        <span>
          {visibles.length} de {total} fila{total === 1 ? '' : 's'}
          {total > filas.length ? ` (la API entrega hasta ${filas.length})` : ''}
        </span>
        {filas.length > FILAS_INICIALES && (
          <button className="link" onClick={() => setMasFilas((v) => !v)}>
            {masFilas ? 'Menos filas' : 'Todas las filas'}
          </button>
        )}
        {ordenadas.length > MAX_COLUMNAS && (
          <button className="link" onClick={() => setTodas((v) => !v)}>
            {todas ? 'Columnas clave' : `Las ${ordenadas.length} columnas`}
          </button>
        )}
      </div>
    </div>
  );
}
