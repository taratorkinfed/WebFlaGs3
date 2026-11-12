from dataclasses import dataclass


@dataclass(frozen=True)
class Example:
	name: str
	title: str
	caption: str

	@property
	def image(self) -> str:
		return "img/examples/{}.svg".format(self.name)


INTRO = ("The demo list holds 15 proteins annotated as the export chaperone SecB. FlaGs3 resolved 14 of them to a genome "
	"and drew these figures; every one is also written as PDF, and the tables behind them come in the archive.")

EXAMPLES = (
	Example("neighbors", "Neighbours",
		"One row per query. The query has a black outline and points right; four genes on each side are drawn to scale. "
		"Genes of one colour, carrying one number, are homologues of each other; grey genes have no homologue in any other row. "
		"Here the query (Q1) always sits behind family 1 and one of families 2, 3 or 13, while the genes further out change from "
		"genome to genome. The panel under the rows is the optional protein clusters legend: every family with its product names."),
	Example("tree", "Tree",
		"The same neighbourhoods in the classic look, in the order of a phylogenetic tree built from the query proteins, with "
		"branch support in red. Related queries with the same gene context end up next to each other."),
	Example("domains", "Domains",
		"Pfam domains drawn as numbered wedges inside the genes, named in the legend. Family labels take a G prefix here so "
		"they cannot be mistaken for domain numbers. A grey gene with a familiar domain is often the most useful thing on the page."),
	Example("defence", "Defence systems",
		"DefenseFinder and PadLoc run on the flanking genes; a system either tool calls is a band under the genes it covers. "
		"Here the toxin\u2013antitoxin\u2013chaperone system CmdTAC (D1) is called in 4 of the 14 neighbourhoods, on the genes next to the query."),
	Example("genomad", "Mobile elements",
		"geNomad scans the sequence around each query for proviruses and plasmid signal. Nine of the 14 neighbourhoods lie "
		"inside a predicted provirus: Caudoviricetes (M1) in eight, Inoviridae (M2) in one."),
	Example("all-in-one", "All-in-one",
		"Everything at once, on the tree: families, domains, and one lane of bands per tool. Every system has its own colour, "
		"the same in every figure of the run."),
	Example("classic", "Classic",
		"The original FlaGs figure: compact arrows with the family number inside."),
)
