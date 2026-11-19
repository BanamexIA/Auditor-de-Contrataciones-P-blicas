from agente_reporte.agente import generar_reporte
from agente_reporte.redactor import Redactor
from agente_reporte.verificador import (
    articulos_mencionados, normalizar_articulo, numeros_no_respaldados, terminos_prohibidos, verificar_reporte,
)

from .fakes import FakeLLM


def _reporte(entrada):
    return generar_reporte(entrada, Redactor(FakeLLM(), "fake"))


def test_normalizar_articulo():
    assert normalizar_articulo("69-B") == normalizar_articulo(" 69b ") == "69B"


def test_articulos_mencionados():
    assert articulos_mencionados("Según el artículo 41 y los arts. 42 y 69-B del código") == ["41", "42", "69B"]
    assert articulos_mencionados("Sin referencias normativas") == []


def test_terminos_prohibidos():
    assert terminos_prohibidos("Posible fraude y corrupción") == ["corrupción", "fraude"]
    assert terminos_prohibidos("Señal que podría requerir revisión") == []


def test_numeros_no_respaldados():
    fuente = {"monto": 4850000.0}
    assert numeros_no_respaldados("Suma de 4,850,000.00 pesos", fuente) == []
    assert numeros_no_respaldados("Suma de 9,999,999 pesos", fuente) == ["9,999,999"]


def test_reporte_valido_tasa_100(entrada):
    v = _reporte(entrada).verificacion
    assert v.aprobado and v.tasa_citas_correctas == 1.0 and v.total_citas >= 1


def test_cita_a_fragmento_inexistente_se_detecta(entrada):
    r = _reporte(entrada)
    r.senales[0].citas[0].fragmento_id = "frag-inventado"
    v = verificar_reporte(r, entrada)
    assert not v.aprobado and v.tasa_citas_correctas == 0.0 and v.citas_invalidas


def test_cita_con_articulo_alterado_se_detecta(entrada):
    r = _reporte(entrada)
    r.senales[0].citas[0].articulo = "99"
    assert not verificar_reporte(r, entrada).aprobado


def test_cita_de_otra_senal_se_detecta(entrada):
    r = _reporte(entrada)
    c = r.senales[0].citas[0]
    c.fragmento_id, c.norma, c.articulo = "frag-cff-0069B", "CFF", "69-B"
    assert not verificar_reporte(r, entrada).aprobado


def test_articulo_inventado_en_texto_se_detecta(entrada):
    r = _reporte(entrada)
    r.senales[0].narrativa += " Esto contraviene el artículo 99."
    assert verificar_reporte(r, entrada).articulos_no_respaldados
