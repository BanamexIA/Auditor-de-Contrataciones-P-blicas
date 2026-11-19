import json
from pathlib import Path

import pytest

from agente_reporte.schemas import EntradaReporte

RUTA = Path(__file__).resolve().parent.parent / "ejemplos" / "entrada_ejemplo.json"


@pytest.fixture
def entrada() -> EntradaReporte:
    return EntradaReporte.model_validate(json.loads(RUTA.read_text(encoding="utf-8")))
