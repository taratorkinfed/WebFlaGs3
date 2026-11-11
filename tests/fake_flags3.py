#!/usr/bin/env python3
import argparse
import sys
import time
from pathlib import Path

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="40"><text x="5" y="25">{}</text></svg>\n'


LISTING = """core           installed  -                       mafft, trimal, VeryFastTree
pfam           installed  38.0                    Pfam-A HMMs
interpro       -          -                       InterPro metadata table
mmseqs         installed  18-8cc5c                MMseqs2
genomad        installed  1.12.0 / db 1.9         geNomad and its database
plasmidfinder  2.1.6      -                       PlasmidFinder replicon database
defensefinder  installed  3.0.0                   DefenseFinder
padloc         -          -                       PadLoc
sismis         on PATH    -                       Sismis
"""


def main() -> int:
	if sys.argv[1:2] == ["install"]:
		print(LISTING, end="")
		return 0
	parser = argparse.ArgumentParser()
	parser.add_argument("command")
	parser.add_argument("-i", action="append", default=[])
	parser.add_argument("-o", required=True)
	parser.add_argument("-nt", action="store_true")
	parser.add_argument("-u")
	parser.add_argument("-api")
	parser.add_argument("-g", type=int)
	parser.add_argument("-n", type=int)
	parser.add_argument("-ce", type=float)
	parser.add_argument("-c", type=int)
	parser.add_argument("-cm")
	parser.add_argument("-t", action="store_true")
	parser.add_argument("-to", action="store_true")
	parser.add_argument("-d", action="store_true")
	parser.add_argument("-df", action="store_true")
	parser.add_argument("-pl", action="store_true")
	parser.add_argument("-gn", action="store_true")
	parser.add_argument("-pf", action="store_true")
	parser.add_argument("-ss", action="store_true")
	parser.add_argument("-sr", type=int)
	parser.add_argument("-cr", action="store_true")
	parser.add_argument("-dg", action="store_true")
	parser.add_argument("-pdf", action="store_true")
	args = parser.parse_args()
	out = Path(args.o)
	lines = [l for l in Path(args.i[0]).read_text().splitlines() if l.strip()]
	print("argv: " + " ".join(sys.argv[1:]), flush=True)
	for stage in ("fetch", "extract", "cluster", "figures", "report"):
		print(">> " + stage, flush=True)
		print("progress 1/3\rprogress 2/3\rprogress 3/3", flush=True)
		time.sleep(0.05)
	if any("FAIL" in l for l in lines):
		print("Error: cannot resolve FAIL", flush=True)
		return 1
	(out / "figures").mkdir(parents=True)
	(out / "report").mkdir(parents=True)
	names = ["neighbors"] + (["tree"] if args.t or args.to else []) + (["domains"] if args.d else [])
	names += ["all-in-one"] if (args.df or args.pl or args.gn or args.pf or args.ss) else []
	for name in names:
		(out / "figures" / (name + ".svg")).write_text(SVG.format(name))
		if args.pdf:
			(out / "figures" / (name + ".pdf")).write_bytes(b"%PDF-1.4 fake\n")
	(out / "report" / "run_summary.txt").write_text("queries: {}\nfigures: {}\n".format(len(lines), ", ".join(names)))
	(out / "report" / "neighbourhoods.tsv").write_text("row_id\tgene\n")
	if args.dg:
		(out / "report" / "digest.md").write_text("# digest\n")
	(out / "run.tsv").write_text("version\t3.4.0\ncommand\t" + " ".join(sys.argv) + "\n")
	(out / "config.tsv").write_text("api_key\t{}\nuser_email\t{}\n".format(args.api, args.u))
	(out / "console.log").write_text("key {} seen\n".format(args.api))
	print("run directory: {}".format(out), flush=True)
	return 0


if __name__ == "__main__":
	sys.exit(main())
