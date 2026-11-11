import os
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
}
COMPONENTS = {name for needed in FEATURES.values() for name in needed}
ABSENT = "-"
PROBE_TIMEOUT = 120


class Capabilities:
	def __init__(self, installed):
		self.installed = set(installed)

	def has(self, feature: str) -> bool:
		needed = FEATURES.get(feature)
		return bool(needed) and all(name in self.installed for name in needed)

	@property
	def features(self) -> list[str]:
		return [feature for feature in FEATURES if self.has(feature)]

	@classmethod
	def everything(cls) -> "Capabilities":
		return cls(COMPONENTS)

	@classmethod
	def parse(cls, listing: str) -> "Capabilities":
		installed = set()
		for line in listing.splitlines():
			parts = line.split()
			if len(parts) >= 2 and parts[0] in COMPONENTS and parts[1] != ABSENT:
				installed.add(parts[0])
		return cls(installed)

	@classmethod
	def probe(cls, settings) -> "Capabilities":
		env = dict(os.environ)
		env["FLAGS3_HOME"] = str(settings.flags3_home)
		try:
			done = subprocess.run([settings.flags3_bin, "install"], env=env, capture_output=True, text=True, timeout=PROBE_TIMEOUT)
		except (OSError, subprocess.SubprocessError):
			return cls(())
		return cls.parse(done.stdout)
