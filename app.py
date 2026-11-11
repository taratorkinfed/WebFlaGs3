import datetime
import re
import uuid

import flask
import redis
import rq
from rq.job import Job
from rq.exceptions import NoSuchJobError

from config import Settings
from jobs import JobDir, run_job
from submission import Submission, Validator

settings = Settings.load()
app = flask.Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
redis_connection = redis.from_url(settings.redis_url)
queue = rq.Queue(name=settings.queue, connection=redis_connection)
validator = Validator(settings.max_lines, settings.domains_available)

DEMO_FILE = "demo_list.txt"
JOB_ID = re.compile(r"^[0-9a-f]{32}$")


class JobStatus:
	FINAL = ("finished", "failed", "stopped", "canceled")

	def __init__(self, job: Job):
		self.job = job
		self.status = job.get_status(refresh=True)
		self.status = self.status.value if hasattr(self.status, "value") else str(self.status)
		self.meta = job.get_meta(refresh=True)

	@property
	def position(self) -> str:
		ids = queue.job_ids
		return str(ids.index(self.job.id) + 1) if self.job.id in ids else "-"

	@property
	def final(self) -> bool:
		return self.status in self.FINAL

	def stamp(self, name: str) -> str:
		value = getattr(self.job, name)
		return value.strftime("%Y-%m-%d %H:%M UTC") if value else "—"

	@property
	def stored_until(self) -> str:
		if not self.job.ended_at:
			return "—"
		return (self.job.ended_at + datetime.timedelta(hours=settings.results_ttl_hours)).strftime("%Y-%m-%d %H:%M UTC")

	def to_dict(self) -> dict:
		return {"status": self.status, "position": self.position, "log": self.meta.get("log", ""),
			"run_name": self.meta.get("run_name", ""), "final": self.final}


def _page(template: str, **context):
	return flask.render_template(template, settings=settings, **context)


def _fetch(job_id: str):
	if not JOB_ID.match(job_id):
		return None
	try:
		return Job.fetch(job_id, connection=redis_connection)
	except NoSuchJobError:
		return None


def _result(job: Job):
	if job.get_status(refresh=True) != "finished":
		return None
	return job.return_value() if hasattr(job, "return_value") else job.result


def _demo() -> str:
	path = app.root_path + "/static/" + DEMO_FILE
	try:
		with open(path) as handle:
			return handle.read()
	except OSError:
		return ""


@app.route("/", methods=["GET", "POST"])
def index():
	if flask.request.method == "GET":
		submission = Submission()
		if flask.request.args.get("demo"):
			submission.lines = [line for line in _demo().splitlines() if line.strip()]
		return _page("index.html", submission=submission)
	upload = flask.request.files.get("list_file")
	upload_text = upload.read().decode("utf-8", errors="replace") if upload and upload.filename else ""
	submission = validator.parse(flask.request.form, upload_text)
	if not submission.accepted:
		return _page("index.html", submission=submission), 400
	job_id = uuid.uuid4().hex
	JobDir(settings.jobs_dir, job_id).create(submission)
	queue.enqueue(run_job, job_id, job_id=job_id, job_timeout=settings.job_timeout,
		result_ttl=settings.results_ttl, failure_ttl=settings.results_ttl,
		meta={"log": "", "run_name": submission.run_name})
	return flask.redirect(flask.url_for("results", job_id=job_id))


@app.route("/results/<job_id>")
def results(job_id: str):
	job = _fetch(job_id)
	job_dir = JobDir(settings.jobs_dir, job_id)
	if job is None or not job_dir.exists:
		return _page("expired.html"), 404
	status = JobStatus(job)
	figures = job_dir.figures() if status.status == "finished" else []
	return _page("results.html", job_id=job_id, status=status, job_dir=job_dir, figures=figures, pdfs=job_dir.pdfs(),
		summary=job_dir.summary() if status.status == "finished" else "", submission=job_dir.submission())


@app.route("/status/<job_id>")
def status(job_id: str):
	job = _fetch(job_id)
	if job is None:
		return flask.jsonify({"status": "expired", "final": True}), 404
	return flask.jsonify(JobStatus(job).to_dict())


@app.route("/jobs/<job_id>/<path:filepath>")
def served(job_id: str, filepath: str):
	job = _fetch(job_id)
	job_dir = JobDir(settings.jobs_dir, job_id)
	if job is None or job.get_status(refresh=True) != "finished" or not job_dir.run_dir.is_dir():
		flask.abort(404)
	return flask.send_from_directory(job_dir.run_dir, filepath, max_age=3600)


@app.route("/download/<job_id>")
def download(job_id: str):
	job = _fetch(job_id)
	job_dir = JobDir(settings.jobs_dir, job_id)
	result = _result(job) if job else None
	if not isinstance(result, dict) or not job_dir.exists:
		flask.abort(404)
	return flask.send_from_directory(job_dir.path, result["archive"], as_attachment=True)


@app.route("/health")
def health():
	return flask.jsonify({"status": "ok", "redis": bool(redis_connection.ping()), "queued": len(queue),
		"domains": settings.domains_available})


@app.errorhandler(404)
def not_found(error):
	return _page("404.html"), 404


@app.errorhandler(413)
def too_large(error):
	submission = Submission(errors={"accessions": "The uploaded file is larger than 2 MB."})
	return _page("index.html", submission=submission), 413
