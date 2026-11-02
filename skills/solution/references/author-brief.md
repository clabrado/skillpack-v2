# Author agent brief (template)

Hand the Opus author:
- the work dir, `BRIEF.md` (framing, outcomes, run plan), every lane `.md`, `kg/graph.json` +
  `GRAPH.md` + the query command
- format references: `<intel>/references/method.md` §4b and §5 (internal vs customer-safe, voice) and the
  render rules in §6 (check.py must exit 0, look at every page PNG, fix overflow by cutting
  words, the class list); NOT §6's skeleton/title/footer commands, its triangulation checklist
  or its section list, since this skill's own method.md, skeleton and build commands below
  govern those, `<intel>/assets/template/style.css`,
  `<skill>/assets/skeleton.html` (markup and pattern library), and the newest example in
  `<skill>/private/` if present, for quality only, never for structure or facts
- the goal in the user's words, any `--target` / `--competitor` hint, the next customer touch, and anything the systems of record contradict
- a short list of **design-critical gaps it must verify itself** (append to `triangulation_notes.md`)
- `references/method.md` §Document structure: the fixed spine is mandatory. The author chooses
  the evidence-driven sections and writes one line per section in `triangulation_notes.md`
  §Section choices, giving the evidence that justified it. It also lists the sections it
  considered and cut.
- `references/method.md` §Talking-point rules
- Rules: `[n]` citations to the sources appendix, internal tags (e.g. [CRM], [Usage], [Chat
  #channel date], [Call mm:ss]) for whichever systems were actually used, "unknown" for
  unmeasured values, no secrets or IDs, ASCII only
- build commands:
  `python3 <intel>/scripts/build.py <work>/build "<out>.pdf" --title ".." --footer "<Account> · <Topic> · Dynatrace internal"`
  `python3 <intel>/scripts/check.py "<out>.pdf"` (must exit 0; read every page PNG; fix overflow by cutting words)
- outputs: `build/content.html`, `build/citations.json` [{n,title,url,used_for}], plus a
  placeholder page "Appendix D · Adversarial QA"
