#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Iterable

try:
    import psycopg
except Exception:  # pragma: no cover - optional dependency
    psycopg = None


OUTPUT_HEADERS = {
    "contratos_comprasmx": [
        "codigo_contrato",
        "codigo_expediente",
        "proveedor",
        "titulo_contrato",
        "descripcion_contrato",
        "contract_type",
        "tipo_contratacion",
        "tipo_expediente",
        "importe",
        "moneda",
        "fecha_inicio",
        "fecha_fin",
    ],
    "listado_69b": [
        "rfc",
        "nombre_del_contribuyente",
        "situacion_del_contribuyente",
    ],
}


def normalize_identifier(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", normalized.strip())
    clean = clean.strip("_")
    return clean.lower() or "col"


def normalize_text(value: str) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip()
    return re.sub(r"\s+", " ", text)


def mapped_value(record: dict[str, str], *names: str) -> str:
    for name in names:
        value = record.get(name, "").strip()
        if value:
            return value
    return ""


def detect_best_encoding(path: Path) -> str:
    data = path.read_bytes()
    encodings = ["utf-8-sig", "utf-8", "cp1252", "latin-1", "iso-8859-1"]
    for encoding in encodings:
        try:
            data.decode(encoding)
            return encoding
        except (UnicodeDecodeError, ValueError):
            continue
    return "latin-1"


def detect_delimiter(path: Path, encoding: str) -> str:
    delimiters = [",", ";", "\t", "|"]
    tokens = {
        "codigo_contrato",
        "codigo_expediente",
        "proveedor",
        "rfc",
        "situacion_del_contribuyente",
        "nombre_del_contribuyente",
        "importe",
        "moneda",
    }
    best = ","
    best_score = -1
    for delimiter in delimiters:
        score = 0
        with path.open("r", encoding=encoding, newline="") as handle:
            for row in csv.reader(handle, delimiter=delimiter):
                if not row or all(not cell.strip() for cell in row):
                    continue
                norm = [normalize_identifier(cell) for cell in row]
                score += sum(10 for token in tokens if token in norm)
                if score > 0:
                    break
        if score > best_score:
            best_score = score
            best = delimiter
    return best


def iter_csv_rows(path: Path) -> list[list[str]]:
    encoding = detect_best_encoding(path)
    delim = detect_delimiter(path, encoding)
    rows: list[list[str]] = []
    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle, delimiter=delim)
        for row in reader:
            if not row or all(not cell.strip() for cell in row):
                continue
            rows.append([cell.strip() for cell in row])
    return rows


def find_header_row(rows: list[list[str]], table_kind: str) -> list[str]:
    candidates = {
        "contratos_comprasmx": [
            "codigo_contrato",
            "codigo_expediente",
            "proveedor",
            "titulo_contrato",
            "importe",
            "moneda",
            "fecha_inicio",
            "fecha_fin",
        ],
        "listado_69b": ["rfc", "nombre_del_contribuyente", "situacion_del_contribuyente", "no"],
    }
    for row in rows:
        norm = [normalize_identifier(cell) for cell in row]
        if any(token in norm for token in candidates[table_kind]):
            return row
    return rows[0]


def build_rows_from_csv(path: Path, kind: str) -> tuple[list[str], list[dict[str, str]]]:
    raw_rows = iter_csv_rows(path)
    header = find_header_row(raw_rows, kind)
    start_index = next((idx for idx, row in enumerate(raw_rows) if row == header), 0)
    data_rows = raw_rows[start_index + 1:]
    normalized_header = [normalize_identifier(cell) for cell in header]
    records: list[dict[str, str]] = []
    for row in data_rows:
        if len(row) < len(normalized_header):
            row = row + [""] * (len(normalized_header) - len(row))
        if len(row) > len(normalized_header):
            row = row[: len(normalized_header)]
        mapping = {normalized_header[i]: row[i] for i in range(len(normalized_header))}
        records.append(mapping)
    return normalized_header, records


def iter_csv_records(path: Path, kind: str):
    encoding = detect_best_encoding(path)
    delimiter = detect_delimiter(path, encoding)
    header = None
    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        for row in reader:
            if not row or all(not cell.strip() for cell in row):
                continue
            if header is None:
                if kind == "listado_69b":
                    header = [normalize_identifier(cell) for cell in row]
                else:
                    header = [normalize_identifier(cell) for cell in row]
                continue
            if len(row) < len(header):
                row = row + [""] * (len(header) - len(row))
            if len(row) > len(header):
                row = row[: len(header)]
            yield {header[idx]: row[idx] for idx in range(len(header))}


