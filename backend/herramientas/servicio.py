"""Herramientas gobernadas que el servidor MCP expone a los agentes.

Reglas de gobierno (las mismas para cualquier agente o cliente MCP):

1. Los datos se leen solo con ``agent_ro``: sesión de solo lectura y con tiempo límite.
2. Toda herramienta que toca datos exige un ``caso_id`` existente y no cerrado, y deja un
   evento en ``audit.bitacora`` con ``origen: "mcp"``. Sin caso no hay acceso a datos.
3. Ninguna herramienta decide sobre una señal ni cambia el estado de un caso: eso lo hace
   una persona (B4) o el orquestador.
4. Los límites (filas, contratos, longitud de texto) son fijos y se aplican antes de tocar la base.

Las dependencias (ejecución de SQL, carga de contratos, RAG) se inyectan para probar sin base.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import date
from typing import Any, Callable

from backend.casos.estados import CERRADO

ORIGEN = "mcp"
MAX_FILAS_RESPUESTA = 200
MAX_CONTRATOS = 500
MAX_TEXTO = 500
MAX_TOP_K = 10

SQL_CONTRATOS = """
SELECT codigo_contrato AS id, proveedor, rfc, importe AS monto, moneda, institucion AS dependencia,
       tipo_procedimiento, tipo_procedimiento_norm, fecha_inicio AS fecha, fecha_fin, fuente,
       fecha_inicio_estado, fecha_inicio_valida, ley
FROM clean.contratos WHERE codigo_contrato = ANY(%s)"""
SQL_COINCIDENCIAS = """
SELECT codigo_contrato, rfc_exacto, nombre_normalizado_exacto, nivel_confianza, rfc,
       nombre_del_contribuyente
