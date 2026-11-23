/**
 * Las anotaciones se guardan en coordenadas de la página a escala 1
 * (puntos PDF, origen arriba a la izquierda). Así no dependen del zoom
 * y el backend puede guardarlas tal cual como JSON.
 */
export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface AnnotationBase {
  id: string;
  /** Página, empezando en 1. */
  page: number;
  createdAt: string;
  updatedAt: string;
}

export type MarkupKind = 'highlight' | 'underline' | 'strike';

export interface MarkupAnnotation extends AnnotationBase {
  type: MarkupKind;
  rects: Rect[];
  color: string;
  /** Texto que quedó marcado. */
  text: string;
  comment: string;
}

export interface NoteAnnotation extends AnnotationBase {
  type: 'note';
  x: number;
  y: number;
  text: string;
  color: string;
}

export interface TextBoxAnnotation extends AnnotationBase {
  type: 'text';
  rect: Rect;
  text: string;
  fontSize: number;
  color: string;
}

/** Reemplazo de un fragmento de texto del PDF: tapa el original y escribe el nuevo. */
export interface TextEditAnnotation extends AnnotationBase {
  type: 'edit';
  rect: Rect;
  originalText: string;
  text: string;
  fontSize: number;
  color: string;
}

export type Annotation =
  | MarkupAnnotation
  | NoteAnnotation
  | TextBoxAnnotation
  | TextEditAnnotation;

export type AnnotationType = Annotation['type'];

export type Tool = 'select' | MarkupKind | 'note' | 'text' | 'edit';
