import email.message
import smtplib

TIMEOUT = 30

FINISHED = """Your FlaGs3 job "{run_name}" has finished.

Results: {link}

The page and the downloadable archive stay available for {retention} from now.

Questions or problems: {contact}

FlaGs3, the Atkinson lab
{site}
"""

FAILED = """Your FlaGs3 job "{run_name}" did not finish.

The log on the results page shows how far it got: {link}

The usual causes are an accession that no database can resolve and an NCBI
outage. You can resubmit with the problem lines removed.

If it keeps failing, write to {contact} with the link above.

FlaGs3, the Atkinson lab
{site}
"""


class Mailer:
	def __init__(self, settings):
		self.settings = settings

	@property
	def enabled(self) -> bool:
		s = self.settings
		return bool(s.smtp_host and s.smtp_user and s.email_pass and s.mail_from)

	def message(self, to: str, subject: str, body: str) -> email.message.EmailMessage:
		msg = email.message.EmailMessage()
		msg["Subject"] = subject
		msg["From"] = self.settings.mail_from
		msg["To"] = to
		msg.set_content(body)
		return msg

	def send(self, to: str, subject: str, body: str) -> bool:
		if not self.enabled:
			return False
		s = self.settings
		try:
			with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=TIMEOUT) as server:
				server.starttls()
				server.login(s.smtp_user, s.email_pass)
				server.send_message(self.message(to, subject, body))
		except (OSError, smtplib.SMTPException):
			return False
		return True


class Notice:
	def __init__(self, settings, job_id: str, submission):
		self.settings = settings
		self.job_id = job_id
		self.submission = submission
		self.mailer = Mailer(settings)

	@property
	def wanted(self) -> bool:
		return bool(self.submission.notify) and self.mailer.enabled

	@property
	def link(self) -> str:
		return "{}/results/{}".format(self.settings.site_url, self.job_id)

	def finished(self) -> bool:
		return self._send("FlaGs3 job finished: {}", FINISHED)

	def failed(self) -> bool:
		return self._send("FlaGs3 job failed: {}", FAILED)

	def _send(self, subject: str, template: str) -> bool:
		if not self.wanted:
			return False
		body = template.format(run_name=self.submission.run_name, link=self.link,
			retention=self.settings.retention, site=self.settings.site_url, contact=self.settings.contact_email)
		return self.mailer.send(self.submission.email, subject.format(self.submission.run_name), body)
