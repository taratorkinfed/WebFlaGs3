# flags3_web architecture

## Shape

Four Python files, five templates, no database beyond Redis.

- `config.py` — `Settings`, read once from `.env` (python-dotenv). Nothing
  machine-specific or secret is in code; `DEFAULTS` are the lab server's paths.
- `submission.py` — `Validator` turns a form into a `Submission`
  (validated fields plus an `errors` dict); `Command` turns a `Submission`
  into the `flags3 run` argv and environment. The web app's whole knowledge of
  FlaGs3's command line is in `Command.argv`.
- `jobs.py` — `JobDir` (the layout of one job's directory), `Runner` (worker
  side: run the subprocess, stream its output into RQ meta, scrub, archive),
  `Sweeper` (delete expired job directories), `run_job` (the RQ entry point).
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

## What the user can reach

`/jobs/<id>/<path>` serves files only from `jobs/<id>/run/` (figures, report,
anything FlaGs3 wrote) and only once the RQ job is finished;
`send_from_directory` rejects traversal. `/download/<id>` serves the archive,
which `shutil.make_archive` builds from `run/` alone, so `input.txt`,
`request.json` and `log.txt` are never in it. The job id is the only
credential: a results link is private to whoever has it, as on the lab server.

## Secrets and paths

The NCBI API key reaches FlaGs3 as `-api`. FlaGs3 records its command line in
`run/run.tsv` and its options in `run/config.tsv`, so after the run (success or
failure) `Scrubber` replaces the key and the submitter's email with `***` in
`run.tsv`, `config.tsv` and `console.log`. `LogSink` does the same to the live
log and also shortens the job directory's absolute path to `<job>`, so the
page shows nothing about the server's layout. A cleaner fix is an
environment-variable fallback for the key inside FlaGs3; until then the scrub
is the guarantee.

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

## Not in v1

Emails on completion, a prioritised queue, BLAST-mode input, geNomad,
DefenseFinder/PadLoc, BioLib tools, a job list page. Each is a form field plus
an argv line in `Command.argv` when wanted, except email, which needs the
SMTP credentials in `.env` and an `on_success` callback.
