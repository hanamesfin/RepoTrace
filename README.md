# RepoTrace

**See what a code change could affect, and how sure we are.**

RepoTrace reads a Python project *without running it* and draws a map of which function uses which, with an honest count of how much of that map is solid.

Two ways to run it:
- **The new guided screens** (`python3 -m repotrace --lab`): choose any Python folder, optionally two Git versions, and get a guided start, the map with code beside it, a change review with the tests worth running first, and **Explore the project**, the Obsidian-style connected graph (folders open into files and functions; a function pulls in its real callers and callees; Physical, Logical and experimental Conceptual views; ⌘K to find or ask; a review mode that rings what changed). Live analysis, no saved data.
- **The classic screen** (`python3 -m repotrace`): the earlier outline-and-details screen, still here until the guided screens replace it.

Two ways in (both screens):
- **Explore the project map:** pick a folder (Git is not needed) and get an **outline** (folders, files, classes, functions) with a search box. Click anything to see what it uses, what uses it, and a small picture of just that thing and its neighbours. Click a neighbour to walk there. No Git needed.
- **See what a change affects:** pick two versions (two Git "save points") and see which functions changed, what depends on them, and what it could not see.

It never says "safe".

## Try it (2 minutes)
You need Python 3.9+ and Git. Nothing else to install.

1. **Double-click `RepoTrace.command`** (Mac), or run `python3 -m repotrace --lab` in this folder (the new screens) or `python3 -m repotrace` (the classic screen).
2. Your browser opens. Click one of the **examples** (each has an *Explore its map* button), or open your own project folder and press **Explore the project map**.

## What the colours mean
| Line | Word | Meaning |
|---|---|---|
| solid | **Sure** | The code text shows this call. |
| dashed | **Maybe** | Probably real, but it depends on an assumption. |
| dotted | **Name only** | Another call has the same name. Weakest evidence. |

## From the terminal
```
python3 -m repotrace change REPO --base HEAD~1 --head HEAD     # what did my last commit affect?
python3 -m repotrace change REPO --base HEAD~1 --head HEAD --include-possible --max-tests 20
python3 -m repotrace map FOLDER --output map.json              # map one project
python3 -m repotrace arrows map.json                           # print the map as arrows
python3 -m repotrace help                                      # all commands
```

Change reviews rank at most 20 tests to run first across the whole comparison (adjust with `--max-tests` in the CLI).
The guided screen and terminal show how many connected tests are outside that list. All per-change test evidence
remains in the JSON report; `test_plan` contains the ranked list. This is a starting point, not permission to skip
the rest of the suite. Ranking favors stronger evidence, lost paths, explicit use over shared setup/autouse,
and shorter call paths; it does not estimate failure probability or test duration.

## The folders at a glance
```
repotrace/
  reading/      read one file
  mapping/      join all files into one map
  graph/        ask questions of the map
  changes/      compare two versions
  report/       plain-words story and web page
  app/  cli/    the doors: browser app, terminal commands
  evaluation/   measure how accurate the map is
tests/          513 automatic checks
samples/        small example projects
prototype/      clickable design prototypes on saved data (the guided one shares its code with the real app)
docs/           ARCHITECTURE, GUIDE, REFERENCE, ROADMAP
```
Each folder uses only the ones above it. **Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) first**: it explains every folder and the reasons behind each decision.

## Run the checks
```
python3 -m unittest discover -s tests -t .      # 513 unit tests (about 70 seconds)
qa/browser/run.sh light                         # drives the classic screen in Chrome (needs Chrome + Node 22+)
qa/browser/run_lab.sh OUT PROJECT BASE HEAD      # drives the new guided screens, live, on a project (see the script header)
qa/browser/run_lab_saved.sh OUT                  # the same checks on the saved demo in prototype/lab
```

## Honest limits
- Python can decide at run time what to call, so some calls are invisible to any tool that only reads code. In our test projects RepoTrace follows roughly a third to a half of calls. The screen always lists what it could not see.
- It suggests where to look. It does not prove that anything breaks or is safe.

## More
- **New teammate? Start with [docs/PROJECT_HANDBOOK.md](docs/PROJECT_HANDBOOK.md)**: direction, decisions, measured numbers, weak spots, plan
- [prototype/](prototype/README.md): the clickable designs (open `prototype/lab/index.html` in Chrome)
- [docs/RepoTrace_User_Manual.pdf](docs/RepoTrace_User_Manual.pdf): the senior-project user manual for submission (HiLCoE guideline, section 5)
- [docs/GUIDE.md](docs/GUIDE.md): the earlier screen, and how to run each example
- [docs/REFERENCE.md](docs/REFERENCE.md): the detailed technical reference
- [docs/ROADMAP.md](docs/ROADMAP.md): what could come next
