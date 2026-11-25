"""D2 (Aarón) · Convierte el PDF de una ley en fragmentos por artículo, listos para `python -m rag.cli ingest`.

El texto es literal (solo se quitan encabezados y pies de página repetidos y se unen las líneas cortadas de un párrafo).
Cada artículo es un fragmento; si pasa de --max-chars se parte entre párrafos (metadata.parte = "2/3"). Se corta antes del primer
apartado de TRANSITORIOS: los transitorios del decreto y de las reformas no se cargan porque no son artículos de la ley.

    python -m rag.chunk_normas --pdf rag/LAASSP.pdf --ley LAASSP --titulo "Ley de Adquisiciones… (Nueva Ley DOF 16-04-2025)" \\
        --version "Nueva Ley DOF 16-04-2025" --publicacion 2025-04-16 --vigor 2025-04-17 \\
        --url https://www.diputados.gob.mx/LeyesBiblio/pdf/LAASSP.pdf --archivo-local rag/LAASSP.pdf --salida rag/samples/laassp_vigente.jsonl

Requiere `pdftotext` (poppler). Al terminar imprime un control de calidad: artículos encontrados, saltos o repetidos en la
numeración y fragmentos muy largos. Revisa ese control y el texto antes de usarlo como criterio legal.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ARTICULO = re.compile(
    r"^\s*(Art[ií]culo\s+(\d+)(?:\s*(?:o\.|º|°))?(?:-[A-Z]{1,2})?(?:\s+(Bis|Ter|Qu[aá]ter|Quinquies|Sexies|Septies|Octies|Nonies|Decies))?"
    r"(?:\s+[A-Z])?)\s*[.\-–]+\s*(.*)$")   # 69-B (CFF), 2 Bis, 17 A
TRANSITORIOS = re.compile(r"^\s*(ART[ÍI]CULOS\s+)?TRANSITORIOS?\s*$", re.IGNORECASE)
TITULO = re.compile(r"^\s*(T[ÍI]TULO|Cap[ií]tulo|Secci[oó]n)\s+(\S+(?:\s+\S+)?)\s*$", re.IGNORECASE)
PAGINA = re.compile(r"^\s*(P[áa]gina\s+)?\d+(\s+de\s+\d+)?\s*$", re.IGNORECASE)


def texto_por_paginas(pdf: Path) -> list[list[str]]:
    out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    return [p.splitlines() for p in out.split("\f") if p.strip()]


def quitar_encabezados(paginas: list[list[str]], minimo: float = 0.4) -> list[list[str]]:
    """Líneas cortas que se repiten en al menos `minimo` de las páginas (encabezados y pies) y números de página."""
    norm = lambda l: re.sub(r"\s+", " ", l).strip()
    cuenta = Counter(l for p in paginas for l in {norm(x) for x in p if x.strip()})
    repetidas = {l for l, n in cuenta.items() if n >= max(3, minimo * len(paginas)) and len(l) <= 120}
    return [[l for l in p if norm(l) not in repetidas and not PAGINA.match(l)] for p in paginas]


def _sangria(l: str) -> int:
    return len(l) - len(l.lstrip())


def unir_parrafos(lineas: list[str]) -> list[str]:
    """pdftotext deja los párrafos con sangría y sus renglones sin ella: se une cada párrafo en una línea."""
    parrafos: list[str] = []
    for l in lineas:
        if not l.strip():
            continue
        if _sangria(l) >= 2 or not parrafos:
            parrafos.append(l.strip())
        else:
            parrafos[-1] += " " + l.strip()
    return parrafos


def partir(parrafos: list[str], max_chars: int) -> list[str]:
    partes, actual = [], ""
    for p in parrafos:
        if actual and len(actual) + len(p) + 1 > max_chars:
            partes.append(actual)
            actual = ""
        actual = f"{actual}\n{p}" if actual else p
    if actual:
        partes.append(actual)
    return partes


def extraer_articulos(paginas: list[list[str]]) -> tuple[list[dict], bool]:
    """Devuelve ([{articulo, pagina, ruta, lineas}], corto_en_transitorios)."""
    arts, actual, ruta, corto = [], None, [], False
    for n, lineas in enumerate(paginas, start=1):
        for l in lineas:
            if TRANSITORIOS.match(l) and arts:
                corto = True
                break
            m = ARTICULO.match(l)
            if m and (_sangria(l) >= 1 or actual is None):
                etiqueta = re.sub(r"\s+", " ", m.group(1)).replace("Articulo", "Artículo")
                actual = {"articulo": etiqueta, "numero": int(m.group(2)), "pagina": n, "ruta": " > ".join(ruta),
                          "lineas": [" " * 4 + m.group(4)] if m.group(4) else []}
                arts.append(actual)
                continue
            t = TITULO.match(l)
            if t and _sangria(l) >= 10:                       # encabezados centrados
                nivel = {"t": 0, "c": 1, "s": 2}[t.group(1)[0].lower()]      # título > capítulo > sección
                ruta = ruta[:nivel] + [f"{t.group(1).capitalize()} {t.group(2)}"]
                continue
            if actual is not None:
                actual["lineas"].append(l)
        if corto:
            break
    return arts, corto


def revisar(arts: list[dict], max_chars: int) -> list[str]:
    """Control de calidad de la numeración: avisa de repetidos, saltos y retrocesos."""
    avisos, previo = [], None
    for a in arts:
        n = a["numero"]
        if previo is not None and n < previo:
            avisos.append(f"{a['articulo']} (pág. {a['pagina']}) retrocede después del {previo}")
        elif previo is not None and n > previo + 1:
            avisos.append(f"salto de {previo} a {n} (pág. {a['pagina']})")
        previo = n if previo is None or n >= previo else previo
    repetidos = [k for k, c in Counter(a["articulo"] for a in arts).items() if c > 1]
    avisos += [f"{k} aparece más de una vez" for k in repetidos]
    return avisos


def construir(pdf: Path, ley: str, titulo: str, version: str, publicacion: str, vigor: str, abrogacion: str | None,
              url: str, archivo_local: str | None, max_chars: int = 1800, fuente: str = "Cámara de Diputados",
              solo_articulos: set | None = None):
    paginas = quitar_encabezados(texto_por_paginas(pdf))
    arts, corto = extraer_articulos(paginas)
    avisos = revisar(arts, max_chars)
    if solo_articulos:
        faltan = sorted(solo_articulos - {a["articulo"] for a in arts})
        if faltan:
            raise SystemExit(f"No se encontraron en el PDF: {', '.join(faltan)}")
        arts = [a for a in arts if a["articulo"] in solo_articulos]
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    doc = {"ley": ley, "version": version, "fecha_publicacion_dof": publicacion, "fecha_entrada_vigor": vigor,
           "fecha_abrogacion": abrogacion, "sha256": sha, "archivo_local": archivo_local or str(pdf)}
    registros, pos = [], 0
    for a in arts:
        parrafos = unir_parrafos(a["lineas"])
        if not parrafos:
            continue
        partes = partir(parrafos, max_chars)
        for i, texto in enumerate(partes, start=1):
            meta = {"articulo": a["articulo"], "pagina": a["pagina"]}
            if a["ruta"]:
                meta["ruta_normativa"] = a["ruta"]
            if len(partes) > 1:
                meta["parte"] = f"{i}/{len(partes)}"
            registros.append({"fuente": fuente, "tipo": "normas", "titulo": titulo, "url_o_ruta": url, "posicion": pos,
                              "contenido": texto, "document_metadata": doc, "metadata": meta})
            pos += 1
    qa = {"solo_articulos": sorted(solo_articulos) if solo_articulos else None, "articulos": len({a['articulo'] for a in arts}), "fragmentos": len(registros), "paginas": len(paginas),
          "se_corto_en_transitorios": corto, "avisos_numeracion": revisar(arts, max_chars),
          "fragmentos_mas_largos_que_max": sum(len(r["contenido"]) > max_chars for r in registros),
          "articulos_sin_texto": sorted({a["articulo"] for a in arts if not unir_parrafos(a["lineas"])})}
    return registros, qa


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", required=True, type=Path)
    ap.add_argument("--ley", required=True)
    ap.add_argument("--titulo", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--publicacion", required=True, help="fecha de publicación en el DOF, AAAA-MM-DD")
    ap.add_argument("--vigor", required=True, help="fecha de entrada en vigor, AAAA-MM-DD")
    ap.add_argument("--abrogacion", help="fecha de abrogación (exclusiva), AAAA-MM-DD; vacío si sigue vigente")
    ap.add_argument("--url", required=True, help="URL oficial (Cámara de Diputados o DOF)")
    ap.add_argument("--archivo-local")
    ap.add_argument("--max-chars", type=int, default=1800)
    ap.add_argument("--solo-articulos", help="lista separada por comas (p. ej. '69,69-A,69-B'); útil para leyes enormes como el CFF")
    ap.add_argument("--salida", required=True, type=Path)
    a = ap.parse_args(argv)
    solo = {f"Artículo {x.strip()}" for x in a.solo_articulos.split(",")} if a.solo_articulos else None
    registros, qa = construir(a.pdf, a.ley, a.titulo, a.version, a.publicacion, a.vigor, a.abrogacion, a.url,
                              a.archivo_local, a.max_chars, solo_articulos=solo)
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in registros), encoding="utf-8")
    print(json.dumps(qa, ensure_ascii=False, indent=2))
    print(f"-> {a.salida}", file=sys.stderr)
    return 0 if registros else 1


if __name__ == "__main__":
    raise SystemExit(main())
