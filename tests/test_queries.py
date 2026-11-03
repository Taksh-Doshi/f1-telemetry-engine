import pytest

from f1engine.queries import _format_table, run_query


def test_format_table_aligns_column_values():
    assert _format_table(
        ["driver", "lap"],
        [("VER", 1), ("LEC", None)],
    ) == (
        "driver | lap \n"
        "-------+-----\n"
        "VER    | 1   \n"
        "LEC    | NULL"
    )


@pytest.mark.parametrize("query_number", [0, 11])
def test_run_query_rejects_numbers_outside_available_files(query_number):
    with pytest.raises(ValueError, match="between 1 and 10"):
        run_query(query_number)
