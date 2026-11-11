from config import Settings
from submission import Command, Validator


def _form(**overrides):
	base = {"accessions": "WP_000001.1\nAAC73113.1\tU00096\n# comment\n", "gene": "4", "iterations": "3",
		"evalue": "1e-10", "tree": "none", "pdf": "1", "email": "fed@example.org", "run_name": "my_run"}
	base.update(overrides)
	return base


def test_good_form_is_accepted():
	s = Validator(200, True).parse(_form())
	assert s.accepted and s.lines == ["WP_000001.1", "AAC73113.1\tU00096"]
	assert s.gene == 4 and s.iterations == 3 and s.evalue == 1e-10 and s.pdf and not s.domains
	assert s.run_name == "my_run" and s.email == "fed@example.org"


def test_upload_replaces_textarea_and_whitespace_is_normalised():
	s = Validator(200, True).parse(_form(), "  AAC73113.1    U00096 \r\n\r\nWP_1.1\n")
	assert s.lines == ["AAC73113.1\tU00096", "WP_1.1"]


def test_bad_lines_and_limits():
	s = Validator(2, True).parse(_form(accessions="WP_1.1\nbad line here\n<script>\n"))
	assert "accessions" in s.errors and "<b>bad line here</b>" in s.errors["accessions"] and "&lt;script&gt;" in s.errors["accessions"]
	assert s.list_text == "WP_1.1\nbad line here\n<script>\n"
	s = Validator(2, True).parse(_form(accessions="only bad line\n"))
	assert "<b>only bad line</b>" in s.errors["accessions"]
	s = Validator(2, True).parse(_form(accessions="A1\nA2\nA3\n"))
	assert "at most 2" in s.errors["accessions"]
	s = Validator(2, True).parse(_form(accessions="\n# only\n"))
	assert "at least one" in s.errors["accessions"]


def test_field_errors():
	s = Validator(200, True).parse(_form(gene="0", iterations="x", evalue="5", tree="weird", email="nope", run_name="bad name!"))
	assert set(s.errors) == {"gene", "iterations", "evalue", "tree", "email", "run_name"}
	assert s.gene == 0 and s.iterations == 3 and s.evalue == 5.0


def test_domains_only_when_available():
	assert not Validator(200, False).parse(_form(domains="1")).domains
	assert Validator(200, True).parse(_form(domains="1")).domains


def test_command_argv(tmp_path):
	settings = Settings({"flags3_bin": "/opt/flags3", "flags3_home": str(tmp_path), "ncbi_api_key": "KEY", "cpu_per_job": "6"})
	s = Validator(200, True).parse(_form(tree="tree_order", domains="1", pdf=""))
	argv = Command(settings, s, "/j/input.txt", "/j/run").argv()
	assert argv[:7] == ["/opt/flags3", "run", "-i", "/j/input.txt", "-o", "/j/run", "-nt"]
	assert argv[argv.index("-u") + 1] == "fed@example.org" and argv[argv.index("-api") + 1] == "KEY"
	assert argv[argv.index("-c") + 1] == "6" and "-to" in argv and "-t" not in argv and "-d" in argv and "-pdf" not in argv
	assert argv[argv.index("-ce") + 1] == "1e-10" and argv[argv.index("-cm") + 1] == "jackhmmer"
	env = Command(settings, s, "a", "b").environment({"PATH": "/bin"})
	assert env["FLAGS3_HOME"] == str(tmp_path) and env["PATH"] == "/bin"
	settings = Settings({"flags3_bin": "/opt/flags3", "flags3_home": str(tmp_path)})
	assert "-api" not in Command(settings, s, "a", "b").argv()