FROM clean.v_coincidencias_69b_agente WHERE codigo_contrato = ANY(%s)"""

EjecutarSQL = Callable[[str], list[dict[str, Any]]]
CargarContratos = Callable[[list[str]], tuple[list[dict], list[dict]]]
Recuperador = Callable[[str, "date | None", int], list[dict]]


class HerramientaRechazada(ValueError):
    """La petición no cumple las reglas; el mensaje es para el agente (sin datos sensibles)."""


def _json(valor: Any) -> Any:
    """Fechas, Decimal y demás a tipos JSON."""
    return json.loads(json.dumps(valor, ensure_ascii=False, default=str))


def _ids(contratos_ids: list[str]) -> list[str]:
    if not isinstance(contratos_ids, list) or not contratos_ids:
        raise HerramientaRechazada("Indica al menos un código de contrato en contratos_ids.")
    ids = list(dict.fromkeys(str(i).strip() for i in contratos_ids if str(i).strip()))
    if not ids:
        raise HerramientaRechazada("Los códigos de contrato están vacíos.")
    if len(ids) > MAX_CONTRATOS:
        raise HerramientaRechazada(f"Máximo {MAX_CONTRATOS} contratos por llamada; se recibieron {len(ids)}.")
    return ids


def cargar_contratos_con(conectar_ro: Callable[[], Any]) -> CargarContratos:
    """Carga contratos y coincidencias 69-B con agent_ro (conexión psycopg con filas dict)."""

    def cargar(ids: list[str]) -> tuple[list[dict], list[dict]]:
        with conectar_ro() as conn, conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(SQL_CONTRATOS, (ids,))
            filas = list(cur.fetchall())
            cur.execute(SQL_COINCIDENCIAS, (ids,))
            return filas, list(cur.fetchall())
    return cargar


class Herramientas:
    def __init__(
        self,
        repo,
        ejecutar_sql: EjecutarSQL,
        cargar_contratos: CargarContratos,
        describir: Callable[[], dict[str, Any]],
        cobertura: Callable[[], Any] | None = None,
        recuperador: Callable[[], Recuperador] | None = None,
        origen: str = ORIGEN,
    ):
        self.repo = repo
        self.origen = origen  # quién usó la herramienta: "mcp" o el orquestador que la llama directo
        self._ejecutar_sql = ejecutar_sql
        self._cargar = cargar_contratos
        self._describir = describir
        self._cobertura = cobertura
        self._recuperador = recuperador

    # ------------------------------------------------------------------ apoyo
    def _caso(self, caso_id: str) -> dict:
        from backend.casos.repositorio import CasoNoEncontrado
        if not isinstance(caso_id, str) or not caso_id.strip():
            raise HerramientaRechazada("Falta caso_id: todo acceso a datos se registra en un caso.")
        try:
            caso = self.repo.obtener(caso_id.strip())
        except CasoNoEncontrado:
            raise HerramientaRechazada(f"El caso {caso_id} no existe.") from None
        if caso["estado"] == CERRADO:
            raise HerramientaRechazada(f"El caso {caso_id} está cerrado; abre un caso nuevo.")
        return caso

    def _registrar(self, caso_id: str, evento: str, detalle: dict) -> None:
        self.repo.registrar_evento(caso_id, evento, {**_json(detalle), "origen": self.origen})

    # ------------------------------------------------------------------ herramientas
    def describir_datos(self) -> dict[str, Any]:
        """Metadatos: vistas, columnas con su significado y periodos con datos completos."""
        return self._describir()

    def consultar_contratos(self, caso_id: str, sql: str) -> dict[str, Any]:
        from agents.consulta.coverage import check_coverage
        from agents.consulta.validator import SQLValidationError, validate_sql
        from psycopg import DataError, ProgrammingError

        caso = self._caso(caso_id)
        if not isinstance(sql, str) or not sql.strip():
            raise HerramientaRechazada("El SQL está vacío.")
        try:
            seguro = validate_sql(sql)
        except SQLValidationError as exc:
            self._registrar(caso["id"], "sql_rechazado", {"sql": sql[:2000], "motivo": str(exc)})
            raise HerramientaRechazada(f"SQL rechazado: {exc}") from None

        supuestos: list[str] = []
        if self._cobertura is not None:
            revision = check_coverage(seguro, self._cobertura())
            if revision.sin_datos:
                self._registrar(caso["id"], "sql_rechazado", {"sql": seguro, "motivo": revision.sin_datos})
                raise HerramientaRechazada(f"Sin datos para ese periodo: {revision.sin_datos}")
            supuestos = list(revision.supuestos)

        inicio = time.perf_counter()
        try:
            filas = self._ejecutar_sql(seguro)
        except (ProgrammingError, DataError) as exc:
            motivo = f"PostgreSQL rechazó la consulta: {str(exc).strip()[:300]}"
            self._registrar(caso["id"], "sql_rechazado", {"sql": seguro, "motivo": motivo})
            raise HerramientaRechazada(motivo) from None
        duracion = round((time.perf_counter() - inicio) * 1000, 1)
        self._registrar(caso["id"], "sql_ejecutado", {
            "sql": seguro, "vistas": ["clean"], "filas": len(filas), "duracion_ms": duracion,
            "truncado": len(filas) > MAX_FILAS_RESPUESTA})
        return {"caso_id": caso["id"], "sql": seguro, "supuestos": supuestos, "total_filas": len(filas),
                "filas": _json(filas[:MAX_FILAS_RESPUESTA])}

    def evaluar_calidad(self, caso_id: str, contratos_ids: list[str]) -> dict[str, Any]:
        from agente_deteccion.detectores import construir_excluidos
        from agente_deteccion.normalizacion import normalizar_contratos

        caso = self._caso(caso_id)
        ids = _ids(contratos_ids)
        filas, _ = self._cargar(ids)
        no_encontrados = sorted(set(ids) - {str(f["id"]) for f in filas})
        if filas:
            contratos, contradicciones, resumen = normalizar_contratos(filas)
            problemas = construir_excluidos(contratos)
        else:
            contradicciones, resumen, problemas = [], {}, []
        por_motivo = dict(Counter(p["motivo"] for p in problemas))
        self._registrar(caso["id"], "calidad_evaluada", {
            "contratos": len(filas), "problemas": por_motivo,
            "contradicciones": len(contradicciones), "no_encontrados": len(no_encontrados)})
        return _json({
            "caso_id": caso["id"], "contratos_revisados": len(filas),
            "problemas_por_motivo": por_motivo, "problemas": problemas[:MAX_FILAS_RESPUESTA],
            "contradicciones": contradicciones[:MAX_FILAS_RESPUESTA], "resumen": resumen,
            "no_encontrados": no_encontrados[:MAX_FILAS_RESPUESTA],
            "nota": "Un problema no descarta el contrato: indica qué reglas no se le pueden aplicar.",
        })

    def detectar_senales(self, caso_id: str, contratos_ids: list[str]) -> dict[str, Any]:
        from agente_deteccion.agente import ejecutar

        caso = self._caso(caso_id)
        ids = _ids(contratos_ids)
        filas, coincidencias = self._cargar(ids)
        if not filas:
            raise HerramientaRechazada("Ninguno de esos códigos de contrato existe en clean.contratos.")
        r = _json(ejecutar(filas, coincidencias, consulta_id=caso["id"]))
        self._registrar(caso["id"], "reglas_evaluadas", {
            "reglas": sorted({s["codigo"] for s in r["senales"]}), "senales": len(r["senales"]),
            "version_reglas": r["version_reglas"],
            "evaluadas": r["calidad"]["senales_evaluadas"],
            "no_evaluables": r["calidad"]["senales_no_evaluables"]})
        return {"caso_id": caso["id"], "version_reglas": r["version_reglas"], "senales": r["senales"],
                "excluidos": r["excluidos"][:MAX_FILAS_RESPUESTA], "concentracion": r["concentracion"][:10],
                "aviso": r["aviso"],
                "nota": "Las señales son propuestas: solo una persona las marca como relevantes o descartadas."}

    def buscar_norma(self, caso_id: str, texto: str, fecha: str | None = None,
                     top_k: int = 3) -> dict[str, Any]:
        caso = self._caso(caso_id)
        if not isinstance(texto, str) or not texto.strip():
            raise HerramientaRechazada("Describe qué norma buscas en 'texto'.")
        if len(texto) > MAX_TEXTO:
            raise HerramientaRechazada(f"'texto' pasa de {MAX_TEXTO} caracteres.")
        if not isinstance(top_k, int) or not 1 <= top_k <= MAX_TOP_K:
            raise HerramientaRechazada(f"top_k debe estar entre 1 y {MAX_TOP_K}.")
        try:
            dia = date.fromisoformat(fecha) if fecha else None
        except ValueError:
            raise HerramientaRechazada("La fecha debe tener formato AAAA-MM-DD.") from None
        if self._recuperador is None:
            raise HerramientaRechazada("El RAG normativo no está configurado en este servidor.")

        try:
            filas = self._recuperador()(texto.strip(), dia, top_k)
        except Exception as exc:  # sin laptop para embeddings, base caída, etc.
            motivo = f"El RAG normativo no está disponible: {str(exc)[:200]}"
            self._registrar(caso["id"], "error", {"tipo": type(exc).__name__, "mensaje": motivo})
            raise HerramientaRechazada(motivo) from None
        normas = [{"fragmento_id": f"chunk-{f['id']}", "ley": f.get("ley"), "articulo": f.get("articulo"),
                   "version": f.get("version"), "vigencia": f.get("fecha_entrada_vigor"),
                   "abrogacion": f.get("fecha_abrogacion"), "distancia_coseno": f.get("distancia"),
                   "texto": f.get("contenido")} for f in filas]
        self._registrar(caso["id"], "normas_recuperadas", {
            "normas": [{k: n[k] for k in ("fragmento_id", "ley", "articulo", "version")} for n in normas],
            "sin_soporte": [] if normas else [texto.strip()[:200]],
            "fecha_referencia": dia})
        return _json({"caso_id": caso["id"], "fecha_referencia": dia, "normas": normas,
                      "nota": ("Cita solo estos fragmentos." if normas else
                               "No hay norma vigente que respalde esto: decláralo, no la inventes.")})
