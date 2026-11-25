"""D5 · búsqueda híbrida (vectores + palabras clave con RRF) y su uso desde la tool normativa."""
import unittest
from datetime import date

from agente_deteccion.normativo import recuperar_normas
from rag.core import fusionar_rrf, retrieve_hybrid, retrieve_text


def fila(i, d, **extra):
    return {"id": i, "distancia_coseno": d, "contenido": f"c{i}", **extra}


class Fusion(unittest.TestCase):
    def test_lo_que_aparece_en_las_dos_listas_gana(self):
        # puntajes: 3 -> 1/63 + 1/61 = 0.0323 ; 1 -> 1/61 = 0.0164 ; 2 -> 1/62 = 0.0161
        r = fusionar_rrf([fila(1, .1), fila(2, .2), fila(3, .3)], [fila(3, .3, puntaje_texto=.9)])
        self.assertEqual([f["id"] for f in r], [3, 1, 2])
        f3 = r[0]
        self.assertEqual((f3["rank_vector"], f3["rank_texto"], f3["coincide_texto"]), (3, 1, True))
        self.assertAlmostEqual(f3["puntaje_rrf"], 1 / 63 + 1 / 61)

    def test_una_coincidencia_de_texto_sube_un_fragmento_lejano_en_vectores(self):
        # el 3 es el último en vectores pero primero en texto: 3 -> 0.03227 ; 2 -> 1/62 + 1/62 = 0.03226 ; 1 -> 0.0164
        r = fusionar_rrf([fila(1, .1), fila(2, .2), fila(3, .6)], [fila(3, .6), fila(2, .2)])
        self.assertEqual([f["id"] for f in r], [3, 2, 1])

    def test_solo_vectores_marca_que_no_hubo_coincidencia_de_texto(self):
        (f,) = fusionar_rrf([fila(1, .1)], [])
        self.assertEqual((f["rank_texto"], f["coincide_texto"]), (None, False))

    def test_empate_se_resuelve_por_distancia_y_despues_por_id(self):
        r = fusionar_rrf([fila(2, .5)], [fila(1, .1)])
        self.assertEqual([f["id"] for f in r], [1, 2])


class Cursor:
    description = []

    def __init__(self, filas=()):
        self.filas = filas
        self.consultas = []

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def execute(self, q, p):
        self.consultas.append((q, p))

    def fetchall(self): return []


class Conn:
    def __init__(self): self.c = Cursor()
    def cursor(self): return self.c


class ConsultaTexto(unittest.TestCase):
    def test_palabras_clave_son_alternativas_y_el_filtro_de_vigencia_es_el_mismo(self):
        conn = Conn()
        retrieve_text(conn, [0.1, 0.2], 5, date(2024, 6, 1), "consulta", ["adjudicación directa", "69-B"])
        q, p = conn.c.consultas[0]
        self.assertEqual(q.count("websearch_to_tsquery"), 2)
        self.assertIn("||", q)
        self.assertIn("fecha_entrada_vigor <= %(fecha)s::date", q)
        self.assertIn("%(fecha)s::date < d.fecha_abrogacion", q)
        self.assertEqual((p["p0"], p["p1"], p["fecha"], p["n"]), ("adjudicación directa", "69-B", date(2024, 6, 1), 5))
        self.assertNotIn("%s", q)

    def test_sin_palabras_clave_usa_los_terminos_de_la_consulta(self):
        conn = Conn()
        retrieve_text(conn, [0.1], 5, None, "adjudicación directa", None)
        q, p = conn.c.consultas[0]
        self.assertIn("plainto_tsquery", q)
        self.assertEqual(p["p0"], "adjudicación directa")
        self.assertIsNone(p["fecha"])

    def test_top_k_invalido(self):
        with self.assertRaises(ValueError):
            retrieve_hybrid(Conn(), [0.1], 0)


class Normativo(unittest.TestCase):
    SENALES = [{"senal_id": "ADJ-001", "codigo": "ADJ_DIRECTA_RECURRENTE", "estado": "evaluada", "contratos_ids": ["C1"]}]
    CONTRATOS = [{"id": "C1", "fecha": date(2026, 3, 2)}]

    def test_pasa_palabras_clave_solo_si_el_recuperador_las_acepta(self):
        vistos = {}

        def con(consulta, fecha, top_k, palabras_clave=None):
            vistos["pc"] = palabras_clave
            return []

        def sin(consulta, fecha, top_k):
            vistos["sin"] = True
            return []
        recuperar_normas(self.SENALES, self.CONTRATOS, con)
        recuperar_normas(self.SENALES, self.CONTRATOS, sin)
        self.assertIn("adjudicación directa", vistos["pc"])
        self.assertTrue(vistos["sin"])

    def test_respeta_el_orden_de_la_busqueda_hibrida_y_trae_sus_campos(self):
        filas = [{"id": 2, "ley": "LAASSP", "articulo": "41", "distancia": 0.6, "contenido": "a", "puntaje_rrf": 0.03, "coincide_texto": True, "metodo_busqueda": "hibrida"},
                 {"id": 1, "ley": "LAASSP", "articulo": "26", "distancia": 0.2, "contenido": "b", "puntaje_rrf": 0.02, "coincide_texto": False, "metodo_busqueda": "hibrida"}]
        normas, _ = recuperar_normas(self.SENALES, self.CONTRATOS, lambda c, f, k, palabras_clave=None: list(filas))
        self.assertEqual([n["fragmento_id"] for n in normas], ["chunk-2", "chunk-1"])
        self.assertEqual(normas[0]["metodo_busqueda"], "hibrida")
        self.assertTrue(normas[0]["coincide_texto"])

    def test_el_umbral_de_distancia_sigue_mandando(self):
        filas = [{"id": 2, "ley": "L", "articulo": "1", "distancia": 0.9, "contenido": "a", "coincide_texto": True}]
        normas, sin = recuperar_normas(self.SENALES, self.CONTRATOS, lambda c, f, k, palabras_clave=None: list(filas), umbral_distancia=0.5)
        self.assertEqual(normas, [])
        self.assertIn("umbral", sin[0]["motivo"])


if __name__ == "__main__":
    unittest.main()
