import unittest

from agents.consulta.counts import count_support, records_query, total_rows_query, truncation_note
from agents.consulta.validator import validate_sql

V = "clean.v_contratos_agente"
M = "clean.v_coincidencias_69b_agente"


class FakeExecute:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.queries = []

    def __call__(self, sql):
        self.queries.append(sql)
        return self.answers.pop(0)


class TotalRowsQueryTests(unittest.TestCase):
    def test_drops_limit_and_order_and_passes_the_validator(self):
        query = total_rows_query(f"SELECT codigo_contrato FROM {V} ORDER BY fecha_inicio DESC LIMIT 10")
        self.assertEqual(query, f"SELECT COUNT(*) AS filas_totales FROM (SELECT codigo_contrato FROM {V}) AS t LIMIT 1")
        validate_sql(query)

    def test_keeps_the_order_that_distinct_on_needs(self):
        query = total_rows_query(f"SELECT DISTINCT ON (fuente) fuente, codigo_contrato FROM {V} ORDER BY fuente LIMIT 5")
        self.assertIn("ORDER BY fuente", query)

    def test_invalid_sql_gives_none(self):
        self.assertIsNone(total_rows_query("SELECT FROM WHERE"))


class RecordsQueryTests(unittest.TestCase):
    def test_counts_the_records_of_each_group(self):
        query = records_query(f"SELECT fuente, SUM(importe) AS total FROM {V} WHERE moneda = 'MXN' GROUP BY fuente LIMIT 5")
        self.assertEqual(
            query,
            f"SELECT COALESCE(SUM(t.n), 0) AS registros FROM (SELECT COUNT(*) AS n FROM {V} "
            "WHERE moneda = 'MXN' GROUP BY fuente) AS t LIMIT 1",
        )
        validate_sql(query)

    def test_group_by_an_alias_or_a_position_uses_the_expression(self):
        by_alias = records_query(
            f"SELECT EXTRACT(YEAR FROM fecha_inicio) AS anio, COUNT(*) FROM {V} WHERE fecha_inicio_valida "
            "GROUP BY anio ORDER BY anio LIMIT 20"
        )
        self.assertIn("GROUP BY EXTRACT(YEAR FROM fecha_inicio)", by_alias)
        by_position = records_query(f"SELECT institucion, COUNT(*) FROM {V} GROUP BY 1 LIMIT 200")
        self.assertIn("GROUP BY institucion", by_position)
        for query in (by_alias, by_position):
            validate_sql(query)

    def test_an_alias_named_like_a_column_is_left_as_the_column(self):
        query = records_query(f"SELECT UPPER(fuente) AS fuente, COUNT(*) FROM {V} GROUP BY fuente LIMIT 5")
        self.assertIn("GROUP BY fuente", query)

    def test_keeps_joins_and_having(self):
        query = records_query(
            f"SELECT c.proveedor_normalizado, COUNT(*) AS n FROM {V} AS c JOIN {M} AS m "
            "ON m.codigo_contrato = c.codigo_contrato GROUP BY c.proveedor_normalizado HAVING COUNT(*) > 3 LIMIT 10"
        )
        self.assertIn("JOIN", query)
        self.assertIn("HAVING COUNT(*) > 3", query)
        validate_sql(query)

    def test_lists_and_subqueries_give_none(self):
        self.assertIsNone(records_query(f"SELECT codigo_contrato FROM {V} LIMIT 5"))
        self.assertIsNone(records_query(f"SELECT COUNT(*) FROM (SELECT fuente FROM {V}) AS s LIMIT 1"))


class CountSupportTests(unittest.TestCase):
    def test_decimal_results_become_integers(self):
        from decimal import Decimal

        execute = FakeExecute([{"registros": Decimal("2356609")}])
        count = count_support(f"SELECT fuente, COUNT(*) FROM {V} GROUP BY fuente LIMIT 5", [{}, {}], execute)
        self.assertEqual(count["registros"], 2356609)
        self.assertIsInstance(count["registros"], int)

    def test_an_aggregate_cut_by_the_limit_runs_both_queries(self):
        execute = FakeExecute([{"filas_totales": 784}], [{"registros": 84676}])
        rows = [{}] * 200
        count = count_support(f"SELECT institucion, COUNT(*) FROM {V} GROUP BY institucion LIMIT 200", rows, execute)
        self.assertEqual(count, {"filas": 200, "filas_totales": 784, "truncado": True, "registros": 84676})
        self.assertEqual(len(execute.queries), 2)

    def test_unparseable_sql_gives_empty_counts(self):
        self.assertEqual(
            count_support("SELECT FROM WHERE", [], FakeExecute()),
            {"filas": 0, "filas_totales": None, "truncado": None, "registros": None},
        )


class TruncationNoteTests(unittest.TestCase):
    def test_only_a_cut_result_gets_a_note(self):
        self.assertEqual(
            truncation_note({"filas": 200, "filas_totales": 784, "truncado": True}),
            "El resultado se cortó: se muestran 200 de 784 filas por el LIMIT.",
        )
        self.assertIsNone(truncation_note({"filas": 5, "filas_totales": 5, "truncado": False}))
        self.assertIsNone(truncation_note({"filas": 5, "filas_totales": None, "truncado": None}))


if __name__ == "__main__":
    unittest.main()
