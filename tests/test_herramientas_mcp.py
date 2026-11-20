"""Herramientas gobernadas y servidor MCP (sin base de datos)."""
import asyncio
import unittest
from pathlib import Path

from psycopg import ProgrammingError

from agente_deteccion.agente import leer_filas
from backend.herramientas.servicio import MAX_CONTRATOS, HerramientaRechazada, Herramientas
from backend.herramientas.servidor import crear_servidor
from tests.fakes_casos import RepositorioEnMemoria

RAIZ = Path(__file__).resolve().parents[1]
MUESTRA = leer_filas(str(RAIZ / "muestra.json"))[:120]
SQL_OK = "SELECT codigo_contrato FROM clean.v_contratos_agente LIMIT 5"


class Fakes:
    def __init__(self):
        self.sql = []
        self.error_sql = None

    def ejecutar_sql(self, sql):
        self.sql.append(sql)
        if self.error_sql:
            raise self.error_sql
        return [{"codigo_contrato": "C-1"}]

    def cargar(self, ids):
        return [f for f in MUESTRA if str(f["id"]) in ids], []

    def recuperador(self):
        return lambda texto, fecha, top_k: [{
            "id": 7, "ley": "CFF", "articulo": "69-B", "version": "2024", "contenido": "Texto.",
            "fecha_entrada_vigor": None, "fecha_abrogacion": None, "distancia": 0.2}][:top_k]


class HerramientasTest(unittest.TestCase):
    def setUp(self):
        self.repo = RepositorioEnMemoria()
        self.caso = self.repo.crear("pregunta")["id"]
        self.f = Fakes()
        self.h = Herramientas(self.repo, self.f.ejecutar_sql, self.f.cargar,
                              describir=lambda: {"vistas": "clean.v_contratos_agente"},
                              recuperador=self.f.recuperador)

    def eventos(self, tipo):
        return self.repo.eventos(self.caso, tipo)

    def test_sin_caso_no_hay_acceso(self):
        for caso in ("", "no-existe"):
            with self.assertRaises(HerramientaRechazada):
                self.h.consultar_contratos(caso, SQL_OK)
        self.assertEqual(self.f.sql, [])

    def test_caso_cerrado(self):
        for estado in ("consultado", "detectado", "normado", "reportado", "en_revision", "cerrado"):
            self.repo.transitar(self.caso, estado, None)
        with self.assertRaisesRegex(HerramientaRechazada, "cerrado"):
            self.h.detectar_senales(self.caso, ["x"])

    def test_consulta_valida_y_queda_en_bitacora(self):
        r = self.h.consultar_contratos(self.caso, SQL_OK)
        self.assertEqual((r["total_filas"], r["filas"]), (1, [{"codigo_contrato": "C-1"}]))
        [ev] = self.eventos("sql_ejecutado")
        self.assertEqual((ev["detalle"]["origen"], ev["detalle"]["filas"]), ("mcp", 1))

    def test_sql_peligroso_no_se_ejecuta(self):
        for sql in ("DELETE FROM clean.contratos", "SELECT 1; DROP TABLE audit.casos",
                    "SELECT * FROM audit.usuarios LIMIT 1"):
            with self.assertRaises(HerramientaRechazada, msg=sql):
                self.h.consultar_contratos(self.caso, sql)
        self.assertEqual(self.f.sql, [])
        self.assertEqual(len(self.eventos("sql_rechazado")), 3)

    def test_error_de_postgres_se_registra(self):
        self.f.error_sql = ProgrammingError('column "x" does not exist')
        with self.assertRaisesRegex(HerramientaRechazada, "PostgreSQL"):
            self.h.consultar_contratos(self.caso, SQL_OK)
        self.assertEqual(len(self.eventos("sql_rechazado")), 1)

    def test_calidad(self):
        ids = [str(f["id"]) for f in MUESTRA[:40]] + ["no-existe"]
        r = self.h.evaluar_calidad(self.caso, ids)
        self.assertEqual((r["contratos_revisados"], r["no_encontrados"]), (40, ["no-existe"]))
        [ev] = self.eventos("calidad_evaluada")
        self.assertEqual(ev["detalle"]["problemas"], r["problemas_por_motivo"])

    def test_limite_de_contratos(self):
        with self.assertRaises(HerramientaRechazada):
            self.h.evaluar_calidad(self.caso, [str(i) for i in range(MAX_CONTRATOS + 1)])
        with self.assertRaises(HerramientaRechazada):
            self.h.detectar_senales(self.caso, [])

    def test_detectar_no_guarda_senales(self):
        r = self.h.detectar_senales(self.caso, [str(f["id"]) for f in MUESTRA])
        self.assertTrue(r["senales"])
        self.assertEqual(self.repo.listar_senales(self.caso), [])  # solo propone
        [ev] = self.eventos("reglas_evaluadas")
        self.assertEqual(ev["detalle"]["senales"], len(r["senales"]))

    def test_buscar_norma(self):
        r = self.h.buscar_norma(self.caso, "listado 69-B", "2026-01-15")
        self.assertEqual(r["normas"][0]["fragmento_id"], "chunk-7")
        with self.assertRaises(HerramientaRechazada):
            self.h.buscar_norma(self.caso, "x", "15/01/2026")
        with self.assertRaises(HerramientaRechazada):
            self.h.buscar_norma(self.caso, "x", top_k=50)
        self.assertEqual(len(self.eventos("normas_recuperadas")), 1)

    def test_rag_caido_da_mensaje_claro(self):
        def caido():
            raise RuntimeError("Ningún agente de inferencia disponible")
        self.h._recuperador = caido
        with self.assertRaisesRegex(HerramientaRechazada, "RAG normativo no está disponible"):
            self.h.buscar_norma(self.caso, "listado 69-B")
        self.assertEqual(len(self.eventos("error")), 1)


class ServidorMcpTest(unittest.TestCase):
    def setUp(self):
        self.repo = RepositorioEnMemoria()
        f = Fakes()
        self.servidor = crear_servidor(Herramientas(self.repo, f.ejecutar_sql, f.cargar,
                                                    describir=lambda: {"ok": True}))

    def test_expone_las_herramientas_y_ninguna_decide(self):
        nombres = {t.name for t in asyncio.run(self.servidor.list_tools())}
        self.assertEqual(nombres, {"describir_datos", "consultar_contratos", "evaluar_calidad",
                                   "detectar_senales", "buscar_norma"})
        self.assertFalse(any("decid" in n or "transit" in n for n in nombres))

    def test_llamada_por_mcp(self):
        caso = self.repo.crear("x")["id"]
        r = asyncio.run(self.servidor.call_tool("consultar_contratos", {"caso_id": caso, "sql": SQL_OK}))
        self.assertFalse(r.is_error)
        self.assertIn("C-1", r.content[0].text)


if __name__ == "__main__":
    unittest.main()
