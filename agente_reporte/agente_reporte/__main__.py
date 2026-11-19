"""Uso:
    python -m agente_reporte ejemplos/entrada_ejemplo.json --out ejemplos/salida --sin-llm
    python -m agente_reporte ejemplos/entrada_ejemplo.json --out ejemplos/salida --modelo qwen2.5:7b-instruct
"""
import argparse
import json
import sys

from .agente import exportar, generar_reporte
from .redactor import Redactor


def main() -> int:
    p = argparse.ArgumentParser(description="Genera un reporte de señales de riesgo.")
    p.add_argument("entrada", help="JSON con la EntradaReporte")
    p.add_argument("--out", default="salida", help="directorio de salida")
    p.add_argument("--sin-llm", action="store_true", help="usa solo textos deterministas")
    p.add_argument("--md", action="store_true", help="genera también una versión Markdown")
    p.add_argument("--modelo", default=None, help="modelo de Ollama (o variable OLLAMA_MODEL)")
    a = p.parse_args()

    with open(a.entrada, encoding="utf-8") as f:
        datos = json.load(f)
    redactor = Redactor() if a.sin_llm else Redactor.desde_ollama(a.modelo)
    reporte = generar_reporte(datos, redactor)
    rutas = exportar(reporte, a.out, ('pdf', 'json', 'md') if a.md else ('pdf', 'json'))

    v = reporte.verificacion
    print("Archivos: " + ", ".join(str(r) for r in rutas.values()))
    print(f"Citas correctas: {v.citas_correctas}/{v.total_citas} ({v.tasa_citas_correctas:.0%}) · "
          f"{'APROBADO' if v.aprobado else 'REQUIERE REVISIÓN'}")
    return 0 if v.aprobado else 1


if __name__ == "__main__":
    sys.exit(main())
