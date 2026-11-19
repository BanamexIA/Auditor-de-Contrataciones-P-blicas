from agente_reporte.agente import generar_reporte
from agente_reporte.plantilla_pdf import render_pdf
from agente_reporte.redactor import Redactor

from .fakes import FakeLLM


def _pdf(entrada, tmp_path, llm=None):
    r = generar_reporte(entrada, Redactor(llm, "fake") if llm else Redactor())
    ruta = render_pdf(r, tmp_path / "r.pdf", comprimir=False)
    return r, ruta.read_bytes()


def test_pdf_valido_con_aprobado_e_indice(entrada, tmp_path):
    _, datos = _pdf(entrada, tmp_path, FakeLLM())
    assert datos.startswith(b"%PDF") and b"%%EOF" in datos
    assert b"APROBADO" in datos and b"NO APROBADO" not in datos
    assert b"ndice" in datos


def test_pdf_no_aprobado(entrada, tmp_path):
    r = generar_reporte(entrada, Redactor())
    r.verificacion.aprobado = False
    datos = render_pdf(r, tmp_path / "r.pdf", comprimir=False).read_bytes()
    assert b"NO APROBADO" in datos


def test_pdf_sin_senales_ni_contratos(entrada, tmp_path):
    entrada.senales, entrada.contratos, entrada.normas_recuperadas = [], [], []
    entrada.concentracion, entrada.patrones_adjudicacion, entrada.contradicciones = [], {}, []
    _, datos = _pdf(entrada, tmp_path)
    assert datos.startswith(b"%PDF")


def test_pdf_texto_con_caracteres_especiales(entrada, tmp_path):
    entrada.contratos[0].proveedor = "Alfa <b>& Asociados</b> S.A."
    entrada.senales[0].criterio = "Criterio con <tags> & ampersand"
    _, datos = _pdf(entrada, tmp_path)
    assert datos.startswith(b"%PDF")


def test_pdf_con_muchas_senales_pagina_varias_veces(entrada, tmp_path):
    base = entrada.senales[0]
    entrada.senales = [base.model_copy(update={"codigo": f"S{i}", "nombre": f"Señal {i}"}) for i in range(25)]
    _, datos = _pdf(entrada, tmp_path)
    assert datos.count(b"/Type /Page\n") + datos.count(b"/Type /Page ") >= 3
