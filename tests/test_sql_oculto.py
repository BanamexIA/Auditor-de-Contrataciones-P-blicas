"""El SQL de un caso solo se devuelve al rol admin (retroalimentación del 2026-11-26).

Mostrarlo al usuario de negocio expone tablas, vistas y columnas. Se sigue guardando completo en la
bitácora: lo que cambia es qué devuelve la API según el rol.
"""

import unittest

from backend.app import create_app
from tests.fakes_casos import RepositorioEnMemoria
from tests.fakes_usuarios import SECRETO, RepositorioUsuariosEnMemoria

CLAVE = "Clave-segura-123"
SQL = "SELECT codigo_contrato FROM clean.v_contratos_agente LIMIT 10"


class SqlOcultoTest(unittest.TestCase):
    def setUp(self):
        self.repo = RepositorioEnMemoria()
        usuarios = RepositorioUsuariosEnMemoria()
        usuarios.alta("ana", "Ana", "auditor", CLAVE)
        usuarios.alta("root", "Admin", "admin", CLAVE)
        self.app = create_app(repositorio=self.repo, repositorio_usuarios=usuarios, auth_secreto=SECRETO)
        self.app.extensions["ejecutar_solo_lectura"] = lambda sql: [{"codigo_contrato": "C-1"}]
        self.c = self.app.test_client()
        self.caso = self.repo.crear("Contratos de prueba", creado_por="ana")
        self.repo.registrar_evento(self.caso["id"], "sql_generado", {"sql": SQL, "supuestos": ["s1"]})
        self.repo.registrar_evento(self.caso["id"], "sql_rechazado", {"sql": "SELECT 1", "motivo": "m"})
        self.repo.registrar_evento(self.caso["id"], "sql_ejecutado",
                                   {"sql": SQL, "vistas": ["clean"], "filas": 1, "duracion_ms": 1.0, "truncado": False})

    def h(self, usuario):
        token = self.c.post("/auth/login", json={"usuario": usuario, "contrasena": CLAVE}).get_json()["token"]
        return {"Authorization": f"Bearer {token}"}

    def eventos_sql(self, usuario):
        eventos = self.c.get(f"/casos/{self.caso['id']}/bitacora", headers=self.h(usuario)).get_json()["eventos"]
        return [e for e in eventos if e["evento"].startswith("sql_")]

    def test_el_auditor_no_recibe_el_sql_pero_si_el_resto(self):
        eventos = self.eventos_sql("ana")
        self.assertEqual(len(eventos), 3)
        for e in eventos:
            self.assertNotIn("sql", e["detalle"])
            self.assertTrue(e["detalle"]["sql_oculto"])
        self.assertEqual(eventos[0]["detalle"]["supuestos"], ["s1"])       # los supuestos sí
        self.assertEqual(eventos[1]["detalle"]["motivo"], "m")             # y el motivo del rechazo
        r = self.c.get(f"/casos/{self.caso['id']}/resultados", headers=self.h("ana")).get_json()
        self.assertIsNone(r["sql"])
        self.assertEqual(r["filas"], [{"codigo_contrato": "C-1"}])        # la tabla sigue llegando

    def test_el_admin_si_lo_recibe(self):
        self.assertTrue(all(e["detalle"].get("sql") for e in self.eventos_sql("root")))
        r = self.c.get(f"/casos/{self.caso['id']}/resultados", headers=self.h("root")).get_json()
        self.assertEqual(r["sql"], SQL)

    def test_la_bitacora_guarda_el_sql_completo(self):
        guardados = [e for e in self.repo.listar_eventos(self.caso["id"]) if e["evento"] == "sql_ejecutado"]
        self.assertEqual(guardados[0]["detalle"]["sql"], SQL)


if __name__ == "__main__":
    unittest.main()
