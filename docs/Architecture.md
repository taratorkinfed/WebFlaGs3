# flags3_web architecture

## Shape

Eight Python files, five templates, no database beyond Redis.

- `config.py` — `Settings`, read once from `.env` (python-dotenv). Nothing
  machine-specific or secret is in code; `DEFAULTS` are the lab server's paths.
- `submission.py` — `Validator` turns a form into a `Submission`
  (validated fields plus an `errors` dict); `Command` turns a `Submission`
  into the `flags3 run` argv and environment. The web app's whole knowledge of
  FlaGs3's command line is in `Command.argv` and the `SCANNERS` table beside
  it: one row per optional tool (form name, flag, label, note, and whether
  it scans sequence windows). The form section is rendered from that table,
  so adding a tool is one row. `-sr` (the form's scan range, 20 000 bp each
  side by default, 5 000–200 000) is passed only when a windowed scanner —
  geNomad or Sismis — is selected; PlasmidFinder keeps its own
  whole-contig span from the tools table and the defence tools read the
  flanking proteins, so neither is affected by it. The clustering
  method is a choice between `jackhmmer` and `mmseqs_cluster` (`-cm`),
  the second offered when the `mmseqs` component is installed: it is the
  cheap way to cluster and the form says so, because long lists on
  jackhmmer are what loads the server. `-n` is passed only with jackhmmer,
  and `-ce` only when the E-value box is filled, so an empty box leaves each
  method its own default from FlaGs3's tools table (1e-10 and 1e-3) rather
  than forcing one method's number on the other. RNA clustering (`-cr`)
  and the digest (`-dg`) are plain switches: both come with FlaGs3 itself
  and need no installed component. `report/digest.md` reaches the user as
  one of the report-file buttons on the results page, like every other
  file FlaGs3 writes there.
- `capabilities.py` — `Capabilities`, what this server's FlaGs3 can do.
  At start-up the app runs `flags3 install` with no arguments, which lists
  every component with its state, and keeps the names whose state is not
  `-`. `FEATURES` maps each optional form control to the components it
  needs (tree → core; domains → pfam; DefenseFinder, PadLoc, geNomad and
  Sismis → their own component; PlasmidFinder → its database and core's
  BLAST+). A control whose feature is missing is drawn disabled and its
  value is dropped by the validator, so the form can never start a run the
  server cannot finish. The web app holds no path into the FlaGs3 home for
  this; FlaGs3 answers for itself. The probe runs once per process, so after
  `flags3 install <component>` the web service is restarted to show it. One
  ambiguity is inherited from that listing: a PlasmidFinder database
  without its `commit.txt` stamp reports `-` and reads as absent; one
  installed by `flags3 install plasmidfinder` always has the stamp.
  A feature can also depend on the FlaGs3 version instead of a component:
  `SINCE` maps it to the first version that has it, and the probe reads
  `flags3 --version` beside the listing. The protein clusters legend
  (`-pcl`, FlaGs3 3.6.0) is the first such feature, so its switch is
  disabled on a server whose FlaGs3 is older rather than failing the job on
  an unknown option. A feature may need both: BlastP needs FlaGs3 3.7.0,
  the `core` component for `blastp`, and the database, which the probe
  enters as the pseudo-component `blastdb` when `blast_db` in `.env` names
  a path with a `.pal` or `.pin` file beside it.
- `blastinput.py` — `BlastQueries`, the parser of the "Starting proteins"
  box (see BlastP below).
- `jobs.py` — `JobDir` (the layout of one job's directory), `Runner` (worker
  side: run the subprocess, stream its output into RQ meta, scrub, archive),
  `Sweeper` (delete expired job directories), `run_job` (the RQ entry point).
- `limits.py` — `BlastLimit`, how many BlastP jobs one address or one
  email may have queued or running (see Limits below).
- `mailer.py` — `Mailer` (one plain-text message through SMTP with
  STARTTLS and a login) and `Notice` (the finished and failed texts for one
  job, with its results link built from `site_url`).
- `app.py` — Flask routes and `JobStatus`, the view model of an RQ job.

## Request flow

1. `POST /` — the form is validated in the request (regex and bounds only, no
   network), so a bad list comes straight back with the fields marked.
   `atkinsonlab_web` validates in a worker because uORF4u's validation calls
   NCBI; ours does not, so there is no helper queue, no validation page and no
   second worker unit.
2. A valid submission gets a job id (`uuid4().hex`, 32 hex chars, the only id
   format any route accepts), `jobs/<id>/input.txt` and `request.json`, and is
   enqueued on the `flags3` queue with that id. `result_ttl` and
   `failure_ttl` equal `results_ttl_hours`, so RQ forgets the job when the
   directory is due to go.
3. `Runner.run` in the worker: `flags3 run -i input.txt -o run -nt …` with
   `cwd` the job directory and `FLAGS3_HOME` in the environment, plus
   `PYTHONUNBUFFERED=1`: FlaGs3 is a Python program writing to a pipe, and
   without it the interpreter holds its output in 8 kB blocks, so the page
   would show nothing until the run ended. Stdout and
   stderr are read line by line (bytes split on `\n` only, so a tool's `\r`
   progress keeps only its last segment) into `job.meta["log"]`, saved at
   most twice a second, capped at 200 kB from the tail. A non-zero exit raises,
   which RQ records as a failed job; the log stays in meta and `log.txt`.
