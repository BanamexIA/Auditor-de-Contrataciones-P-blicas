"""El adaptador Detección -> Reportes del orquestador de demo.

Si Mario o Michelle cambian su contrato, estas pruebas fallan antes de la demo.
"""
import json
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "agente_reporte"))  # en el contenedor el paquete está en la raíz

from agente_deteccion.agente import ejecutar, leer_filas  # noqa: E402
from agente_reporte.agente import generar_reporte  # noqa: E402
from agente_reporte.redactor import Redactor  # noqa: E402
from agente_reporte.schemas import EntradaReporte  # noqa: E402
from backend.demo.adaptadores import (  # noqa: E402
    ClienteConBitacora,
    entrada_reporte,
    ids_de_contratos,
    llm_fn_redactor,
    senales_para_backend,
)
from llm.base import LLMResponse  # noqa: E402
from tests.fakes_casos import RepositorioEnMemoria  # noqa: E402


def _deteccion(normas=()):
    filas = leer_filas(str(RAIZ / "muestra.json"))[:200]
    recuperador = (lambda consulta, fecha, top_k: list(normas)) if normas else None
    return json.loads(json.dumps(ejecutar(filas, moneda_por_defecto="MXN", recuperador=recuperador),
                                 default=str))


class EntradaReporteTest(unittest.TestCase):
    def test_salida_de_deteccion_es_entrada_valida_de_reportes(self):
        d = _deteccion()
        entrada = EntradaReporte.model_validate(entrada_reporte(d))
        self.assertEqual(len(entrada.senales), len(d["senales"]))
        self.assertTrue(all(s.estado in ("activa", "no_evaluable") for s in entrada.senales))
        reporte = generar_reporte(entrada, Redactor())
        self.assertTrue(reporte.verificacion.aprobado)

    def test_normas_incompletas_se_descartan(self):
        completa = {"id": 1, "ley": "CFF", "version": "2024", "fecha_entrada_vigor": "2000-01-01",
                    "fecha_abrogacion": None, "contenido": "Texto del artículo.", "articulo": "69-B",
                    "distancia": 0.1, "fuente": "dof"}
        d = _deteccion([completa, {**completa, "id": 2, "articulo": None}])
        normas = entrada_reporte(d)["normas_recuperadas"]
        self.assertTrue(normas)
        self.assertTrue(all(n["fragmento_id"] == "chunk-1" for n in normas))

    def test_senales_para_backend(self):
        s = senales_para_backend(_deteccion())
        self.assertTrue(all(x["tipo"].islower() and x["datos"]["senal_id"] for x in s))


class OtrosTest(unittest.TestCase):
    def test_ids_de_contratos(self):
        self.assertEqual(ids_de_contratos([{"codigo_contrato": "A"}, {"codigo_contrato": "A"},
                                           {"codigo_contrato": "B"}]), ["A", "B"])
        self.assertEqual(ids_de_contratos([{"total": 3}]), [])

    def test_redactor_registra_en_bitacora_y_limpia_json(self):
        class Falso:
            model, base_url = "m", "http://laptop:11434"

            def generate(self, system, prompt, temperature=0.0):
                self.prompt = prompt
                return LLMResponse(text='```json\n{"texto": "hola"}\n```', input_tokens=1,
                                   output_tokens=1, latency_ms=1)
        repo = RepositorioEnMemoria()
        caso = repo.crear("x")["id"]
        falso = Falso()
        fn = llm_fn_redactor(ClienteConBitacora(falso, repo.registrar_evento, caso, "reportes"))
        texto = fn([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
                   {"type": "object"})
        self.assertEqual(texto, '{"texto": "hola"}')
        self.assertIn("JSON Schema", falso.prompt)
        [ev] = repo.eventos(caso, "llamada_llm")
        self.assertEqual((ev["detalle"]["agente"], ev["equipo"]), ("reportes", "laptop"))


if __name__ == "__main__":
    unittest.main()
