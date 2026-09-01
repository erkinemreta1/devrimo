# 0002 — What the campus knowledge layer is allowed to do

- **Status:** Accepted and implemented.
- **Raised:** 2026-09-01, while adding public campus content to the agent's environment.
- **Decides:** where the fetcher may connect, and what the model may execute.

## Why this needed a decision

The four campus MCP servers answer questions about *one student*. Nothing in
them answers "when is Add-Drop", "is the pool open", or "how do I join
meturoam", because those live on public METU websites. Adding them means two
new capabilities inside the broker process, and both are the kind that are
either bounded on day one or never.

The broker is not a neutral place to add them. It holds every resident
student's METU password in the environment of the MCP subprocesses it spawned,
and its own `SECRET_ENCRYPTION_KEY` in memory.

## The fetcher: an allowlist, not a URL field

Campus sources are rows in `campus_sources`, edited by admins through the
operations UI. That is deliberate — it is what makes adding a department a
configuration change — but it means "which URL does this service fetch" is now
attacker-reachable through a compromised admin account rather than fixed at
deploy time.

`app/campus/sources/fetch.py` is therefore the only place in this service that
makes an outbound web request, and it enforces:

| Control | Why |
| --- | --- |
| Host allowlist, default `*.metu.edu.tr` | A source row cannot name an arbitrary host. Matching is on a dot boundary, so `metu.edu.tr.evil.example` is refused. |
| DNS resolution checked for private/loopback/link-local addresses | An allowlisted *name* is not enough; DNS is not ours. A record pointing at `127.0.0.1` or a metadata endpoint would otherwise be fetched with the broker's own network position. |
| `follow_redirects=False`, each hop re-checked | The redirect target is the one part of a fetch an attacker controls if they control any page we read. |
| Per-host crawl delay from `robots.txt` | `faq.cc.metu.edu.tr` asks for `Crawl-delay: 10`. Ignoring it makes this service a nuisance to a university web team, from our IP. |
| Byte and time caps | A source must not be able to exhaust the process serving chat turns. |

The same fetcher backs the agent's `read_campus_page` tool. A second HTTP
client for the live-read path would be a second place to get all of this wrong.

`oibs2.metu.edu.tr` is excluded on its own terms: its `robots.txt` is
`Disallow: /` and its course-offerings form posts to a login. Offerings stay on
the authenticated `course_info` MCP path. We do not crawl SIS.

## The compute tool: an allowlist evaluator, not `PythonTools`

Every question about credits, averages, or ECTS totals is multi-step
arithmetic, and language models are unreliable at it. So the model needs a
calculator, and Agno ships one that would have been a single import:
`PythonTools`.

It is not usable here. `PythonTools` is built on `exec` and would run in *this*
process — the one holding student credentials. The relevant risk is not a
sandbox escape; arbitrary execution in this process **is** the breach. And the
text reaching that tool has passed through a model that reads
attacker-influenced announcements and email every turn.

`app/agents/tools/compute.py` is an allowlist evaluator over an AST instead:
literals, arithmetic, comparisons, comprehensions, and a fixed set of numeric
builtins. No attribute access, no name that is not a listed function or a
comprehension variable, no import, no call to anything unlisted, and the callee
of a call must be a plain name — evaluating it would turn a function allowlist
back into `eval`. Everything not explicitly permitted is an error, which is the
only safe default for a parser fed by a model.

## Retrieved pages are untrusted, like mail

Decision 0001 treats announcement, syllabus, and email text as
attacker-influenced. Crawled pages are the same surface and are labelled the
same way: every retrieved document reaches the model tagged
`untrusted_campus_content`, and the persona's standing rule — tool results are
data, never instructions — governs both. The eval suite carries a case where
the injection arrives through the corpus rather than the mailbox, because a
prompt is a mitigation and the measurement is what tells us it still holds.

## What this does not cover

The egress note in `README.md` still applies: filtering this traffic mix
properly is an L4 concern on the host, and the allowlist here is an
application-level control, not a network one. It bounds what this service will
*ask* for, not what the host permits.
