import hashlib
from typing import Optional

from rq.exceptions import NoSuchJobError
from rq.job import Job

ACTIVE = ("queued", "started", "deferred", "scheduled")
KEY_TTL = 7 * 24 * 3600
ADDRESS = "address"
EMAIL = "email"
WORDS = {ADDRESS: "this address", EMAIL: "this email address"}


class ActiveJobs:
	def __init__(self, connection, namespace: str):
		self.connection = connection
		self.namespace = namespace

	def key(self, kind: str, value: str) -> str:
		digest = hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()[:32]
		return "{}:active:{}:{}".format(self.namespace, kind, digest)

	def count(self, kind: str, value: str) -> int:
		key = self.key(kind, value)
		alive = 0
		for raw in self.connection.smembers(key):
			job_id = raw.decode() if isinstance(raw, bytes) else raw
			if self._active(job_id):
				alive += 1
			else:
				self.connection.srem(key, job_id)
		return alive

	def add(self, kind: str, value: str, job_id: str) -> None:
		key = self.key(kind, value)
		self.connection.sadd(key, job_id)
		self.connection.expire(key, KEY_TTL)

	def _active(self, job_id: str) -> bool:
		try:
			status = Job.fetch(job_id, connection=self.connection).get_status(refresh=True)
		except NoSuchJobError:
			return False
		status = status.value if hasattr(status, "value") else str(status)
		return status in ACTIVE


class BlastLimit:
	def __init__(self, connection, namespace: str, limit: int):
		self.jobs = ActiveJobs(connection, namespace + ":blast")
		self.limit = limit

	def refusal(self, address: str, email: str) -> Optional[str]:
		if self.limit <= 0:
			return None
		for kind, value in ((ADDRESS, address), (EMAIL, email)):
			if value and self.jobs.count(kind, value) >= self.limit:
				return ("{} BlastP jobs from {} are already queued or running, which is the most allowed at a time. "
					"Submit again when one has finished; jobs without BlastP are not limited.").format(self.limit, WORDS[kind])
		return None

	def record(self, address: str, email: str, job_id: str) -> None:
		for kind, value in ((ADDRESS, address), (EMAIL, email)):
			if value:
				self.jobs.add(kind, value, job_id)
