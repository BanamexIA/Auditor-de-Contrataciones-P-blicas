"""D2 · conversor de PDF de ley a fragmentos por artículo (rag/chunk_normas.py), sin necesidad de un PDF real."""
import unittest

from rag.chunk_normas import extraer_articulos, partir, quitar_encabezados, revisar, unir_parrafos

ENC = "LEY DE PRUEBA"


def pagina(*lineas):
    return [f"      {ENC}", "", *lineas, "", "   12"]


PAGINAS = [
    pagina("                       Título Primero", "                       Capítulo Único",
           "   Artículo 1. Esta Ley es de orden público", "y de observancia general.",
           "   Artículo 2. Para los efectos de esta Ley:", "    I. Secretaría: la de Hacienda;"),
    pagina("II. Dependencias: las que sean.", "   Artículo 2 Bis.- Texto del bis.",
           "                       Capítulo Segundo", "   Artículo 3.- Texto tres que cita el", "artículo 5 de otra ley."),
    pagina("   Artículo 4. Texto cuatro.", "                       Transitorios", "   Artículo 5. Esto es del decreto, no de la ley."),
]


class Chunker(unittest.TestCase):
    def setUp(self):
        self.paginas = quitar_encabezados(PAGINAS, minimo=0.4)
        self.arts, self.corto = extraer_articulos(self.paginas)

    def test_quita_encabezados_y_numeros_de_pagina_repetidos(self):
        plano = " ".join(l for p in self.paginas for l in p)
        self.assertNotIn(ENC, plano)
        self.assertNotIn("   12", self.paginas[0])

    def test_un_articulo_por_fragmento_con_bis_y_pagina(self):
        self.assertEqual([a["articulo"] for a in self.arts], ["Artículo 1", "Artículo 2", "Artículo 2 Bis", "Artículo 3", "Artículo 4"])
        self.assertEqual([a["pagina"] for a in self.arts], [1, 1, 2, 2, 3])

    def test_corta_antes_de_los_transitorios(self):
        self.assertTrue(self.corto)
        self.assertNotIn("Artículo 5", [a["articulo"] for a in self.arts])

    def test_una_cita_a_otro_articulo_en_minuscula_no_abre_un_articulo_nuevo(self):
        art3 = next(a for a in self.arts if a["articulo"] == "Artículo 3")
        self.assertIn("artículo 5 de otra ley", " ".join(art3["lineas"]))

    def test_ruta_normativa_titulo_y_capitulo(self):
        rutas = {a["articulo"]: a["ruta"] for a in self.arts}
        self.assertEqual(rutas["Artículo 1"], "Título Primero > Capítulo Único")
        self.assertEqual(rutas["Artículo 3"], "Título Primero > Capítulo Segundo")

    def test_une_las_lineas_cortadas_en_un_parrafo(self):
        art1 = self.arts[0]
        self.assertEqual(unir_parrafos(art1["lineas"]), ["Esta Ley es de orden público y de observancia general."])
        art2 = self.arts[1]
        self.assertEqual(unir_parrafos(art2["lineas"] + self.arts[1]["lineas"][:0])[0], "Para los efectos de esta Ley:")

    def test_partir_respeta_parrafos(self):
        self.assertEqual(partir(["a" * 10, "b" * 10, "c" * 10], 25), ["a" * 10 + "\n" + "b" * 10, "c" * 10])
        self.assertEqual(partir(["x" * 50], 25), ["x" * 50])             # un párrafo más largo que el máximo no se corta

    def test_articulos_con_letra_como_el_69_b_del_cff(self):
        arts, _ = extraer_articulos([["   Artículo 69-A.- Texto A.", "   Artículo 69-B.- Cuando la autoridad fiscal detecte", "que un contribuyente...",
                                      "   Artículo 69-B Bis.- Otro."]])
        self.assertEqual([a["articulo"] for a in arts], ["Artículo 69-A", "Artículo 69-B", "Artículo 69-B Bis"])
        self.assertTrue(unir_parrafos(arts[1]["lineas"])[0].startswith("Cuando la autoridad"))

    def test_control_de_numeracion(self):
        mk = lambda *ns: [{"articulo": f"Artículo {n}", "numero": n, "pagina": 1} for n in ns]
        self.assertEqual(revisar(mk(1, 2, 3), 1800), [])
        self.assertTrue(any("salto de 3 a 5" in a for a in revisar(mk(1, 2, 3, 5), 1800)))
        self.assertTrue(any("retrocede" in a for a in revisar(mk(1, 2, 3, 2), 1800)))
        self.assertTrue(any("más de una vez" in a for a in revisar(mk(1, 2, 2), 1800)))


if __name__ == "__main__":
    unittest.main()
