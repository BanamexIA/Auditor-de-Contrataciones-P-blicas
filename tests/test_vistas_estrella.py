"""T6: checks the star views without a database (docs/vistas_estrella.md, section 6).

sqlglot does not read COMMENT ON VIEW, so comments and grants are read with
regular expressions and only each view's SELECT goes through sqlglot.
"""
import re
import unittest
from pathlib import Path

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify

ROOT = Path(__file__).resolve().parents[1]
VIEWS = {"v_hecho_contrato", "v_dim_proveedor", "v_dim_institucion", "v_dim_fecha", "v_dim_procedimiento"}


def views_sql_path() -> Path:
    """The draft lives in docs/ until Backend moves it to etl/sql/ with its number."""
    moved = sorted((ROOT / "etl" / "sql").glob("*vistas_estrella*.sql"))
    return moved[-1] if moved else ROOT / "docs" / "vistas_estrella.sql"


def clean_tables() -> dict[str, list[str]]:
    """Columns of the clean tables, read from their CREATE TABLE and ALTER TABLE statements."""
    tables: dict[str, list[str]] = {}
    for name in ("04_clean.sql", "06_fase4b_schema.sql"):
        text = (ROOT / "etl" / "sql" / name).read_text(encoding="utf-8")
        for table, body in re.findall(r"CREATE TABLE IF NOT EXISTS clean\.(\w+) \((.*?)\n\);", text, flags=re.DOTALL):
            columns = [line.strip().split()[0] for line in body.splitlines() if line.strip()]
            tables.setdefault(table, []).extend(c for c in columns if c.upper() not in {"PRIMARY", "UNIQUE", "CHECK"})
        for table, body in re.findall(r"ALTER TABLE clean\.(\w+)(.*?);", text, flags=re.DOTALL):
            tables.setdefault(table, []).extend(re.findall(r"ADD COLUMN IF NOT EXISTS (\w+)", body))
    return tables


class StarViewsTests(unittest.TestCase):
    def setUp(self):
        self.text = views_sql_path().read_text(encoding="utf-8")
        self.views = {
            name: sqlglot.parse_one(body, read="postgres")
            for name, body in re.findall(
                r"CREATE OR REPLACE VIEW clean\.(\w+) AS\s*(.*?);\s*$", self.text, flags=re.DOTALL | re.MULTILINE
            )
        }
        self.comments = {
            (view, column or None)
            for _, view, column in re.findall(r"COMMENT ON (VIEW|COLUMN) clean\.(\w+)(?:\.(\w+))? IS", self.text)
        }

    def test_defines_the_fact_and_the_four_dimensions(self):
        self.assertEqual(set(self.views), VIEWS)

    def test_every_view_and_column_has_a_comment(self):
        # The evidence T6 asks for: scripts/check_comentarios.sql returns no rows.
        expected = set()
        for name, select in self.views.items():
            expected.add((name, None))
            expected |= {(name, column) for column in select.named_selects}
        self.assertEqual(self.comments, expected)

    def test_views_only_read_columns_that_exist_in_clean(self):
        schema = {"clean": {table: {column: "TEXT" for column in columns} for table, columns in clean_tables().items()}}
        for name, select in self.views.items():
            with self.subTest(vista=name):
                qualify(select.copy(), schema=schema, dialect="postgres", validate_qualify_columns=True,
                        quote_identifiers=False, identify=False)

    def test_views_read_only_clean_tables(self):
        for name, select in self.views.items():
            with self.subTest(vista=name):
                self.assertTrue(all(table.db == "clean" for table in select.find_all(exp.Table)))

    def test_every_view_is_granted_to_agent_ro(self):
        grant = re.search(r"GRANT SELECT ON (.*?) TO agent_ro;", self.text, flags=re.DOTALL)
        self.assertIsNotNone(grant)
        self.assertEqual(set(re.findall(r"clean\.(\w+)", grant.group(1))), VIEWS)

    def test_provider_dimension_does_not_expose_the_rfc(self):
        self.assertNotIn("rfc", [column.lower() for column in self.views["v_dim_proveedor"].named_selects])

    def test_procedure_dimension_has_the_values_of_the_semantic_layer(self):
        document = (ROOT / "docs" / "capa_semantica.md").read_text(encoding="utf-8")
        sentence = re.search(r"Conteo por `tipo_procedimiento_norm`:(.*?)\.", document, flags=re.DOTALL).group(1)
        semantic = set(re.findall(r"`(\w+)`", sentence))
        rows = self.views["v_dim_procedimiento"].find(exp.Values).expressions
        self.assertEqual({row.expressions[0].this for row in rows}, semantic)
        self.assertEqual(len(semantic), 5)

    def test_draft_is_not_run_by_init_db_until_approved(self):
        # scripts/init_db.ps1 runs every file in etl/sql/; the draft stays in docs/.
        if views_sql_path().parent.name == "docs":
            self.assertFalse(list((ROOT / "etl" / "sql").glob("*vistas_estrella*.sql")))


if __name__ == "__main__":
    unittest.main()
