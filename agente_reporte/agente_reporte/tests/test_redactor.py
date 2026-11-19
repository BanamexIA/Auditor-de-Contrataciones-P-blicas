from agente_reporte.redactor import Redactor

from .fakes import FakeLLM, narrativa

BUENA = "Se detectó una señal que podría requerir revisión humana, con base en los valores calculados."


def _args(entrada, i=0):
    s = entrada.senales[i]
    ids = set(s.contratos_ids)
    return (
        s,
        [c for c in entrada.contratos if c.id in ids],
        [f for f in entrada.normas_recuperadas if f.senal_codigo == s.codigo],
    )


def test_respuesta_valida_se_usa_sin_reintento(entrada):
    llm = FakeLLM([narrativa(BUENA, ["frag-laassp-0041"])])
    n = Redactor(llm).redactar_senal(*_args(entrada))
    assert n and n.fragmento_ids == ["frag-laassp-0041"] and len(llm.llamadas) == 1


def test_articulo_inventado_regenera_una_vez(entrada):
    mala = narrativa("Se detectó una señal conforme al artículo 99 que podría requerir revisión.", ["frag-laassp-0041"])
    llm = FakeLLM([mala, narrativa(BUENA, ["frag-laassp-0041"])])
    n = Redactor(llm).redactar_senal(*_args(entrada))
    assert n and len(llm.llamadas) == 2


def test_dos_fallos_devuelve_none_y_solo_dos_llamadas(entrada):
    mala = narrativa("Posible fraude detectado en estos contratos, requiere revisión.", [])
    llm = FakeLLM([mala])
    assert Redactor(llm).redactar_senal(*_args(entrada)) is None
    assert len(llm.llamadas) == 2


def test_fragmento_de_otra_senal_no_se_acepta(entrada):
    llm = FakeLLM([narrativa(BUENA, ["frag-cff-0069B"])])
    assert Redactor(llm).redactar_senal(*_args(entrada)) is None


def test_cifra_inventada_no_se_acepta(entrada):
    mala = narrativa("El monto total asciende a 9,999,999.00 pesos y podría requerir revisión.", [])
    llm = FakeLLM([mala])
    assert Redactor(llm).redactar_senal(*_args(entrada)) is None


def test_json_invalido_regenera(entrada):
    llm = FakeLLM(["esto no es json", narrativa(BUENA, [])])
    assert Redactor(llm).redactar_senal(*_args(entrada)) is not None
    assert len(llm.llamadas) == 2


def test_error_de_ollama_usa_respaldo_sin_reintentar(entrada):
    llm = FakeLLM(error=ConnectionError("ollama caído"))
    assert Redactor(llm).redactar_senal(*_args(entrada)) is None
    assert len(llm.llamadas) == 1


def test_sin_normas_no_permite_citar(entrada):
    llm = FakeLLM([narrativa(BUENA, ["frag-laassp-0041"])])
    assert Redactor(llm).redactar_senal(*_args(entrada, 1)) is None  # MONTO_ATIPICO no tiene normas