4. `GET /results/<id>` renders the state from RQ and the files from the job
   directory; a script polls `GET /status/<id>` every two seconds, refreshes
   the log in place while the job runs, and reloads the page when the state
   changes.

## Form defaults

A fresh form has the tree on, with rows in tree order, and the protein
clusters legend ticked. Both were opt-in at first; in the first days of
testing every user turned the tree on, some reran a finished job to get it,
and it costs seconds. The defaults are the field defaults of `Submission`,
which is what `GET /` renders; a posted form is read as sent, so unticking
or choosing "No tree" is respected. A default the server's FlaGs3 cannot
deliver is shown off and disabled, not ticked and greyed. A job without a
tree still gets the all-in-one figure from FlaGs3 3.7.0 on.

Synteny (`-sy`, FlaGs3 3.8.0) is a fourth choice of the tree select, not a
switch of its own: it means nothing without rows in tree order, and as a
choice of the same field it cannot be combined with anything else.
`TREE_FLAGS` maps each choice to its one option; `-sy` implies `-to` in
FlaGs3. The choice is offered only when the `synteny` feature is there
(`core` for `blastn`, and the version); a posted `synteny` on a server
without it falls back to `tree_order`. It stays opt-in: it makes the job
fetch the genome sequence of every assembly, which a job without scanners
otherwise does not.

## BlastP

The form can start a job from proteins instead of a finished list: FlaGs3
searches a local database for their homologues and the hits become
queries. The web app adds nothing to FlaGs3's own mechanism. Each starting
protein is written to the job's `input.txt` as a line marked `BLAST`
(`Submission.input_text`), and the command gets `-bm local -bd <blast_db>
-bh <n> -bx <blast_exclude>`.

The service is shaped so that it is of no use as a BLAST server, because a
fast RefSeq search without a login would otherwise attract exactly that:

- at most `blast_max_queries` (5) starting proteins a job;
- `blast_total_hits` (50) hits a job in all. FlaGs3's `-bh` is per
  starting protein, so `Command` passes the total divided by their number:
  50, 25, 16, 12 or 10 each;
- nothing of the search is returned but what FlaGs3 keeps for itself,
  `blast/hits.tsv` (accession, E-value, bit score, description of the hits
  that became queries) — no alignments, no other output format, and no
  option on the form that reaches `blastp`: E-value and database are the
  server's;
- the number of BlastP jobs one address or one email may have in the queue
  at a time (Limits below).

`BlastQueries` reads the box line by line. An accession on a line of its
own (RefSeq `WP_`/`NP_`/`YP_`/`XP_`/`AP_`, or an INSDC protein id) is a
query; other lines are collected into a sequence until a FASTA header or
an empty line ends it. Headers are dropped — FlaGs3's inline form has no
place for a name — and a sequence is upper-cased, stripped of spaces and a
final `*`, and must be 10 to 5000 residues of the amino-acid alphabet.
What is written to `input.txt` is therefore an accession or one line of
residues, never the user's text. With starting proteins the accession list
may be empty.

`blast_exclude` (2759, eukaryotes) is the reason for the FlaGs3 3.7.0
requirement: the database is NCBI's whole `refseq_protein`, and the
exclusion is applied at search time by `-bx`. `Command.environment` sets
`BLASTDB` to the database's directory so that `blastp` finds
`taxonomy4blast.sqlite3` there whatever its search path. The database path
and its directory are replaced by `<blastdb>` in the live log and scrubbed
from the run's files like the other server paths. An accession's sequence
is fetched from NCBI by FlaGs3, so an accession start still depends on
NCBI answering; a pasted sequence does not, until the hits are resolved to
genomes.

## Limits

A BlastP job is refused when its submitter already has `blast_limit` (3)
BlastP jobs queued or running, counted separately for the client address
and for the email address, so three from one address and any email, or
three for one email from any address, close the door. Jobs without BlastP
are not counted and not limited, and there is no daily allowance: the
limit is on what waits and runs at once, which is what a flood would
occupy.

`limits.ActiveJobs` keeps one Redis set of job ids per address and per
email, under `<queue>:blast:active:<kind>:<hash>`; the key is a truncated
SHA-256 of the lower-cased value, so neither addresses nor emails are
readable in the shared Redis. Nothing removes a job from its set when it
ends. Instead the count asks RQ for the status of each id and drops those
no longer queued or running, so a job that finished, failed, was killed
with its worker or expired frees its place the same way, with no callback
to miss. The sets expire a week after their last addition. Check and
record are two steps and not atomic: two submissions in the same instant
could both pass at two, giving four; that is accepted, the limit being a
brake and not an account.

The address is `REMOTE_ADDR` as nginx hands it over in `uwsgi_params`, the
peer of the TLS connection, and not a forwarded-for header, which a client
could write itself. Everyone behind one NAT address shares one allowance;
`blast_limit` in `.env` is the dial, and 0 turns the limit off. A refused
submission is answered 429 with the form filled in as it was sent.

