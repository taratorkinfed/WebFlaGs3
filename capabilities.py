import os
import re
import subprocess

FEATURES = {
	"tree": ("core",),
	"mmseqs": ("mmseqs",),
	"domains": ("pfam",),
	"defensefinder": ("defensefinder",),
	"padloc": ("padloc",),
	"genomad": ("genomad",),
	"plasmidfinder": ("plasmidfinder", "core"),
	"sismis": ("sismis",),
	"blast": ("core", "blastdb"),
	"synteny": ("core",),
}
SINCE = {
	"clusters_legend": (3, 6, 0),
	"blast": (3, 7, 0),
	"synteny": (3, 8, 0),
}
BLAST_DATABASE = "blastdb"
DATABASE_FILES = (".pal", ".pin")
COMPONENTS = {name for needed in FEATURES.values() for name in needed}
ABSENT = "-"
PROBE_TIMEOUT = 120
VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")
UNKNOWN = (0, 0, 0)


class Capabilities:
	def __init__(self, installed, version: tuple = UNKNOWN):
		self.installed = set(installed)
		self.version = tuple(version)

	def has(self, feature: str) -> bool:
		if feature not in FEATURES and feature not in SINCE:
			return False
		if self.version < SINCE.get(feature, UNKNOWN):
			return False
		return all(name in self.installed for name in FEATURES.get(feature, ()))

	@property
	def features(self) -> list[str]:
		return [feature for feature in dict.fromkeys(list(FEATURES) + list(SINCE)) if self.has(feature)]

	@property
	def version_text(self) -> str:
		return ".".join(str(n) for n in self.version) if self.version != UNKNOWN else "unknown"

	@classmethod
	def everything(cls) -> "Capabilities":
		return cls(COMPONENTS, max(SINCE.values()))

	@classmethod
	def parse(cls, listing: str, version_line: str = "") -> "Capabilities":
		installed = set()
		for line in listing.splitlines():
			parts = line.split()
			if len(parts) >= 2 and parts[0] in COMPONENTS and parts[1] != ABSENT:
				installed.add(parts[0])
		match = VERSION.search(version_line)
		return cls(installed, tuple(int(n) for n in match.groups()) if match else UNKNOWN)

	@classmethod
	def probe(cls, settings) -> "Capabilities":
		env = dict(os.environ)
		env["FLAGS3_HOME"] = str(settings.flags3_home)
		found = cls.parse(cls._output(settings, env, "install"), cls._output(settings, env, "--version"))
		if settings.blast_db and any(os.path.isfile(settings.blast_db + suffix) for suffix in DATABASE_FILES):
			found.installed.add(BLAST_DATABASE)
		return found

	@staticmethod
	def _output(settings, env, argument: str) -> str:
		try:
			done = subprocess.run([settings.flags3_bin, argument], env=env, capture_output=True, text=True, timeout=PROBE_TIMEOUT)
		except (OSError, subprocess.SubprocessError):
			return ""
		return done.stdout
