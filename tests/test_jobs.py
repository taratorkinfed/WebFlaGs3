import os
import time
import zipfile

from config import Settings
from jobs import JobDir, Runner, Scrubber, Sweeper
from capabilities import Capabilities
from submission import Validator


def _submission(text="WP_1.1\nAAC73113.1\tU00096\n", **extra):
	form = {"accessions": text, "gene": "3", "iterations": "2", "evalue": "1e-5", "tree": "tree", "pdf": "1",
		"email": "a@b.cd", "run_name": "demo"}
	form.update(extra)
	return Validator(200, Capabilities.everything()).parse(form)


def test_runner_produces_run_archive_and_scrubbed_log(workspace):
	settings = Settings.load()
	job_dir = JobDir(settings.jobs_dir, "unit1").create(_submission(domains="1"))
	assert job_dir.list_file.read_text() == "WP_1.1\nAAC73113.1\tU00096\n"
	result = Runner(settings, job_dir).run()
	assert result["archive"] == "demo.zip" and result["figures"] == ["domains.svg", "neighbors.svg", "tree.svg"]
	views = {v.title: v for v in job_dir.figure_views()}
	assert views["tree"].pdf == "tree.pdf" and views["tree"].clusters_legend == "protein_clusters_legend.txt"
	assert views["neighbors"].clusters_legend and views["domains"].clusters_legend is None
	assert all(v.systems_summary is None for v in views.values())
	log = job_dir.log_file.read_text()
	assert "TESTAPIKEY123" not in log and "-api" not in log and "ncbi key: environment" in log and "a@b.cd" not in log
	assert "-o <job>/run" in log and str(job_dir.path) not in log
	assert "progress 3/3" in log and "progress 1/3" not in log and ">> report" in log
	archive = zipfile.ZipFile(job_dir.archive("demo"))
	for name in archive.namelist():
		text = archive.read(name).decode("utf-8", errors="replace")
		assert "TESTAPIKEY123" not in text and "a@b.cd" not in text, name
	for name in ("run.tsv", "config.tsv", "report/run_summary.txt"):
		assert "-u ***" in (job_dir.run_dir / name).read_text() or "user_email\t***" in (job_dir.run_dir / name).read_text(), name
	names = archive.namelist()
	assert "run/figures/neighbors.svg" in names and "run/report/run_summary.txt" in names and not any(n.startswith("input") for n in names)
	assert "queries: 2" in job_dir.summary() and job_dir.report_files() == ["neighbourhoods.tsv", "run_summary.txt"]


def test_scrubber_cleans_every_listed_file(tmp_path):
	(tmp_path / "report").mkdir()
	for name in ("run.tsv", "config.tsv", "console.log", "report/run_summary.txt", "report/digest.md"):
		(tmp_path / name).write_text("command: flags3 run -u me@lab.se -api SECRETKEY\n")
	(tmp_path / "report" / "other.tsv").write_text("me@lab.se\n")
	touched = Scrubber(["SECRETKEY", "me@lab.se", ""]).scrub(tmp_path)
	assert sorted(touched) == ["config.tsv", "console.log", "report/digest.md", "report/run_summary.txt", "run.tsv"]
	for name in touched:
		assert (tmp_path / name).read_text() == "command: flags3 run -u *** -api ***\n"
	assert (tmp_path / "report" / "other.tsv").read_text() == "me@lab.se\n"


def test_figure_views_for_parts_and_systems(tmp_path):
	job_dir = JobDir(tmp_path, "j")
	job_dir.figures_dir.mkdir(parents=True)
	for name in ("neighbors_part1.svg", "neighbors_part2.svg", "neighbors.pdf", "all-in-one.svg", "defence.svg", "classic.svg",
			"protein_clusters_legend.txt", "systems_summary.txt"):
		(job_dir.figures_dir / name).write_text("x")
	views = {v.title: v for v in job_dir.figure_views()}
	assert list(views) == ["all-in-one", "classic", "defence", "neighbors_part1", "neighbors_part2"]
	assert views["neighbors_part2"].pdf == "neighbors.pdf" and views["neighbors_part2"].clusters_legend
	assert views["all-in-one"].clusters_legend and views["all-in-one"].systems_summary and views["all-in-one"].pdf is None
	assert views["defence"].systems_summary and views["defence"].clusters_legend is None
	assert views["classic"].clusters_legend and views["classic"].systems_summary is None
	(job_dir.figures_dir / "systems_summary.txt").unlink()
	assert all(v.systems_summary is None for v in job_dir.figure_views())


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