## Email

Testers close the tab, so a job tells its submitter when it ends. The route
is the one the lab server already uses: `smtps.lu.se:587`, STARTTLS, a
function account's login (`smtp_user`, `email_pass`) and the lab's sender
address (`mail_from`), all from `.env`. Mail is on only when all three are
set; `Mailer.enabled` is what the form and the results page ask, so a
server without credentials says "no email is sent" instead of promising
one. The form's box is ticked by default and the submitter can untick it.

`run_job` builds the `Notice` before the run and sends after it: the
finished text when `Runner.run` returns, the failed text when it raises
(the exception is re-raised, so RQ still records the failure). Sending
happens in the worker, which is why the link comes from `site_url` and not
from a request. A message that cannot be sent — SMTP down, login refused
— returns `False` and never fails the job; `notified` in the job's result
records which it was. A worker killed outright (a restart mid-job) sends
nothing. The address is validated to contain no whitespace and the run
name to a fixed alphabet before either reaches a header. Both messages, the
failed-job page and the foot of the main page name `contact_email` from
`.env` as the place to write to.

## What the user can reach

`/jobs/<id>/<path>` serves files only from `jobs/<id>/run/` (figures, report,
anything FlaGs3 wrote) and only once the RQ job is finished;
`send_from_directory` rejects traversal. `/download/<id>` serves the archive,
which `shutil.make_archive` builds from `run/` alone, so `input.txt`,
`request.json` and `log.txt` are never in it. The job id is the only
credential: a results link is private to whoever has it, as on the lab server.

Each figure on the results page is a `FigureView` (`JobDir.figure_views`):
its SVG, its PDF when there is one (a figure split into parts shares one
PDF), and two text companions FlaGs3 writes beside the figures —
`protein_clusters_legend.txt` for the figures that show families by number
(`CLUSTER_FIGURES`: classic, neighbors, tree, all-in-one) and
`systems_summary.txt` for the figures that draw systems (`SYSTEM_FIGURES`).
A link is offered only when the file exists. The two tuples name FlaGs3's
shipped figures; a figure the web app does not know simply gets no
companion link.

## Secrets and paths

The NCBI API key reaches FlaGs3 in the environment, as `NCBI_API_KEY`
(`Command.environment`), never on the command line: FlaGs3 from 3.6.0 reads
it there when `-api` is absent, and an older FlaGs3 simply runs without a
key. A key on the command line is visible in the server's process list and
is written by FlaGs3 into every place it records the command.

The submitter's email still travels as `-u`, and FlaGs3 records its command
line in `run/run.tsv`, its options in `run/config.tsv`, and the command
again in `report/run_summary.txt` and `report/digest.md` — the last two are
shown on the results page and are in the archive. After the run (success or
failure) `Scrubber` replaces the email, and the key should it ever appear,
with `***` in all five files plus `console.log`; the archive is built
afterwards. The first version scrubbed only the three files in the run's
root and so published the key in every summary; `SCRUBBED_FILES` is the
list to extend when FlaGs3 starts recording the command somewhere new, and
a test reads every file of a job's archive for the key and the address.
`LogSink` does the same to the live log and also shortens the job
directory's absolute path to `<job>`, so the page shows nothing about the
server's layout.

## Expiry

There is no scheduler process. `run_job` first calls `Sweeper.sweep`, which
removes every job directory whose mtime is older than `results_ttl_hours`.
Results therefore live at least `results_ttl_hours` and at most until the next
job starts after that; RQ's own TTL hides the page in the meantime, and a
directory without a job (or a job without a directory) renders the expired
page.

## Prefix safety

Every link goes through `url_for`, so the app can be mounted under a path
prefix (`uwsgi_param SCRIPT_NAME /flags` in nginx) as well as at the root of
its own hostname. The vendored `styles.css` references `/static/fonts/…` and
`/static/img/…` absolutely because it is compiled from the lab's SCSS; under a
prefix those two directories would need a copy at the root or a sed over the
stylesheet.

## Look

`static/css/styles.css`, the fonts, `background_webflags.svg`, the favicon and
`bootstrap.bundle.min.js` are copied from `atkinsonlab_web` unchanged, so the
page is the lab's Bootstrap build with the lab's palette and navbar.
`static/css/flags3.css` holds the few additions (body background, log box,
spinner). Refresh the copies when the lab stylesheet changes.

The "Example output" block on the main page is `examples.py`: one
`Example` per figure (file name, tab title, caption) and the intro line,
rendered as Bootstrap pills with one pane each. The SVGs in
`static/img/examples/` are FlaGs3's own figures for the demo list, so the
captions describe exactly what the demo job returns; when the demo list or
FlaGs3's drawing changes, rerun the demo and replace the seven files and
whatever the captions say about them. Tabs rather than the lab pages'
carousel because a carousel's arrows lie over the left and right edge of a
wide figure, which is where the row labels and the system codes are.

## Not in v1

A prioritised queue, a job list page, and two FlaGs3 features left out
on purpose: DeepTMHMM and SignalP (BioLib login or licensed local
installs).
