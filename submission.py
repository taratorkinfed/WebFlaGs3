import re
from dataclasses import dataclass, field

TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,59}$")
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
RUN_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
TREE_CHOICES = ("none", "tree", "tree_order")
GENE_RANGE = (1, 20)
ITERATION_RANGE = (1, 10)
EVALUE_RANGE = (1e-100, 1.0)
SCAN_RANGE = (5000, 200000)


@dataclass(frozen=True)
class Scanner:
	name: str
	flag: str
	label: str
	note: str
	windowed: bool = False


SCANNERS = (
	Scanner("defensefinder", "-df", "DefenseFinder", "Anti-phage defence systems among the flanking genes."),
	Scanner("padloc", "-pl", "PadLoc", "Anti-phage defence systems; one both tools agree on is drawn once."),
	Scanner("genomad", "-gn", "geNomad", "Proviruses and plasmid signal in the sequence around each query.", True),
	Scanner("plasmidfinder", "-pf", "PlasmidFinder", "Plasmid replicon types on the contig carrying each query."),
	Scanner("sismis", "-ss", "Sismis", "Secretion systems in the sequence around each query.", True),
)


@dataclass
class Submission:
	lines: list[str] = field(default_factory=list)
	gene: int = 4
	iterations: int = 3
	evalue: float = 1e-10
	tree: str = "none"
	domains: bool = False
	scanners: list[str] = field(default_factory=list)
	scan_range: int = 20000
	pdf: bool = True
	email: str = ""
	run_name: str = "flags3_run"
	errors: dict[str, str] = field(default_factory=dict)
	raw: str = ""

	@property
	def accepted(self) -> bool:
		return not self.errors

	@property
	def list_text(self) -> str:
		return self.raw if self.errors else "\n".join(self.lines)

	def to_dict(self) -> dict:
		return {k: v for k, v in self.__dict__.items() if k not in ("errors", "raw")}

	@classmethod
	def from_dict(cls, values: dict) -> "Submission":
		return cls(**{k: v for k, v in values.items() if k in cls.__dataclass_fields__})


class Validator:
	def __init__(self, max_lines: int, capabilities):
		self.max_lines = max_lines
		self.capabilities = capabilities

	def parse(self, form, upload_text: str = "") -> Submission:
		s = Submission()
		s.raw = upload_text if upload_text.strip() else form.get("accessions", "")
		s.lines, line_error = self._lines(s.raw)
		if line_error:
			s.errors["accessions"] = line_error
		s.gene = self._integer(form, "gene", s.gene, GENE_RANGE, s.errors)
		s.iterations = self._integer(form, "iterations", s.iterations, ITERATION_RANGE, s.errors)
		s.evalue = self._float(form, "evalue", s.evalue, EVALUE_RANGE, s.errors)
		s.tree = form.get("tree", "none")
		if s.tree not in TREE_CHOICES:
			s.errors["tree"] = "Unknown tree option."
		elif not self.capabilities.has("tree"):
			s.tree = "none"
		s.domains = bool(form.get("domains")) and self.capabilities.has("domains")
		s.scanners = [sc.name for sc in SCANNERS if form.get(sc.name) and self.capabilities.has(sc.name)]
		s.scan_range = self._integer(form, "scan_range", s.scan_range, SCAN_RANGE, s.errors)
		s.pdf = bool(form.get("pdf"))
		s.email = form.get("email", "").strip()
		if not EMAIL.match(s.email):
			s.errors["email"] = "A valid email address is required: NCBI asks for one with every request FlaGs3 makes on your behalf."
		s.run_name = form.get("run_name", "").strip() or "flags3_run"
		if not RUN_NAME.match(s.run_name):
			s.errors["run_name"] = "Letters, digits, '-' and '_' only, up to 40 characters."
		return s

	def _lines(self, raw: str) -> tuple[list[str], str]:
		lines = []
		bad = []
		for line in raw.replace("\r", "").split("\n"):
			line = line.strip()
			if not line or line.startswith("#"):
				continue
			tokens = line.split()
			if len(tokens) > 2 or not all(TOKEN.match(t) for t in tokens):
				bad.append(line)
				continue
			lines.append("\t".join(tokens))
		if bad:
			shown = ", ".join("<b>{}</b>".format(_escape(b)) for b in bad[:5])
			more = " and {} more".format(len(bad) - 5) if len(bad) > 5 else ""
			return lines, "These lines are not an accession or an accession–assembly pair: {}{}.".format(shown, more)
		if not lines:
			return lines, "Give at least one protein accession."
		if len(lines) > self.max_lines:
			return lines, "{} queries given; the server takes at most {} per job.".format(len(lines), self.max_lines)
		return lines, ""

	@staticmethod
	def _integer(form, key, default, bounds, errors) -> int:
		try:
			value = int(form.get(key, default))
		except (TypeError, ValueError):
			errors[key] = "Must be a whole number."
			return default
		if not bounds[0] <= value <= bounds[1]:
			errors[key] = "Must be between {} and {}.".format(*bounds)
		return value

	@staticmethod
	def _float(form, key, default, bounds, errors) -> float:
		try:
			value = float(form.get(key, default))
		except (TypeError, ValueError):
			errors[key] = "Must be a number such as 1e-10."
			return default
		if not bounds[0] <= value <= bounds[1]:
			errors[key] = "Must be between {:g} and {:g}.".format(*bounds)
		return value


def _escape(text: str) -> str:
	return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Command:
	def __init__(self, settings, submission: Submission, list_path: str, run_dir: str):
		self.settings = settings
		self.submission = submission
		self.list_path = list_path
		self.run_dir = run_dir

	def argv(self) -> list[str]:
		s, sub = self.settings, self.submission
		argv = [s.flags3_bin, "run", "-i", self.list_path, "-o", self.run_dir, "-nt",
			"-u", sub.email, "-g", str(sub.gene), "-n", str(sub.iterations), "-ce", "{:g}".format(sub.evalue),
			"-c", str(s.cpu_per_job), "-cm", "jackhmmer"]
		if s.ncbi_api_key:
			argv += ["-api", s.ncbi_api_key]
		if sub.tree == "tree":
			argv.append("-t")
		elif sub.tree == "tree_order":
			argv.append("-to")
		if sub.domains:
			argv.append("-d")
		chosen = [sc for sc in SCANNERS if sc.name in sub.scanners]
		argv += [sc.flag for sc in chosen]
		if any(sc.windowed for sc in chosen):
			argv += ["-sr", str(sub.scan_range)]
		if sub.pdf:
			argv.append("-pdf")
		return argv

	def environment(self, base: dict) -> dict:
		env = dict(base)
		env["FLAGS3_HOME"] = str(self.settings.flags3_home)
		env["PYTHONUNBUFFERED"] = "1"
		return env
