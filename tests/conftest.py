import os
import sys
from pathlib import Path

import pytest
import redis

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
REDIS_URL = os.environ.get("FLAGS3_TEST_REDIS", "redis://localhost:6379/15")
SECRET = "TESTAPIKEY123"


@pytest.fixture(scope="session")
def workspace(tmp_path_factory):
	base = tmp_path_factory.mktemp("flags3_web")
	home = base / "home"
	(home / "db" / "pfam").mkdir(parents=True)
	(home / "db" / "pfam" / "Pfam-A.hmm").write_text("HMMER3/f\n")
	env = base / ".env"
	env.write_text("\n".join([
		"flags3_bin=" + str(ROOT / "tests" / "fake_flags3.py"),
		"flags3_home=" + str(home),
		"jobs_dir=" + str(base / "jobs"),
		"ncbi_api_key=" + SECRET,
		"redis_url=" + REDIS_URL,
		"queue=flags3_test",
		"results_ttl_hours=1",
		"cpu_per_job=2",
		"max_lines=5",
	]) + "\n")
	os.environ["FLAGS3_WEB_ENV"] = str(env)
	return base


@pytest.fixture(scope="session")
def flask_app(workspace):
	redis.from_url(REDIS_URL).flushdb()
	import app as module
	module.app.config["TESTING"] = True
	return module


@pytest.fixture
def client(flask_app):
	return flask_app.app.test_client()
