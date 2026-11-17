import re

ACCESSION = re.compile(r"^([ANYXW]P_\d+|[A-Z]{3}\d{5,7})(\.\d+)?$")
RESIDUES = set("ACDEFGHIKLMNPQRSTVWYBZXUO")
SEQUENCE_LENGTH = (10, 5000)


class BlastQueries:
	def __init__(self, max_queries: int):
		self.max_queries = max_queries
		self.queries: list[str] = []
		self.error = ""

	def parse(self, raw: str) -> "BlastQueries":
		buffer: list[str] = []
		for line in raw.replace("\r", "").split("\n") + [""]:
			line = line.strip()
			if line.startswith(">") or not line:
				self._flush(buffer)
			elif ACCESSION.match(line) and not buffer:
				self.queries.append(line)
			else:
				buffer.append(line)
		if not self.error and len(self.queries) > self.max_queries:
			self.error = "{} starting proteins given; a job takes at most {}.".format(len(self.queries), self.max_queries)
		return self

	def _flush(self, buffer: list[str]) -> None:
		if not buffer:
			return
		sequence = "".join("".join(buffer).split()).upper().rstrip("*")
		buffer.clear()
		bad = sorted(set(sequence) - RESIDUES)
		low, high = SEQUENCE_LENGTH
		if bad:
			self.error = self.error or "Not a protein accession or a protein sequence: unexpected {}.".format(
				" ".join(_escape(c) for c in bad[:10]))
		elif not low <= len(sequence) <= high:
			self.error = self.error or "A sequence of {} residues; between {} and {} are accepted.".format(len(sequence), low, high)
		else:
			self.queries.append(sequence)


def _escape(text: str) -> str:
	return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
