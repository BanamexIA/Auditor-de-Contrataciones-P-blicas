import { createContext, useContext, type Dispatch } from 'react';
import type { Tool } from '../../types/annotations';
import type { AnnotationsAction } from './annotationsReducer';

/** Estado compartido del editor que necesitan las páginas y las anotaciones. */
export interface EditorContextValue {
  tool: Tool;
  color: string;
  scale: number;
  selectedId: string | null;
  /** Anotación recién creada que debe recibir el foco para escribir. */
  focusId: string | null;
  select: (id: string | null) => void;
  clearFocus: () => void;
  dispatch: Dispatch<AnnotationsAction>;
  /** Crea anotaciones y deja el foco listo para escribir. */
  createAt: (page: number, x: number, y: number, kind: 'note' | 'text') => void;
  createEdit: (page: number, rect: { x: number; y: number; width: number; height: number }, text: string, fontSize: number) => void;
}

export const EditorContext = createContext<EditorContextValue | null>(null);

export function useEditor(): EditorContextValue {
  const ctx = useContext(EditorContext);
  if (!ctx) throw new Error('useEditor debe usarse dentro de <EditorContext.Provider>');
  return ctx;
}
