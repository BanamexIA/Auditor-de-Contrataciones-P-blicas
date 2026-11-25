"""Ajustes al orquestador después del PR #4: límite de tiempo, bitácora del RAG, laptop por caso,
reporte rápido y resultados para el front. Reusa el escenario falso de test_orquestador."""

import unittest
from decimal import Decimal
from unittest.mock import patch

from backend.casos import estados as e
from backend.orquestador.estado import Limites
from tests.test_orquestador import Escenario


class LimiteDeTiempoTest(unittest.TestCase):
    def test_pasarse_del_tiempo_en_reportes_no_bloquea_un_caso_ya_reportado(self):
        esc = Escenario()
        reportar = esc.deps().generar_reporte

        deps = esc.deps()

        def reporte_lento(caso_id, deteccion, cliente, agente):
            esc.ahora += 1000  # el Agente Reportes tardó más que el límite del caso
            return reportar(caso_id, deteccion, cliente, agente)
        deps.generar_reporte = reporte_lento
        from backend.orquestador.grafo import orquestar_caso
        orquestar_caso(esc.caso["id"], deps, Limites(tiempo_max_s=900))
        caso = esc.repo.obtener(esc.caso["id"])
        self.assertEqual(caso["estado"], e.EN_REVISION)
        self.assertEqual(len(esc.repo.listar_reportes(esc.caso["id"])), 1)

    def test_el_limite_sigue_cortando_antes_de_las_etapas_de_trabajo(self):
        esc = Escenario()
        esc.paso_reloj = 100.0
        self.assertEqual(esc.correr(Limites(tiempo_max_s=350))["estado"], e.BLOQUEADO)


class BitacoraRagTest(unittest.TestCase):
    def test_busquedas_fallidas_quedan_en_un_solo_evento(self):
        esc = Escenario()

        def falla(consulta, fecha, top_k):
            raise TimeoutError("embeddings")
        esc.recuperador = falla
        self.assertEqual(esc.correr()["estado"], e.EN_REVISION)
        eventos = [ev for ev in esc.repo.eventos(esc.caso["id"], "error")
                   if "Búsqueda normativa" in ev["detalle"]["mensaje"]]
        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0]["detalle"]["tipo"], "TimeoutError")
        self.assertGreater(eventos[0]["detalle"]["busquedas_fallidas"], 1)


class LaptopPorCasoTest(unittest.TestCase):
    def test_embeddings_en_la_laptop_del_caso_sin_tocar_el_entorno(self):
        from backend.orquestador.dependencias import recuperador_para

        class RecuperadorFalso:
            def __init__(self, conn=None):
                self.cliente, self.conn = "por-defecto", conn

        with patch.dict("os.environ", {"OLLAMA_EMBED_BASE_URL": ""}), \
                patch("agente_deteccion.normativo.RecuperadorPgvector", RecuperadorFalso):
            import os
            a = recuperador_para({"url": "http://laptop-a:11434"}, conn="c1")
            b = recuperador_para({"url": "http://laptop-b:11434"}, conn="c2")
            self.assertEqual(os.environ.get("OLLAMA_EMBED_BASE_URL"), "")
        self.assertEqual((a.cliente.base_url, b.cliente.base_url),
                         ("http://laptop-a:11434", "http://laptop-b:11434"))


class ReporteRapidoTest(unittest.TestCase):
    def test_sin_narrativa_llm_no_usa_el_modelo_ni_pide_laptop(self):
        esc = Escenario()
        deps = esc.deps()
        deps.narrativa_llm = False
        elegidas = []
        elegir = deps.seleccionar_agente
        deps.seleccionar_agente = lambda u: elegidas.append(u) or elegir(u)
        from backend.orquestador.grafo import orquestar_caso
        final = orquestar_caso(esc.caso["id"], deps, Limites())
        self.assertEqual(esc.repo.obtener(esc.caso["id"])["estado"], e.EN_REVISION)
        self.assertEqual(esc.clientes_reporte, [None])   # narrativas de respaldo
        self.assertEqual(len(elegidas), 1)                # solo la de la consulta
        self.assertFalse(final.get("parciales"))         # es una elección, no un resultado parcial


