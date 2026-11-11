import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import rq

from config import Settings
from submission import Command, Submission

LOG_LIMIT = 200_000
SAVE_INTERVAL = 0.5
SCRUBBED_FILES = ("run.tsv", "config.tsv", "console.log")


class JobDir:
	def __init__(self, root: Path, job_id: str):
		self.root = Path(root)
		self.job_id = job_id
		self.path = self.root / job_id

	@property
	def list_file(self) -> Path:
		return self.path / "input.txt"

	@property
	def request_file(self) -> Path:
		return self.path / "request.json"

	@property
	def run_dir(self) -> Path:
		return self.path / "run"

	@property
	def log_file(self) -> Path:
		return self.path / "log.txt"

	@property
	def figures_dir(self) -> Path:
		return self.run_dir / "figures"

	@property
	def report_dir(self) -> Path:
		return self.run_dir / "report"

	@property
	def exists(self) -> bool:
		return self.path.is_dir()

	def archive(self, run_name: str) -> Path:
		return self.path / (run_name + ".zip")

	def create(self, submission: Submission) -> "JobDir":
		self.path.mkdir(parents=True, exist_ok=False)
		self.list_file.write_text(submission.list_text + "\n")
		self.request_file.write_text(json.dumps(submission.to_dict(), indent=1))
		return self

	def submission(self) -> Submission:
		return Submission.from_dict(json.loads(self.request_file.read_text()))

	def figures(self) -> list[str]:
		if not self.figures_dir.is_dir():
			return []
		return sorted(p.name for p in self.figures_dir.iterdir() if p.suffix == ".svg" and p.is_file())

	def pdfs(self) -> set[str]:
		if not self.figures_dir.is_dir():
			return set()
		return {p.name for p in self.figures_dir.iterdir() if p.suffix == ".pdf"}

	def report_files(self) -> list[str]:
		if not self.report_dir.is_dir():
			return []
		return sorted(p.name for p in self.report_dir.iterdir() if p.is_file())

	def summary(self) -> str:
		path = self.report_dir / "run_summary.txt"
		return path.read_text(errors="replace") if path.is_file() else ""

	def served_file(self, relative: str) -> Path:
		return self.run_dir / relative


class LogSink:
	def __init__(self, job, replacements: list[tuple[str, str]]):
		self.job = job
		self.replacements = [(old, new) for old, new in replacements if old]
		self.text = ""
		self.saved_at = 0.0

	def add(self, line: str) -> None:
		line = line.rstrip("\n").split("\r")[-1]
		for old, new in self.replacements:
			line = line.replace(old, new)
		if not line.strip():
			return
		self.text += line + "\n"
		if len(self.text) > LOG_LIMIT:
			self.text = self.text[-LOG_LIMIT:]
		self.save()

	def save(self, force: bool = False) -> None:
		now = time.monotonic()
		if self.job is None:
			return
		if force or now - self.saved_at >= SAVE_INTERVAL:
			self.job.meta["log"] = self.text
			self.job.save_meta()
			self.saved_at = now


class Scrubber:
	def __init__(self, secrets: list[str]):
		self.secrets = [s for s in secrets if s]

	def scrub(self, directory: Path) -> list[str]:
		touched = []
		for name in SCRUBBED_FILES:
			path = directory / name
			if not path.is_file():
				continue
			text = path.read_text(errors="replace")
			clean = text
			for secret in self.secrets:
				clean = clean.replace(secret, "***")
			if clean != text:
				path.write_text(clean)
				touched.append(name)
		return touched


class Runner:
	def __init__(self, settings: Settings, job_dir: JobDir, job=None):
		self.settings = settings
		self.job_dir = job_dir
		self.job = job

	def run(self) -> dict:
		submission = self.job_dir.submission()
		command = Command(self.settings, submission, str(self.job_dir.list_file), str(self.job_dir.run_dir))
		sink = LogSink(self.job, [(self.settings.ncbi_api_key, "***"), (submission.email, "***"),
			(str(self.job_dir.path), "<job>")])
		if self.job is not None:
			self.job.meta["run_name"] = submission.run_name
			self.job.save_meta()
		try:
			code = self._execute(command, sink)
		finally:
			Scrubber([self.settings.ncbi_api_key, submission.email]).scrub(self.job_dir.run_dir)
		sink.save(force=True)
		self.job_dir.log_file.write_text(sink.text)
		if code != 0:
			raise RuntimeError("flags3 exited with status {}".format(code))
		archive = self._archive(submission.run_name)
		return {"run_name": submission.run_name, "archive": archive.name, "figures": self.job_dir.figures()}

	def _execute(self, command: Command, sink: LogSink) -> int:
		process = subprocess.Popen(command.argv(), cwd=str(self.job_dir.path), env=command.environment(os.environ),
			stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		try:
			for raw in process.stdout:
				sink.add(raw.decode("utf-8", errors="replace"))
			return process.wait()
		except BaseException:
			process.kill()
			process.wait()
			raise

	def _archive(self, run_name: str) -> Path:
		target = self.job_dir.archive(run_name)
		shutil.make_archive(str(target.with_suffix("")), "zip", root_dir=str(self.job_dir.path), base_dir="run")
		return target


class Sweeper:
	def __init__(self, root: Path, ttl_hours: int):
		self.root = Path(root)
		self.ttl_seconds = ttl_hours * 3600

	def sweep(self) -> list[str]:
		removed = []
		if not self.root.is_dir():
			return removed
		cutoff = time.time() - self.ttl_seconds
		for entry in os.scandir(self.root):
			if entry.is_dir(follow_symlinks=False) and entry.stat().st_mtime < cutoff:
				shutil.rmtree(entry.path, ignore_errors=True)
				removed.append(entry.name)
		return removed


def run_job(job_id: str) -> dict:
	settings = Settings.load()
	Sweeper(settings.jobs_dir, settings.results_ttl_hours).sweep()
	job = rq.get_current_job()
	return Runner(settings, JobDir(settings.jobs_dir, job_id), job).run()
