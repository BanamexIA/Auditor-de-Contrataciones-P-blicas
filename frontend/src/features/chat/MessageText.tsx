import { Fragment } from 'react';

/** Markdown mínimo y seguro: párrafos, saltos de línea, **negritas** y `código`. */
export function MessageText({ text }: { text: string }) {
  return (
    <>
      {text.split(/\n{2,}/).map((para, i) => (
        <p key={i}>
          {para.split('\n').map((line, j) => (
            <Fragment key={j}>
              {j > 0 && <br />}
              {renderInline(line)}
            </Fragment>
          ))}
        </p>
      ))}
    </>
  );
}

function renderInline(line: string) {
  return line.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, k) => {
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={k}>{part.slice(2, -2)}</strong>;
    if (part.startsWith('`') && part.endsWith('`')) return <code key={k}>{part.slice(1, -1)}</code>;
    return <Fragment key={k}>{part}</Fragment>;
  });
}
