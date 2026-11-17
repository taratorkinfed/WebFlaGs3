import rq
import redis

from blastinput import BlastQueries
from capabilities import Capabilities
from config import Settings
from submission import Command, Validator
from tests.conftest import REDIS_URL

SEQ = "MDQGKNVLEWDEYFMGVAALSALRSKDPHTQVGACIVSKDRRILSIGYNGTPRGIDDSVF"
FORM = {"accessions": "", "gene": "4", "iterations": "3", "evalue": "", "tree": "none", "pdf": "1", "email": "fed@example.org",
	"run_name": "blastrun"}
ALL = Capabilities.everything()


def _work(flask_app):
	rq.SimpleWorker([flask_app.queue], connection=redis.from_url(REDIS_URL)).work(burst=True)


def test_queries_are_accessions_and_sequences():
	text = "WP_005328829.1\n\n>first protein\n{}\n{}\n>second\n{}*\n\nAAC73113.1\n{}\n".format(SEQ[:30], SEQ[30:], SEQ.lower(), SEQ[:20])
	found = BlastQueries(5).parse(text)
	assert found.error == "" and found.queries == ["WP_005328829.1", SEQ, SEQ, "AAC73113.1", SEQ[:20]]
	assert BlastQueries(5).parse("").queries == [] and BlastQueries(5).parse(" \n\n").error == ""
	spaced = BlastQueries(5).parse("MDQGK NVLEW\nDEYFM")
	assert spaced.queries == ["MDQGKNVLEWDEYFM"]


def test_bad_queries_are_refused():
	assert "unexpected 1 2" in BlastQueries(5).parse("MDQGKNVLEW12").error
	assert "&lt;" in BlastQueries(5).parse("MDQGK<script>NVLEW").error
	assert "9 residues" in BlastQueries(5).parse("MDQGKNVLE").error
	assert "5001 residues" in BlastQueries(5).parse("M" * 5001).error
	many = BlastQueries(5).parse("\n".join("WP_00000000{}.1".format(i) for i in range(6)))
	assert "6 starting proteins given; a job takes at most 5" in many.error
	assert BlastQueries(5).parse("WP_1.1 GCF_000005845.2").error


def test_submission_with_blast_only(tmp_path):
	s = Validator(200, ALL, 5).parse({**FORM, "blast": "WP_005328829.1\n>x\n" + SEQ})
	assert s.accepted and s.lines == [] and s.blast == ["WP_005328829.1", SEQ]
	assert s.input_text == "WP_005328829.1\tBLAST\n{}\tBLAST".format(SEQ)
	both = Validator(200, ALL, 5).parse({**FORM, "accessions": "WP_1.1", "blast": "WP_005328829.1"})
	assert both.input_text == "WP_1.1\nWP_005328829.1\tBLAST"
	empty = Validator(200, ALL, 5).parse(FORM)
	assert "accessions" in empty.errors and "blast" not in empty.errors
	bad = Validator(200, ALL, 5).parse({**FORM, "blast": "MDQ1"})
	assert set(bad.errors) == {"blast", "accessions"} and bad.blast_text == "MDQ1"
	off = Validator(200, Capabilities({"core"}, (3, 7, 0)), 5).parse({**FORM, "accessions": "WP_1.1", "blast": "WP_005328829.1"})
	assert off.accepted and off.blast == [] and off.input_text == "WP_1.1"


def test_hits_are_shared_between_queries(tmp_path):
	settings = Settings({"flags3_bin": "/opt/flags3", "flags3_home": str(tmp_path), "blast_db": "/db/refseq_protein"})
	for count, each in ((1, "50"), (2, "25"), (3, "16"), (4, "12"), (5, "10")):
		s = Validator(200, ALL, 5).parse({**FORM, "blast": "\n".join("WP_00000000{}.1".format(i) for i in range(count))})
		command = Command(settings, s, "a", "b")
		argv = command.argv()
		assert argv[argv.index("-bm") + 1] == "local" and argv[argv.index("-bd") + 1] == "/db/refseq_protein"
		assert argv[argv.index("-bh") + 1] == each and argv[argv.index("-bx") + 1] == "2759"
		assert command.environment({})["BLASTDB"] == "/db"
	plain = Validator(200, ALL, 5).parse({**FORM, "accessions": "WP_1.1"})
	argv = Command(settings, plain, "a", "b").argv()
	assert "-bm" not in argv and "-bx" not in argv and "BLASTDB" not in Command(settings, plain, "a", "b").environment({})
	everything = Settings({"flags3_bin": "/opt/flags3", "flags3_home": str(tmp_path), "blast_db": "/db/x", "blast_exclude": " "})
	s = Validator(200, ALL, 5).parse({**FORM, "blast": "WP_005328829.1"})
	assert "-bx" not in Command(everything, s, "a", "b").argv()


