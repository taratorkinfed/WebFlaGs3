from capabilities import Capabilities
from config import Settings
from submission import Command, Validator

ALL = Capabilities.everything()
NONE = Capabilities(())


def _form(**overrides):
	base = {"accessions": "WP_000001.1\nAAC73113.1\tU00096\n# comment\n", "gene": "4", "iterations": "3",
		"evalue": "1e-10", "tree": "none", "pdf": "1", "email": "fed@example.org", "run_name": "my_run"}
	base.update(overrides)
	return base


def test_good_form_is_accepted():
	s = Validator(200, ALL).parse(_form())
	assert s.accepted and s.lines == ["WP_000001.1", "AAC73113.1\tU00096"]
	assert s.gene == 4 and s.iterations == 3 and s.evalue == 1e-10 and s.pdf and not s.domains and s.method == "jackhmmer"
	assert s.run_name == "my_run" and s.email == "fed@example.org"


def test_upload_replaces_textarea_and_whitespace_is_normalised():
	s = Validator(200, ALL).parse(_form(), "  AAC73113.1    U00096 \r\n\r\nWP_1.1\n")
	assert s.lines == ["AAC73113.1\tU00096", "WP_1.1"]


def test_bad_lines_and_limits():
	s = Validator(2, ALL).parse(_form(accessions="WP_1.1\nbad line here\n<script>\n"))
	assert "accessions" in s.errors and "<b>bad line here</b>" in s.errors["accessions"] and "&lt;script&gt;" in s.errors["accessions"]
	assert s.list_text == "WP_1.1\nbad line here\n<script>\n"
	s = Validator(2, ALL).parse(_form(accessions="only bad line\n"))
	assert "<b>only bad line</b>" in s.errors["accessions"]
	s = Validator(2, ALL).parse(_form(accessions="A1\nA2\nA3\n"))
	assert "at most 2" in s.errors["accessions"]
	s = Validator(2, ALL).parse(_form(accessions="\n# only\n"))
	assert "at least one" in s.errors["accessions"]


def test_field_errors():
	s = Validator(200, ALL).parse(_form(gene="0", iterations="x", evalue="5", tree="weird", email="nope", run_name="bad name!"))
	assert set(s.errors) == {"gene", "iterations", "evalue", "tree", "email", "run_name"}
	assert s.gene == 0 and s.iterations == 3 and s.evalue == 5.0
	s = Validator(200, ALL).parse(_form(evalue="tiny", method="phmmer"))
	assert set(s.errors) == {"evalue", "method"}


def test_extras_only_when_installed():
	asked = _form(domains="1", tree="tree", genomad="1", padloc="1", defensefinder="1", plasmidfinder="1", sismis="1")
	bare = Validator(200, NONE).parse(asked)
	assert bare.accepted and not bare.domains and bare.tree == "none" and bare.scanners == []
	full = Validator(200, ALL).parse(asked)
	assert full.domains and full.tree == "tree"
	assert full.scanners == ["defensefinder", "padloc", "genomad", "plasmidfinder", "sismis"]
	some = Validator(200, Capabilities({"genomad", "plasmidfinder"})).parse(asked)
	assert some.scanners == ["genomad"]
	assert Validator(200, Capabilities({"plasmidfinder", "core"})).parse(asked).scanners == ["plasmidfinder"]


def test_clustering_method_and_defaults(tmp_path):
	settings = Settings({"flags3_bin": "/opt/flags3", "flags3_home": str(tmp_path)})
	s = Validator(200, ALL).parse(_form(evalue="", iterations="5"))
	argv = Command(settings, s, "a", "b").argv()
	assert s.evalue is None and "-ce" not in argv
	assert argv[argv.index("-cm") + 1] == "jackhmmer" and argv[argv.index("-n") + 1] == "5"
	s = Validator(200, ALL).parse(_form(method="mmseqs_cluster", evalue="", iterations="5"))
	argv = Command(settings, s, "a", "b").argv()
	assert argv[argv.index("-cm") + 1] == "mmseqs_cluster" and "-n" not in argv and "-ce" not in argv
	s = Validator(200, ALL).parse(_form(method="mmseqs_cluster", evalue="1e-5"))
	argv = Command(settings, s, "a", "b").argv()
	assert argv[argv.index("-ce") + 1] == "1e-05" and "-n" not in argv
	s = Validator(200, NONE).parse(_form(method="mmseqs_cluster"))
	assert s.accepted and s.method == "jackhmmer"


def test_capabilities_parse_the_install_listing():
	listing = "core           installed  -      tools\npfam           -          -      Pfam\nsismis         on PATH    -      Sismis\n" \
		"plasmidfinder  2.1.6      -      db\nsignalp        installed  6.0    licensed\n\nversions recorded in /x/versions.tsv\n"
	caps = Capabilities.parse(listing)
	assert caps.installed == {"core", "sismis", "plasmidfinder"}
	assert caps.features == ["tree", "plasmidfinder", "sismis"]
	assert Capabilities.parse("").features == []


def test_scan_range_bounds_and_argv(tmp_path):
	settings = Settings({"flags3_bin": "/opt/flags3", "flags3_home": str(tmp_path)})
	s = Validator(200, ALL).parse(_form(defensefinder="1", plasmidfinder="1"))
	argv = Command(settings, s, "a", "b").argv()
	assert "-df" in argv and "-pf" in argv and "-sr" not in argv and "-gn" not in argv
	assert "-cr" not in argv and "-dg" not in argv
	s = Validator(200, ALL).parse(_form(genomad="1", sismis="1", scan_range="50000", rna="1", digest="1"))
	argv = Command(settings, s, "a", "b").argv()
	assert "-gn" in argv and "-ss" in argv and argv[argv.index("-sr") + 1] == "50000"
	assert "-cr" in argv and "-dg" in argv and s.rna and s.digest
	assert "scan_range" in Validator(200, ALL).parse(_form(scan_range="100")).errors
	assert "scan_range" in Validator(200, ALL).parse(_form(scan_range="lots")).errors


def test_command_argv(tmp_path):
	settings = Settings({"flags3_bin": "/opt/flags3", "flags3_home": str(tmp_path), "ncbi_api_key": "KEY", "cpu_per_job": "6"})
	s = Validator(200, ALL).parse(_form(tree="tree_order", domains="1", pdf=""))
	argv = Command(settings, s, "/j/input.txt", "/j/run").argv()
	assert argv[:7] == ["/opt/flags3", "run", "-i", "/j/input.txt", "-o", "/j/run", "-nt"]
	assert argv[argv.index("-u") + 1] == "fed@example.org" and argv[argv.index("-api") + 1] == "KEY"
	assert argv[argv.index("-c") + 1] == "6" and "-to" in argv and "-t" not in argv and "-d" in argv and "-pdf" not in argv
	assert argv[argv.index("-ce") + 1] == "1e-10" and argv[argv.index("-cm") + 1] == "jackhmmer"
	env = Command(settings, s, "a", "b").environment({"PATH": "/bin"})
	assert env["FLAGS3_HOME"] == str(tmp_path) and env["PATH"] == "/bin" and env["PYTHONUNBUFFERED"] == "1"
	settings = Settings({"flags3_bin": "/opt/flags3", "flags3_home": str(tmp_path)})
	assert "-api" not in Command(settings, s, "a", "b").argv()
