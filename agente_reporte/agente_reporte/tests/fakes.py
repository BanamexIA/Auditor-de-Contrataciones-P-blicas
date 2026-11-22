"""LLM falso para pruebas: no requiere Ollama."""
import json
import re


class FakeLLM:
    def __init__(self, respuestas=None, error=None):
        """respuestas: lista de strings JSON (se consumen en orden; la última se repite)."""
        self.respuestas = list(respuestas or [])
        self.error = error
        self.llamadas = []

    def __call__(self, messages, schema):
        self.llamadas.append(messages)
        if self.error:
            raise self.error
        if self.respuestas:
            return self.respuestas.pop(0) if len(self.respuestas) > 1 else self.respuestas[0]
        return self.automatica(messages, schema)

    @staticmethod
    def automatica(messages, schema):
        """Respuesta válida: cita el primer fragmento del bloque NORMAS (si hay)."""
        if "texto" in schema["properties"]:
            return json.dumps({"texto": "Se observa concentración en un proveedor; son señales que requieren revisión humana."})
        contenido = messages[1]["content"]
        ids = re.findall(r'"fragmento_id": "([^"]+)"', contenido)
        return json.dumps({
            "narrativa": "Se detectó una señal que podría requerir revisión humana, con base en los valores calculados.",
            "fragmento_ids": ids[:1],
        })


def narrativa(texto, ids=()):
    return json.dumps({"narrativa": texto, "fragmento_ids": list(ids)})
