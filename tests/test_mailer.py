from config import Settings
from mailer import Mailer, Notice
from submission import Submission

MAIL = {"smtp_user": "robot@example.org", "mail_from": "lab@example.org", "email_pass": "pw", "site_url": "https://flags.example.org/",
	"results_ttl_hours": "120"}


def test_mail_is_off_without_credentials(smtp):
	for missing in ("smtp_user", "mail_from", "email_pass"):
		settings = Settings({k: v for k, v in MAIL.items() if k != missing})
		assert not Mailer(settings).enabled
		assert not Mailer(settings).send("a@b.cd", "s", "b")
		assert not Notice(settings, "j1", Submission(email="a@b.cd")).finished()
	assert smtp.sent == []


def test_finished_and_failed_notices(smtp):
	settings = Settings(MAIL)
	sub = Submission(email="user@lab.se", run_name="my_run")
	notice = Notice(settings, "abc123", sub)
	assert notice.finished() and notice.failed()
	(host, port, user, password, first), (_, _, _, _, second) = smtp.sent
	assert (host, port, user, password) == ("smtps.lu.se", 587, "robot@example.org", "pw")
	assert first["To"] == "user@lab.se" and first["From"] == "lab@example.org" and first["Subject"] == "FlaGs3 job finished: my_run"
	body = first.get_content()
	assert "https://flags.example.org/results/abc123" in body and "5 days" in body and '"my_run"' in body
	assert second["Subject"] == "FlaGs3 job failed: my_run" and "did not finish" in second.get_content()


def test_opt_out_and_smtp_failure(smtp):
	settings = Settings(MAIL)
	assert not Notice(settings, "j", Submission(email="u@l.se", notify=False)).finished()
	smtp.fail = True
	assert not Notice(settings, "j", Submission(email="u@l.se")).finished()
	assert smtp.sent == []