def test_blast_needs_database_core_and_flags3_3_7(tmp_path):
	assert Capabilities({"core", "blastdb"}, (3, 7, 0)).has("blast")
	assert not Capabilities({"core", "blastdb"}, (3, 6, 0)).has("blast")
	assert not Capabilities({"core"}, (3, 7, 0)).has("blast")
	assert not Capabilities({"blastdb"}, (3, 7, 0)).has("blast")
	assert Capabilities(set(), (3, 7, 0)).has("clusters_legend") and not Capabilities(set(), (3, 7, 0)).has("nonsense")
	fake = str(__import__("pathlib").Path(__file__).with_name("fake_flags3.py"))
	(tmp_path / "db.pal").write_text("TITLE x\n")
	assert Capabilities.probe(Settings({"flags3_bin": fake, "flags3_home": str(tmp_path), "blast_db": str(tmp_path / "db")})).has("blast")
	assert not Capabilities.probe(Settings({"flags3_bin": fake, "flags3_home": str(tmp_path), "blast_db": str(tmp_path / "gone")})).has("blast")
	assert not Capabilities.probe(Settings({"flags3_bin": fake, "flags3_home": str(tmp_path)})).has("blast")


def test_blast_job_through_the_form(client, flask_app, workspace):
	page = client.get("/")
	assert b'id="blast" name="blast"' in page.data and b"RefSeq proteins without eukaryotes" in page.data
	assert b"up to 5 starting proteins" in page.data and b"50 in all" in page.data
	sent = client.post("/", data={**FORM, "blast": "WP_005328829.1\n>mine\n" + SEQ})
	assert sent.status_code == 302
	job_id = sent.headers["Location"].rsplit("/", 1)[1]
	job_dir = workspace / "jobs" / job_id
	assert (job_dir / "input.txt").read_text() == "WP_005328829.1\tBLAST\n{}\tBLAST\n".format(SEQ)
	_work(flask_app)
	status = client.get("/status/" + job_id).get_json()
	assert status["status"] == "finished"
	assert "-bm local -bd <blastdb> -bh 25 -bx 2759" in status["log"] and str(workspace) not in status["log"]
	assert "BlastP (local) for 2 queries against <blastdb>, BLASTDB=<blastdb>" in status["log"]
	assert (job_dir / "run" / "blast" / "hits.tsv").read_text().count("WP_") == 50
	for name in ("run.tsv", "report/run_summary.txt"):
		assert str(workspace / "blastdb") not in (job_dir / "run" / name).read_text(), name
	refused = client.post("/", data={**FORM, "blast": "not a protein 1"})
	assert refused.status_code == 400 and b"Not a protein accession or a protein sequence" in refused.data
	assert b"not a protein 1" in refused.data


def _submit(client, email="limited@example.org", address="10.0.0.1", **extra):
	return client.post("/", data={**FORM, "email": email, "blast": "WP_005328829.1", **extra}, environ_overrides={"REMOTE_ADDR": address})


def test_three_blast_jobs_at_a_time_per_address_and_email(client, flask_app):
	for n in range(3):
		assert _submit(client, email="user{}@example.org".format(n)).status_code == 302
	fourth = _submit(client, email="user3@example.org")
	assert fourth.status_code == 429 and b"3 BlastP jobs from this address are already queued or running" in fourth.data
	assert b"WP_005328829.1" in fourth.data and len(flask_app.queue) == 3
	plain = client.post("/", data={**FORM, "accessions": "WP_1.1", "email": "user0@example.org"}, environ_overrides={"REMOTE_ADDR": "10.0.0.1"})
	assert plain.status_code == 302
	assert _submit(client, email="other@example.org", address="10.0.0.2").status_code == 302
	for n in range(2):
		assert _submit(client, email="Same@Example.org", address="10.0.1.{}".format(n)).status_code == 302
	assert _submit(client, email="same@example.org", address="10.0.1.9").status_code == 302
	by_email = _submit(client, email=" SAME@example.org", address="10.0.1.10")
	assert by_email.status_code == 429 and b"from this email address" in by_email.data
	_work(flask_app)
	assert _submit(client, email="user3@example.org").status_code == 302
	_work(flask_app)


def test_limit_counts_only_live_jobs_and_can_be_switched_off(flask_app):
	from limits import ActiveJobs, BlastLimit
	connection = redis.from_url(REDIS_URL)
	jobs = ActiveJobs(connection, "unit:blast")
	key = jobs.key("address", "192.0.2.7")
	connection.delete(key)
	assert "192.0.2.7" not in key and jobs.key("email", "A@b.c ") == jobs.key("email", "a@b.c")
	jobs.add("address", "192.0.2.7", "0" * 32)
	assert connection.scard(key) == 1 and 0 < connection.ttl(key) <= 7 * 24 * 3600
	assert jobs.count("address", "192.0.2.7") == 0 and connection.scard(key) == 0
	off = BlastLimit(connection, "unit", 0)
	for n in range(5):
		off.record("192.0.2.8", "x@y.z", "{:032d}".format(n))
	assert off.refusal("192.0.2.8", "x@y.z") is None
	assert BlastLimit(connection, "unit", 3).refusal("", "nobody@y.z") is None
