# Author agent brief (template)

Hand the Opus author:
- the work dir, `BRIEF.md`, every research `.md`, `kg/graph.json` + `GRAPH.md` + the query command
- format references: `<intel>/references/method.md`, `<intel>/assets/template/style.css`,
  `<skill>/assets/skeleton.html` (markup + ASCII diagram patterns), and the newest example in `<skill>/private/` if present
- the goal in the user's words, the competitor, the next meeting, and anything systems of record contradict
- a short list of **design-critical gaps it must verify itself** (append to `triangulation_notes.md`)
- the required content list (references/method.md §Document structure) and Rules: `[n]` citations to Appendix A,
  internal tags such as [SFDC] / [PBI] / [Slack #channel date], "unknown" for unmeasured values, no secrets or IDs, ASCII only
- build commands:
  `python3 <intel>/scripts/build.py <work>/build "<out>.pdf" --title ".." --footer "<Acct> · <Target> Observability · Dynatrace internal"`
  `python3 <intel>/scripts/check.py "<out>.pdf"` (must exit 0; read every page PNG; fix overflow by cutting words)
- outputs: `build/content.html`, `build/citations.json` [{n,title,url,used_for}], plus a placeholder page "Appendix D · Adversarial QA"
