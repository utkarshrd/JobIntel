"""The Alembic baseline must build exactly the schema the models describe (no drift)."""
import argparse
import os

from alembic import command
from alembic.config import Config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cfg(url):
    cfg = Config(os.path.join(ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(ROOT, "alembic"))
    cfg.cmd_opts = argparse.Namespace(x=[f"url={url}"])
    return cfg


def test_baseline_migration_matches_models(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = _cfg(url)
    command.upgrade(cfg, "head")
    command.check(cfg)          # raises if models and migrations differ
    from sqlalchemy import create_engine, inspect
    tables = set(inspect(create_engine(url)).get_table_names())
    assert {"jobs", "users", "skills", "job_skills", "user_skills", "interactions", "ingestion_runs", "companies"} <= tables
