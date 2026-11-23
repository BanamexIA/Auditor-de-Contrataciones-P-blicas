import type {
  Annotation,
  MarkupAnnotation,
  NoteAnnotation,
  TextBoxAnnotation,
  TextEditAnnotation,
} from '../../types/annotations';
import { nowIso } from '../../lib/id';

type Fields<T> = Omit<T, 'type' | 'id' | 'page' | 'createdAt'>;
export type AnnotationPatch = Partial<
  Fields<MarkupAnnotation> & Fields<NoteAnnotation> & Fields<TextBoxAnnotation> & Fields<TextEditAnnotation>
>;

export interface AnnotationsState {
  items: Annotation[];
  past: Annotation[][];
  future: Annotation[][];
  /** Agrupa cambios seguidos (escribir, arrastrar) en un solo paso de deshacer. */
  lastKey?: string;
  /** Se incrementa con cada cambio; sirve para el guardado automático. */
  revision: number;
}

export type AnnotationsAction =
  | { type: 'load'; items: Annotation[] }
  | { type: 'add'; item: Annotation }
  | { type: 'update'; id: string; patch: AnnotationPatch; coalesceKey?: string }
  | { type: 'remove'; id: string }
  | { type: 'undo' }
  | { type: 'redo' };

const HISTORY_LIMIT = 100;

export const initialAnnotationsState: AnnotationsState = { items: [], past: [], future: [], revision: 0 };

function commit(state: AnnotationsState, items: Annotation[], key?: string): AnnotationsState {
  const coalesce = key !== undefined && key === state.lastKey;
  return {
    items,
    past: coalesce ? state.past : [...state.past, state.items].slice(-HISTORY_LIMIT),
    future: [],
    lastKey: key,
    revision: state.revision + 1,
  };
}

export function annotationsReducer(state: AnnotationsState, action: AnnotationsAction): AnnotationsState {
  switch (action.type) {
    case 'load':
      return { ...initialAnnotationsState, items: action.items };
    case 'add':
      return commit(state, [...state.items, action.item]);
    case 'update': {
      if (!state.items.some((a) => a.id === action.id)) return state;
      const items = state.items.map((a) =>
        a.id === action.id ? ({ ...a, ...action.patch, updatedAt: nowIso() } as Annotation) : a,
      );
      return commit(state, items, action.coalesceKey);
    }
    case 'remove':
      if (!state.items.some((a) => a.id === action.id)) return state;
      return commit(
        state,
        state.items.filter((a) => a.id !== action.id),
      );
    case 'undo': {
      if (state.past.length === 0) return state;
      const previous = state.past[state.past.length - 1];
      return {
        items: previous,
        past: state.past.slice(0, -1),
        future: [state.items, ...state.future],
        revision: state.revision + 1,
      };
    }
    case 'redo': {
      if (state.future.length === 0) return state;
      const [next, ...rest] = state.future;
      return {
        items: next,
        past: [...state.past, state.items],
        future: rest,
        revision: state.revision + 1,
      };
    }
  }
}
