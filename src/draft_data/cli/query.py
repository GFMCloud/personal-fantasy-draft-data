"""query: ad-hoc DuckDB SQL over the processed outputs.

Views: players (players.parquet), picks (draft_picks.parquet).
"""

from __future__ import annotations

import duckdb
import pandas as pd

from draft_data.config import PROCESSED_DIR


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"CREATE VIEW players AS SELECT * FROM read_parquet('{PROCESSED_DIR}/players.parquet')")
    picks = PROCESSED_DIR / "draft_picks.parquet"
    if picks.exists():
        con.execute(f"CREATE VIEW picks AS SELECT * FROM read_parquet('{picks}')")
    return con


def run_query(sql: str) -> int:
    pd.set_option("display.width", 200)
    pd.set_option("display.max_rows", 200)
    con = connect()
    print(con.execute(sql).df().to_string(index=False))
    return 0
