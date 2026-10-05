"""Result storage (SQLite / Parquet).

Auto Design saves every evaluation from day one: geometry, grouping, sections,
DCRs, drift, weight, analysis time. This data trains the ML phase later.
TODO: choose schema (see plugins/auto_design/records.py).
"""
