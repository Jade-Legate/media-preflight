import os

import psycopg
import pytest

# 실제 Postgres의 테스트 전용 DB를 쓴다(모킹 없음). preflight import 전에 환경을 정해야 한다.
_base = os.environ.get("DATABASE_URL", "postgresql+psycopg://preflight:preflight@localhost:5432/preflight")
_admin = _base.replace("postgresql+psycopg://", "postgresql://")
with psycopg.connect(_admin, autocommit=True) as conn:
    conn.execute("DROP DATABASE IF EXISTS preflight_test WITH (FORCE)")
    conn.execute("CREATE DATABASE preflight_test")
os.environ["DATABASE_URL"] = _base.rsplit("/", 1)[0] + "/preflight_test"
os.environ["RQ_SYNC"] = "true"
os.environ["OBJECT_STORAGE_CREATE_BUCKET"] = "true"
os.environ.setdefault("OBJECT_STORAGE_PUBLIC_ENDPOINT", os.environ.get("OBJECT_STORAGE_ENDPOINT", "http://localhost:9000"))

from preflight.samples import make_samples  # noqa: E402


@pytest.fixture(scope="session")
def samples(tmp_path_factory):
    return make_samples(str(tmp_path_factory.mktemp("samples")))
