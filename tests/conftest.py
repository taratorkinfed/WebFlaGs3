import os
import sys
from pathlib import Path

import pytest
import redis

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
REDIS_URL = os.environ.get("FLAGS3_TEST_REDIS", "redis://localhost:6379/15")
SECRET = "TESTAPIKEY123"
MAIL_SECRET = "TESTMAILPASS"


class FakeSmtp:
	sent = []
	fail = False

	def __init__(self, host, port, timeout=None):
		self.host, self.port = host, port
		if FakeSmtp.fail:
			raise OSError("connection refused")

	def __enter__(self):
		return self

	def __exit__(self, *exc):
		return False

	def starttls(self):
		self.tls = True

	def login(self, user, password):
		self.user, self.password = user, password

	def send_message(self, message):
		FakeSmtp.sent.append((self.host, self.port, self.user, self.password, message))


@pytest.fixture(autouse=True)
def smtp(monkeypatch):
	import smtplib
	FakeSmtp.sent = []
	FakeSmtp.fail = False
	monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
	return FakeSmtp


@pytest.fixture(scope="session")
def workspace(tmp_path_factory):
	base = tmp_path_factory.mktemp("flags3_web")
	home = base / "home"
	home.mkdir()
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
		"site_url=https://flags.example.org/",
		"smtp_user=robot@example.org",
		"mail_from=lab@example.org",
		"email_pass=" + MAIL_SECRET,
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