def percent_missing(values: Iterable[str]) -> float:
    vals = list(values)
    if not vals:
        return 0.0
    missing = sum(1 for v in vals if v is None or str(v).strip() == "")
    return round((missing / len(vals)) * 100, 2)


def cardinality(values: Iterable[str]) -> int:
    return len({str(v).strip() for v in values if str(v).strip()})


def parse_decimal(value: str) -> float | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("$", "").replace(",", "")
    s = s.replace("(", "-").replace(")", "")
    s = s.replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return None


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    index = max(0, min(len(values) - 1, int(math.ceil((pct / 100) * len(values)) - 1)))
    return values[index]


def normalize_provider(value: str) -> str:
    text = normalize_text(value).upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("&", " Y ")
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    text = re.sub(r"\b(S\.?A\.?|SOCIEDAD ANONIMA|S\.? DE R\.?L\.?|S\.? DE C\.?V\.?|DE C\.?V\.?|SA DE CV|S\.R\.?L\.?|S\.?C\.?|SC|SRL)\b", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_date(value: str) -> datetime | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    patterns = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%d.%m.%Y",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    ]
    for pattern in patterns:
        try:
            return datetime.strptime(s, pattern)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        pass
    return None


def rfc_is_valid(rfc: str) -> bool:
    text = str(rfc or "").strip().upper()
    if not text:
        return False
    if len(text) not in (12, 13):
        return False
    if not re.fullmatch(r"[A-Z&Ñ]+[0-9]{6}[A-Z0-9]{3}", text) and not re.fullmatch(r"[A-Z&Ñ]+[0-9]{6}[A-Z0-9]{3}[A-Z0-9]", text):
        return False
    return True


def analyze_contracts(file_path: Path) -> dict:
    encoding = detect_best_encoding(file_path)
    delimiter = detect_delimiter(file_path, encoding)
    columns: list[str] | None = None
    rows_seen = 0
    missing_counts: dict[str, int] = defaultdict(int)
    seen_values: dict[str, set[str]] = defaultdict(set)
    contrato_counts: Counter[str] = Counter()
    expediente_counts: Counter[str] = Counter()
    importe_values: list[float] = []
    non_numeric_importes = 0
    zero_importes = 0
    negative_importes = 0
    moneda_counter: Counter[str] = Counter()
    parsed_date_values: set[str] = set()
    start_years: Counter[str] = Counter()
    empty_dates = 0
    invalid_dates = 0
    fecha_fin_menor_inicio = 0
    outside_date_range = 0
    provider_variants: Counter[str] = Counter()
    categorical_counter: dict[str, Counter[str]] = defaultdict(Counter)

    with file_path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        for row in reader:
            if not row or all(not cell.strip() for cell in row):
                continue
            if columns is None:
                columns = [normalize_identifier(cell) for cell in row]
                continue
            rows_seen += 1
            if len(row) < len(columns):
                row = row + [""] * (len(columns) - len(row))
            if len(row) > len(columns):
                row = row[: len(columns)]
            record = {columns[idx]: row[idx].strip() for idx in range(len(columns))}
            for col in columns:
                value = record.get(col, "")
                if value == "":
                    missing_counts[col] += 1
                else:
                    seen_values[col].add(value)
            codigo = mapped_value(record, "codigo_contrato", "codigo_del_contrato")
            if codigo:
                contrato_counts[codigo] += 1
            expediente = mapped_value(record, "codigo_expediente", "codigo_del_expediente")
            if expediente:
                expediente_counts[expediente] += 1
            importe_raw = mapped_value(record, "importe", "importe_drc")
            importe_value = parse_decimal(importe_raw)
            if importe_raw:
                if importe_value is None:
                    non_numeric_importes += 1
                else:
                    importe_values.append(importe_value)
                    if importe_value == 0:
                        zero_importes += 1
                    if importe_value < 0:
                        negative_importes += 1
            moneda = mapped_value(record, "moneda", "moneda_1")
            if moneda:
                moneda_counter[moneda] += 1
            start_text = mapped_value(
                record, "fecha_inicio", "fecha_de_inicio_del_contrato", "fecha_de_inicio"
            )
            end_text = mapped_value(
                record, "fecha_fin", "fecha_de_fin_del_contrato", "fecha_de_fin"
            )
            parsed_dates = {}
            for field_name, value in (("fecha_inicio", start_text), ("fecha_fin", end_text)):
                if not value or value.casefold() == "sin dato":
                    empty_dates += 1
                    parsed_dates[field_name] = None
                    continue
                parsed = parse_date(value)
                parsed_dates[field_name] = parsed
                if parsed is None:
                    invalid_dates += 1
                else:
                    parsed_date_values.add(parsed.strftime("%Y-%m-%d"))
                    if field_name == "fecha_inicio":
                        start_years[str(parsed.year)] += 1
            start_dt = parsed_dates["fecha_inicio"]
            end_dt = parsed_dates["fecha_fin"]
            if start_dt and end_dt and end_dt < start_dt:
                fecha_fin_menor_inicio += 1
            if start_dt and not 2010 <= start_dt.year <= 2026:
                outside_date_range += 1
            proveedor = mapped_value(record, "proveedor", "proveedor_o_contratista")
            if proveedor:
                provider_variants[normalize_provider(proveedor)] += 1
            categorical_fields = (
                ("tipo_contratacion", "tipo_de_contratacion"),
                ("tipo_expediente", "tipo_de_expediente"),
                ("tipo_procedimiento",),
                ("contract_type", "tipo_de_contrato"),
                ("moneda", "moneda_1"),
            )
            for aliases in categorical_fields:
                value = mapped_value(record, *aliases)
                if value:
                    categorical_counter[aliases[0]][value] += 1

    if columns is None:
        return {"columns": [], "rows": 0, "metrics": {}}

    metrics = {
        "total_rows": rows_seen,
        "total_columns": len(columns),
        "file_size_bytes": file_path.stat().st_size,
        "nulls_by_column": {col: round((missing_counts.get(col, 0) / rows_seen) * 100, 2) if rows_seen else 0.0 for col in columns},
        "cardinality_by_column": {col: len(seen_values.get(col, set())) for col in columns},
        "duplicates_codigo_contrato": sum(1 for count in contrato_counts.values() if count > 1),
        "duplicates_codigo_expediente": sum(1 for count in expediente_counts.values() if count > 1),
        "importe": {},
        "moneda": dict(moneda_counter.most_common(10)),
        "date_issues": {
            "distinct_parseable_dates": len(parsed_date_values),
            "nula_o_sin_dato": empty_dates,
            "unparseable": invalid_dates,
            "fecha_fin_menor_inicio": fecha_fin_menor_inicio,
            "fecha_inicio_fuera_de_rango_2010_2026": outside_date_range,
        },
        "fecha_inicio_por_anio": dict(sorted(start_years.items())),
        "categorical_top": {col: dict(counter.most_common(10)) for col, counter in categorical_counter.items()},
        "provider_variants": dict(provider_variants.most_common(10)),
    }
    if importe_values:
        metrics["importe"] = {
            "zero": zero_importes,
            "negative": negative_importes,
            "non_numeric": non_numeric_importes,
            "p50": round(percentile(importe_values, 50), 2),
            "p90": round(percentile(importe_values, 90), 2),
            "p99": round(percentile(importe_values, 99), 2),
            "max": round(max(importe_values), 2),
        }
    return {"columns": columns, "rows": rows_seen, "metrics": metrics}


def analyze_69b(file_path: Path) -> dict:
    encoding = detect_best_encoding(file_path)
    delimiter = detect_delimiter(file_path, encoding)
    columns: list[str] | None = None
    rows_seen = 0
    missing_counts: dict[str, int] = defaultdict(int)
    seen_values: dict[str, set[str]] = defaultdict(set)
    situation_counter: Counter[str] = Counter()
    rfc_counts: Counter[str] = Counter()

    with file_path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        for row in reader:
            if not row or all(not cell.strip() for cell in row):
                continue
            if columns is None:
                columns = [normalize_identifier(cell) for cell in row]
                continue
            rows_seen += 1
            if len(row) < len(columns):
                row = row + [""] * (len(columns) - len(row))
            if len(row) > len(columns):
                row = row[: len(columns)]
            record = {columns[idx]: row[idx].strip() for idx in range(len(columns))}
            for col in columns:
                value = record.get(col, "")
                if value == "":
                    missing_counts[col] += 1
                else:
                    seen_values[col].add(value)
            situacion = record.get("situacion_del_contribuyente", "").strip()
            if situacion:
                situation_counter[situacion] += 1
            rfc = record.get("rfc", "").strip()
            if rfc:
                rfc_counts[rfc] += 1

    if columns is None:
        return {"columns": [], "rows": 0, "metrics": {}}

    metrics = {
        "total_rows": rows_seen,
        "total_columns": len(columns),
        "file_size_bytes": file_path.stat().st_size,
        "nulls_by_column": {col: round((missing_counts.get(col, 0) / rows_seen) * 100, 2) if rows_seen else 0.0 for col in columns},
        "cardinality_by_column": {col: len(seen_values.get(col, set())) for col in columns},
        "situacion_del_contribuyente": dict(situation_counter.most_common(10)),
        "invalid_rfc": sum(1 for rfc in rfc_counts if not rfc_is_valid(rfc)),
        "duplicate_rfc": sum(1 for count in rfc_counts.values() if count > 1),
    }
    return {"columns": columns, "rows": rows_seen, "metrics": metrics}


def markdown_escape(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|")


def table_from_mapping(mapping: dict) -> str:
    if not mapping:
        return "_Sin datos_"
    header = ["Campo", "Valor"]
    lines = [f"| {header[0]} | {header[1]} |", "|---|---|"]
    for key, value in mapping.items():
        lines.append(f"| {markdown_escape(str(key))} | {markdown_escape(str(value))} |")
    return "\n".join(lines)


def render_top_counts(data: dict) -> str:
    if not data:
        return "_Sin datos_"
    lines = ["| Valor | Conteo |", "|---|---:|"]
    for key, value in list(data.items())[:10]:
        lines.append(f"| {markdown_escape(str(key))} | {value} |")
    return "\n".join(lines)


def render_year_counts(data: dict[str, int]) -> str:
    if not data:
        return "_Sin fechas de inicio parseables_"
    lines = ["| Año | Filas |", "|---:|---:|"]
    lines.extend(f"| {year} | {count} |" for year, count in sorted(data.items()))
    return "\n".join(lines)


def render_quality_report(contract_reports: list[dict], r69_report: dict) -> str:
    r69_metrics = r69_report["metrics"]

    findings = [
        "Las reglas de `tipo_procedimiento_norm` son preliminares mientras `clean.map_tipo_procedimiento.estado` sea `pendiente`.",
        "Las fechas de inicio vacías o ilegibles se conservan en `clean` con un estado explícito; no se rechazan por sí solas.",
        "Las coincidencias con 69-B son señales para revisión humana, no determinaciones legales.",
    ]

    report = f"""# Reporte de calidad de datos

Fecha de generación: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

## 1. Resumen ejecutivo

- Archivos de contratos analizados: {len(contract_reports)}
- Total de filas en contratos: {sum(rep.get('rows', 0) for rep in contract_reports)}
- Archivo 69-B: {r69_report['rows']} filas, {r69_report['columns']} columnas.
- Los datasets se leen desde `data/raw` y se documentan como fuentes no modificadas.
- Los conteos de columnas y fechas se presentan por archivo/fuente; su presencia no demuestra que un periodo esté completo.

## 2. Archivos analizados

| Archivo | Filas | Columnas | Tamaño (bytes) |
|---|---:|---:|---:|
"""

    for rep in contract_reports:
        name = rep.get("source_name", "contratos")
        report += f"| `{name}` | {rep.get('rows', 0)} | {len(rep.get('columns', []))} | {rep.get('metrics', {}).get('file_size_bytes', 0)} |\n"

    report += f"| `Listado_completo_69-B.csv` | {r69_report['rows']} | {len(r69_report['columns'])} | {r69_report['metrics'].get('file_size_bytes', 0)} |\n\n"

    report += "## 3. Métricas de contratos por fuente\n\n"
    for index, contract_report in enumerate(contract_reports, start=1):
        metrics = contract_report["metrics"]
        report += f"### 3.{index} `{contract_report.get('source_name', 'contratos')}`\n\n"
        report += "| Columna | % nulos | Cardinalidad |\n|---|---:|---:|\n"
        for col in contract_report["columns"]:
            null_pct = metrics["nulls_by_column"].get(col, 0)
            card = metrics["cardinality_by_column"].get(col, 0)
            report += f"| {col} | {null_pct}% | {card} |\n"

        report += "\n#### Duplicados e inconsistencias\n\n"
        report += f"- Duplicados en `codigo_contrato`: {metrics['duplicates_codigo_contrato']}\n"
        report += f"- Duplicados en `codigo_expediente`: {metrics['duplicates_codigo_expediente']}\n"
        report += f"- Valores `importe` en cero: {metrics.get('importe', {}).get('zero', 0)}\n"
        report += f"- Valores `importe` negativos: {metrics.get('importe', {}).get('negative', 0)}\n"
        report += f"- `importe` no numéricos: {metrics.get('importe', {}).get('non_numeric', 0)}\n"
        report += "\n#### Importes, moneda y fechas\n\n"
        report += "**`importe`**\n\n" + table_from_mapping(metrics.get("importe", {})) + "\n\n"
        report += "**`moneda`**\n\n" + render_top_counts(metrics.get("moneda", {})) + "\n\n"
        report += "**Incidencias de fechas**\n\n" + table_from_mapping(metrics.get("date_issues", {})) + "\n\n"
        report += "**Fecha de inicio por año parseable**\n\n"
        report += render_year_counts(metrics.get("fecha_inicio_por_anio", {})) + "\n\n"
        report += "#### Proveedores y categorías\n\n"
        report += render_top_counts(metrics.get("provider_variants", {})) + "\n\n"
        for key, values in metrics.get("categorical_top", {}).items():
            report += f"**`{key}`**\n\n{render_top_counts(values)}\n\n"

    report += "## 4. Métricas del listado 69-B\n\n| Columna | % nulos | Cardinalidad |\n|---|---:|---:|\n"
    for col in r69_report["columns"]:
        null_pct = r69_metrics["nulls_by_column"].get(col, 0)
        card = r69_metrics["cardinality_by_column"].get(col, 0)
        report += f"| {col} | {null_pct}% | {card} |\n"

    report += f"- RFC inválidos: {r69_metrics['invalid_rfc']}\n"
    report += f"- RFC duplicados: {r69_metrics['duplicate_rfc']}\n"
    report += "\n## 5. Distribución 69-B\n\n"
    report += render_top_counts(r69_metrics.get("situacion_del_contribuyente", {})) + "\n\n"

    report += "## 6. Hallazgos y decisiones de limpieza\n\n"
    for item in findings:
        report += f"- {item}\n"

    report += "\nLa cobertura anual de contratos debe contrastarse con el periodo y metadatos de publicación de cada fuente. El plan documenta que 2023 y 2024 son parciales y que no hay datos de 2025; confirme estos puntos frente a los conteos de `clean.v_cobertura_fuentes` tras cada carga.\n"
    return report


def detect_input_kind(path: Path) -> str:
    lower = path.name.lower()
    if "69" in lower or "listado" in lower:
        return "listado_69b"
    if "compranet" in lower or "contratos" in lower or "historico" in lower:
        return "contratos_comprasmx"
    return "contratos_comprasmx"


def generate_report(csv_dir: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    files = [p for p in sorted(csv_dir.iterdir()) if p.is_file() and p.suffix.lower() == ".csv"]
    if not files:
        raise FileNotFoundError(f"No CSV files found in {csv_dir}")
    reports = []
    contract_reports: list[dict] = []
    for path in files:
        kind = detect_input_kind(path)
        if "69" in path.name.lower() or "listado" in path.name.lower():
            reports.append((kind, analyze_69b(path)))
        else:
            report = analyze_contracts(path)
            report["source_name"] = path.name
            contract_reports.append(report)
            reports.append((kind, report))

    r69_report = next((report for kind, report in reports if kind == "listado_69b"), {"rows": 0, "columns": [], "metrics": {}})
    markdown = render_quality_report(contract_reports, r69_report)
    output_path.write_text(markdown, encoding="utf-8")
    print(f"Reporte generado: {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera el reporte de calidad de los CSV raw.")
    parser.add_argument("--csv-dir", default="data/raw", help="Directorio con los archivos CSV raw")
    parser.add_argument("--output", default="docs/reporte_calidad.md", help="Ruta del archivo Markdown a generar")
    args = parser.parse_args()
    generate_report(Path(args.csv_dir), Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
