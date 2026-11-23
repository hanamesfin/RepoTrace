# RepoTrace guide: run any project we tried, and what each example shows

The guided screens (`python3 -m repotrace --lab`) are described in the submission user manual: [RepoTrace_User_Manual.pdf](RepoTrace_User_Manual.pdf). This file is the earlier screen and the example gallery.

## Start the app (pick one)
- **Double-click `RepoTrace.command`** in Finder. Your browser opens the app.
- Or in a terminal: `python3 -m repotrace` (add a folder to open a project directly: `python3 -m repotrace "/path/to/project"`).

Stop it by closing the terminal window or pressing Ctrl+C. It only runs on your computer, reads Git history and never runs your code.

## Explore a whole project (no commits needed)
On the first screen, every example has an **Explore its map** button. For your own project, open its folder and press **Explore the project map**.
- **Outline (left):** folders, then files, then classes, then functions. Click the little arrow to open one; click the name to read about it. Arrow keys work too.
- **Search (top):** type a function, class or file name and pick a result.
- **Details (right):** for a **function** you get *It uses* and *Used by* lists, a small picture of just that function and its neighbours, and the code. For a **class** you get what it keeps, what it can do, what it is a kind of, what it uses and what uses it. Click any name to go there; that is how you walk through the project.
- **"maybe"** next to a name means the link depends on an assumption. No tag means sure.
- **How much to trust it:** the start page shows a bar of how many calls RepoTrace could trace. Missing links are holes in the map, not proof that nothing is there. Calls into imports it could not find are counted as not traced, not as outside.
- **Fresh or stale?** The map is a snapshot. The code shown is the code that was analyzed; if you edit a file afterwards the page says so. Press Back and open the project again to refresh.
- **No Git needed:** type or browse to any folder and press **Explore the project map**. Git is only needed for **Compare two versions**.
- **Tests** are hidden until you tick *Show test code*. **See what a change affects** takes you to comparing two versions of the same project.

## The quickest way: the example gallery
The first screen lists examples. **One click** opens a before-and-after, runs the analysis, and shows an
**About this example** card with a plain explanation and numbered **Try this** steps. Press **Show me** next to a
step and the page does it for you. You can also open **Menu → Take a tour** at any time.

### The built-in "Example shop" (works on any computer; each one shows a single idea)
| Button | What it shows | What you should see |
|---|---|---|
| A function changed | The basics: who calls a changed function | `calculate_total` at the right; `place_order` and `Cart.total` as solid (sure) lines; `checkout` dashed (maybe) |
| Only comments changed | No false alarms | "No function changed" (comments and docstrings are ignored) |
| A value changed | A fixed value (`TAX`) changes, no function text does | `calculate_total` listed "because it reads a changed value" |
| A decorator changed | One change that reaches many functions | A column "Functions it wraps" and the callers of those |
| A function was removed, but a caller was forgotten | Catching a real mistake | `report` flagged "head still references the removed name" |
| Maybe links and name-only links | How sure RepoTrace is | `checkout` dashed; `print_summary` dotted (name only) |
| A file that cannot be read | Honesty about gaps | "analysis partly complete"; "What we could not see" names the file; nothing is called safe |
| The unreadable file is repaired | Honesty about gaps | `render_label` listed as new with a "may not really be new" warning |

### Real projects we tried (shown only if they are on this computer)
| Project | How it is opened | Good comparisons to try |
|---|---|---|
| **Shopkeep** (`~/Desktop/Test Project`) | Read through its own Git tags `step-01`..`step-11` | A helper used in many places; a value changed; a function removed with a forgotten caller (`scripts/export_report.py`); a method overridden in one subclass; a file that cannot be read, then repaired |
| **Ledgerly** (`~/Desktop/test project 2`) | Its tags `step-01`..`step-11` | A helper used almost everywhere; a class renamed; a parameter added; a decorator changed; **what RepoTrace cannot see** (a method reached only through `getattr`) |
| **LibTrack** | Copied to a temporary folder, one small edit committed there | A helper called from many menus (23 sure callers) |
| **Flask** | Copied to a temporary folder, two small edits committed there | A function in a big framework; a very common method name (`get`) whose weak matches are hidden on purpose |

LibTrack and Flask have only one commit, so the app makes a throwaway copy and edits one function in the copy.
Your original folders are never touched.

## Your own project
1. Click **Browse…** (Mac) or type the path of the folder that contains `.git`. Click **Open**.
2. Choose **Before** and **After** (the default, the last commit, is a good start). Click **Analyze**.
3. If the results look empty, open the options and check "Where your code lives". A project with a `src/` folder
   needs `src`; the app suggests it for you and says why.

## Reading the results
- **The picture:** the changed function (blue border) is on the right. Boxes to its left call it: the nearest column calls it
  directly, the next column calls those, and so on. Click a box to see why it is there and the exact line of code.
- **Lines:** solid = sure, dashed = maybe, dotted = name only (the weakest evidence).
- **Show: Direct / 2 steps / 3 steps / All** chooses how far from the changed function to look. **Hide test code** appears when
  tests are involved. **More options** has the line filters, zoom, and **Group by file** (a map of files; click a file to open it
  into its functions). When several functions changed, pick one from the row above the picture; the most affected comes first.
- **Explore any function:** search any function and expand "who calls this" and "what this calls" one layer at a time.
- **What we could not see:** what could not be checked (link under the headline). A quiet result never means "safe".

## Make it comfortable (Display settings)
Text size (normal / large / extra large), colors (match my computer / light / dark / high contrast),
and reduced animation. Every picture also has a **Text version** underneath, and the picture can be used with the
keyboard (Tab into it, arrow keys to move, Enter to open a box, Esc to return to the changed function).

## Without the app (command line)
```sh
python3 -m repotrace change "/Users/israelhayalsew/Desktop/Test Project" --base step-05 --head step-06 \
    --source-root src --include-possible --dashboard out.html
python3 -m repotrace change "/Users/israelhayalsew/Desktop/test project 2" --base step-08 --head step-09 \
    --include-possible --dashboard out.html
```
`out.html` is a single file you can open or share (it contains source code snippets).

## Checking that everything works
```sh
python3 -m unittest discover -s tests -t .            # all unit tests, including that every example's explanation matches the analysis
qa/browser/run.sh light        # drives the real app in Chrome: every example, the tour, settings, keyboard, screen-reader tree
```

## New: calls that no longer fit changed parameters

Restart RepoTrace and open the built-in example **A required parameter was added, but callers were forgotten**.
Select `calculate_total`. **Calls to update** shows two callers still missing `currency`; expand an entry to see its line.
The check stays inside the existing review panel. It skips uncertain calls, method targets, decorated targets and unpacked arguments.
No warnings does not mean a change is safe. Run the relevant tests. Older saved reports must be regenerated to include this check.
See [ROADMAP.md](ROADMAP.md) for the limits and the next small additions.

