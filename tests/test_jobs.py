import os
import time
import zipfile

from config import Settings
from jobs import JobDir, Runner, Sweeper
from submission import Validator


def _submission(text="WP_1.1\nAAC73113.1\tU00096\n", **extra):
	form = {"accessions": text, "gene": "3", "iterations": "2", "evalue": "1e-5", "tree": "tree", "pdf": "1",
		"email": "a@b.cd", "run_name": "demo"}
	form.update(extra)
	return Validator(200, True).parse(form)


def test_runner_produces_run_archive_and_scrubbed_log(workspace):
	settings = Settings.load()
	job_dir = JobDir(settings.jobs_dir, "unit1").create(_submission(domains="1"))
	assert job_dir.list_file.read_text() == "WP_1.1\nAAC73113.1\tU00096\n"
	result = Runner(settings, job_dir).run()
	assert result["archive"] == "demo.zip" and result["figures"] == ["domains.svg", "neighbors.svg", "tree.svg"]
	assert job_dir.pdfs() == {"domains.pdf", "neighbors.pdf", "tree.pdf"}
	log = job_dir.log_file.read_text()
	assert "TESTAPIKEY123" not in log and "-api ***" in log and "a@b.cd" not in log
	assert "-o <job>/run" in log and str(job_dir.path) not in log
	assert "progress 3/3" in log and "progress 1/3" not in log and ">> report" in log
	for name in ("run.tsv", "config.tsv", "console.log"):
		text = (job_dir.run_dir / name).read_text()
		assert "TESTAPIKEY123" not in text and "a@b.cd" not in text and "***" in text, name
	names = zipfile.ZipFile(job_dir.archive("demo")).namelist()
	assert "run/figures/neighbors.svg" in names and "run/report/run_summary.txt" in names and not any(n.startswith("input") for n in names)
	assert job_dir.summary().startswith("queries: 2") and job_dir.report_files() == ["neighbourhoods.tsv", "run_summary.txt"]


def test_runner_failure_raises_and_keeps_log(workspace):
	settings = Settings.load()
	job_dir = JobDir(settings.jobs_dir, "unit2").create(_submission("WP_FAIL.1\n"))
	try:
		Runner(settings, job_dir).run()
	except RuntimeError as error:
		assert "status 1" in str(error)
	else:
		raise AssertionError("expected failure")
	assert "cannot resolve FAIL" in job_dir.log_file.read_text() and not job_dir.archive("demo").exists()


def test_sweeper_removes_only_old_directories(tmp_path):
	old, new = tmp_path / "old", tmp_path / "new"
	old.mkdir(), new.mkdir()
	stale = time.time() - 10 * 3600
	os.utime(old, (stale, stale))
	assert Sweeper(tmp_path, 2).sweep() == ["old"]
	assert not old.exists() and new.exists()
	assert Sweeper(tmp_path / "missing", 2).sweep() == []
