from agente_reporte.agente import exportar, generar_reporte
from agente_reporte.plantilla import AVISO_REVISION_HUMANA, render_markdown
from agente_reporte.redactor import Redactor

from .fakes import FakeLLM


def test_flujo_completo_con_llm_falso(entrada):
    llm = FakeLLM()
    r = generar_reporte(entrada, Redactor(llm, "fake"))
    assert len(llm.llamadas) == 3  # 2 señales activas + resumen (la no evaluable no usa LLM)
    assert r.verificacion.aprobado and r.verificacion.tasa_citas_correctas == 1.0
    assert r.aviso == AVISO_REVISION_HUMANA
    tipos = {l.tipo for l in r.limitaciones}
    assert {"registro_excluido", "dato_contradictorio", "senal_no_evaluable",
            "confianza_baja", "sin_norma_aplicable"} <= tipos


def test_senal_no_evaluable_no_concluye_sin_riesgo(entrada):
    r = generar_reporte(entrada, Redactor(FakeLLM(), "fake"))
    s = next(s for s in r.senales if s.estado == "no_evaluable")
    assert "no debe interpretarse como ausencia de riesgo" in s.narrativa and not s.citas


def test_modo_sin_llm_funciona(entrada):
    r = generar_reporte(entrada, Redactor())
    assert all(not s.narrativa_generada_por_llm for s in r.senales)
    assert r.verificacion.aprobado
    assert AVISO_REVISION_HUMANA in render_markdown(r)


def test_fallo_de_ollama_degrada_a_respaldo(entrada):
    r = generar_reporte(entrada, Redactor(FakeLLM(error=ConnectionError("x")), "fake"))
    assert r.verificacion.aprobado and all(not s.narrativa_generada_por_llm for s in r.senales)


def test_sin_senales_declara_que_no_es_ausencia_de_riesgo(entrada):
    entrada.senales = []
    r = generar_reporte(entrada, Redactor())
    assert any(l.tipo == "sin_senales" for l in r.limitaciones)


def test_contradiccion_se_muestra_sin_elegir_valor(entrada):
    md = render_markdown(generar_reporte(entrada, Redactor()))
    assert "1650000.00" in md and "1560000.00" in md


def test_exportar(entrada, tmp_path):
    rutas = exportar(generar_reporte(entrada, Redactor()), tmp_path, ("pdf", "json", "md"))
    assert all(r.exists() for r in rutas.values())
