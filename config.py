import os
from pathlib import Path

import dotenv

DEFAULTS = {
	"flags3_bin": "/var/www/flags3/venv/bin/flags3",
	"flags3_home": "/var/www/flags3/home",
	"jobs_dir": "/home/webapp/flags3_web/jobs",
	"ncbi_api_key": "",
	"redis_url": "redis://localhost:6379/0",
	"queue": "flags3",
	"results_ttl_hours": "120",
	"job_timeout": "3h",
	"cpu_per_job": "4",
	"max_lines": "200",
	"lab_url": "https://server.atkinson-lab.com",
	"site_name": "FlaGs3",
	"site_url": "https://flags.atkinson-lab.com",
	"contact_email": "fedor.taratorkin@med.lu.se",
	"smtp_host": "smtps.lu.se",
	"smtp_port": "587",
	"smtp_user": "",
	"mail_from": "",
	"email_pass": "",
}


class Settings:
	def __init__(self, values: dict):
		merged = {**DEFAULTS, **{k: v for k, v in values.items() if v is not None}}
		self.flags3_bin = merged["flags3_bin"]
		self.flags3_home = Path(merged["flags3_home"])
		self.jobs_dir = Path(merged["jobs_dir"])
		self.ncbi_api_key = merged["ncbi_api_key"]
		self.redis_url = merged["redis_url"]
		self.queue = merged["queue"]
		self.results_ttl_hours = int(merged["results_ttl_hours"])
		self.job_timeout = merged["job_timeout"]
		self.cpu_per_job = int(merged["cpu_per_job"])
		self.max_lines = int(merged["max_lines"])
		self.lab_url = merged["lab_url"].rstrip("/")
		self.site_name = merged["site_name"]
		self.site_url = merged["site_url"].rstrip("/")
		self.contact_email = merged["contact_email"]
		self.smtp_host = merged["smtp_host"]
		self.smtp_port = int(merged["smtp_port"])
		self.smtp_user = merged["smtp_user"]
		self.mail_from = merged["mail_from"]
		self.email_pass = merged["email_pass"]

	@property
	def results_ttl(self) -> str:
		return "{}h".format(self.results_ttl_hours)

	@property
	def retention(self) -> str:
		hours = self.results_ttl_hours
		if hours % 24 == 0 and hours >= 48:
			return "{} days".format(hours // 24)
		return "{} hour{}".format(hours, "" if hours == 1 else "s")

	@property
	def genomes_dir(self) -> Path:
		return self.flags3_home / "genomes"

	@classmethod
	def load(cls, path: str = "") -> "Settings":
		env_file = path or os.environ.get("FLAGS3_WEB_ENV", str(Path(__file__).with_name(".env")))
		values = dotenv.dotenv_values(env_file) if Path(env_file).is_file() else {}
		return cls(values)