class UmbralNormasTest(unittest.TestCase):
    """2026-11-24: sin umbral, cada señal citaba los 3 fragmentos más cercanos aunque no aplicaran."""

    def _normas(self, distancia, umbral=0.28):
        from tests.test_orquestador import norma
        esc = Escenario()
        esc.recuperador = lambda consulta, fecha, top_k: [{**norma(7), "distancia": distancia}]
        deps = esc.deps()
        deps.umbral_distancia = umbral
        from backend.orquestador.grafo import orquestar_caso
        orquestar_caso(esc.caso["id"], deps, Limites())
        ev = esc.repo.eventos(esc.caso["id"], "normas_recuperadas")[-1]["detalle"]
        return ev["normas"], ev["sin_soporte"]

    def test_un_fragmento_lejano_no_se_cita(self):
        normas, sin = self._normas(0.30)
        self.assertEqual(normas, [])
        self.assertTrue(any("umbral de similitud" in s["motivo"] for s in sin))

    def test_uno_cercano_si(self):
        self.assertTrue(self._normas(0.25)[0])

    def test_sin_umbral_pasa_todo(self):
        self.assertTrue(self._normas(0.9, umbral=None)[0])

    def test_corpus_vacio_no_se_confunde_con_el_umbral(self):
        esc = Escenario()
        esc.recuperador = lambda consulta, fecha, top_k: []
        from backend.orquestador.grafo import orquestar_caso
        orquestar_caso(esc.caso["id"], esc.deps(), Limites())
        sin = esc.repo.eventos(esc.caso["id"], "normas_recuperadas")[-1]["detalle"]["sin_soporte"]
        self.assertTrue(any("no tiene fragmentos vigentes" in s["motivo"] for s in sin))

    def test_umbral_desde_el_entorno(self):
        from backend.orquestador.dependencias import umbral_distancia_rag
        for valor, esperado in (("", 0.28), ("0.3", 0.3), ("ninguno", None)):
            with self.subTest(valor=valor), patch.dict("os.environ", {"RAG_UMBRAL_DISTANCIA": valor}):
                self.assertEqual(umbral_distancia_rag(), esperado)


class ApiTest(unittest.TestCase):
    def setUp(self):
        from backend.app import create_app
        self.esc = Escenario()
        self.app = create_app(repositorio=self.esc.repo, auth_secreto="")
        self.deps = self.esc.deps()
        self.app.extensions["orquestador_deps"] = lambda app: self.deps
        self.app.extensions["lanzar_orquestador"] = lambda trabajo: trabajo()  # sin hilo
        self.sql = []
        self.app.extensions["ejecutar_solo_lectura"] = lambda sql: self.sql.append(sql) or [
            {"codigo_contrato": "C-1", "importe": Decimal("306000.50"), "fecha_inicio": "2026-04-14"}]
        self.cliente = self.app.test_client()
        self.id = self.esc.caso["id"]

    def test_orquestar_con_reporte_rapido(self):
        r = self.cliente.post(f"/casos/{self.id}/orquestar", json={"narrativa_llm": False})
        self.assertEqual(r.status_code, 202)
        self.assertEqual(self.esc.clientes_reporte, [None])

    def test_orquestar_sin_cuerpo_conserva_el_modelo(self):
        self.assertEqual(self.cliente.post(f"/casos/{self.id}/orquestar").status_code, 202)
        self.assertIsNotNone(self.esc.clientes_reporte[0])

    def test_resultados_reejecutan_el_sql_de_la_bitacora(self):
        self.assertEqual(self.cliente.get(f"/casos/{self.id}/resultados").status_code, 409)
        self.cliente.post(f"/casos/{self.id}/orquestar", json={"narrativa_llm": False})
        d = self.cliente.get(f"/casos/{self.id}/resultados").get_json()
        self.assertEqual(self.sql, [d["sql"]])
        self.assertEqual(d["filas"][0]["importe"], 306000.5)  # número, no texto
        self.assertEqual(d["total_filas"], 1)
        self.assertEqual(self.cliente.get("/casos/no-existe/resultados").status_code, 404)


if __name__ == "__main__":
    unittest.main()
