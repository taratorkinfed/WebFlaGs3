import re

import rq
import redis

from tests.conftest import REDIS_URL

FORM = {"accessions": "WP_1.1\nAAC73113.1 U00096", "gene": "4", "iterations": "3", "evalue": "1e-10",
	"tree": "tree_order", "pdf": "1", "email": "fed@example.org", "run_name": "webrun"}


def _work(flask_app):
	worker = rq.SimpleWorker([flask_app.queue], connection=redis.from_url(REDIS_URL))
	worker.work(burst=True)


def test_form_page_and_demo(client):
	page = client.get("/")
	assert page.status_code == 200 and b"Accession list" in page.data and b"Pfam domains" in page.data
	html = page.data.decode()
	padloc = html[html.index('id="padloc"'):html.index('id="padloc"') + 200]
	genomad = html[html.index('id="genomad"'):html.index('id="genomad"') + 200]
	assert "disabled" in padloc and "disabled" not in genomad
	assert client.head("/").status_code == 200
	demo = client.get("/?demo=1")
	assert b"WP_028660106.1" in demo.data and b"WP_028275955.1" in demo.data


def test_invalid_submission_rerenders_with_errors(client):
	page = client.post("/", data={**FORM, "email": "nope", "accessions": "bad line here"})
	assert page.status_code == 400 and b"is-invalid" in page.data and b"<b>bad line here</b>" in page.data
	assert b"valid email address" in page.data


def test_full_job_flow(client, flask_app):
	page = client.post("/", data=FORM)
	assert page.status_code == 302
	job_id = page.headers["Location"].rsplit("/", 1)[1]
	assert re.fullmatch(r"[0-9a-f]{32}", job_id)
	queued = client.get("/results/" + job_id)
	assert queued.status_code == 200 and b"Your job is queued" in queued.data and b"Position in the queue:</span> <span id=\"queue-position\">1" in queued.data
	assert client.get("/jobs/{}/figures/neighbors.svg".format(job_id)).status_code == 404
	assert client.get("/download/" + job_id).status_code == 404
	_work(flask_app)
	status = client.get("/status/" + job_id).get_json()
	assert status["status"] == "finished" and status["final"] and status["run_name"] == "webrun" and "TESTAPIKEY123" not in status["log"]
	done = client.get("/results/" + job_id)
	assert done.status_code == 200 and b"Your job is finished" in done.data
	assert b"figures/neighbors.svg" in done.data and b"figures/tree.svg" in done.data and b"figures/tree.pdf" in done.data
	assert b"queries: 2" in done.data and b"ZIP archive" in done.data and b"neighbourhoods.tsv" in done.data
	svg = client.get("/jobs/{}/figures/neighbors.svg".format(job_id))
	assert svg.status_code == 200 and svg.mimetype == "image/svg+xml"
	assert client.get("/jobs/{}/../input.txt".format(job_id)).status_code == 404
	assert client.get("/jobs/{}/report/../../input.txt".format(job_id)).status_code == 404
	archive = client.get("/download/" + job_id)
	assert archive.status_code == 200 and archive.mimetype == "application/zip" and "webrun.zip" in archive.headers["Content-Disposition"]


def test_failed_job_page(client, flask_app):
	page = client.post("/", data={**FORM, "accessions": "WP_FAIL.1"})
	job_id = page.headers["Location"].rsplit("/", 1)[1]
	_work(flask_app)
	done = client.get("/results/" + job_id)
	assert done.status_code == 200 and b"did not finish (failed)" in done.data and b"cannot resolve FAIL" in done.data
	assert client.get("/download/" + job_id).status_code == 404


def test_unknown_job_is_expired_page(client):
	page = client.get("/results/" + "0" * 32)
	assert page.status_code == 404 and b"not here any more" in page.data
	assert client.get("/results/..").status_code == 404 and client.get("/jobs/../input.txt").status_code == 404
	assert client.get("/status/" + "0" * 32).status_code == 404
	assert client.get("/nothing-here").status_code == 404


def test_health(client):
	data = client.get("/health").get_json()
	assert data["status"] == "ok" and data["redis"]
	assert data["features"] == ["tree", "mmseqs", "domains", "defensefinder", "genomad", "plasmidfinder", "sismis"]


def test_job_with_scanners(client, flask_app):
	page = client.post("/", data={**FORM, "tree": "none", "genomad": "1", "defensefinder": "1", "padloc": "1", "scan_range": "30000",
		"rna": "1", "digest": "1", "method": "mmseqs_cluster", "evalue": ""})
	assert page.status_code == 302
	job_id = page.headers["Location"].rsplit("/", 1)[1]
	_work(flask_app)
	status = client.get("/status/" + job_id).get_json()
	assert status["status"] == "finished"
	assert "-df" in status["log"] and "-gn" in status["log"] and "-sr 30000" in status["log"] and "-pl" not in status["log"]
	done = client.get("/results/" + job_id)
	assert b"figures/all-in-one.svg" in done.data and b"report/digest.md" in done.data
	assert "-cr" in status["log"] and "-dg" in status["log"]
	assert "-cm mmseqs_cluster" in status["log"] and " -n " not in status["log"] and "-ce" not in status["log"]
	bad = client.post("/", data={**FORM, "genomad": "1", "scan_range": "7"})
	assert bad.status_code == 400 and b"Must be between 5000 and 200000" in bad.data
