# Ghostreader SLizard-Audit Triage Outcome

- Total findings: 1
- Verified bugs to fix: 1
- Reporting debt (SLizard noise / overstated): 0
- Wontfix candidates: 0
- Still pending: 0

## 1. BUGS WE NEED TO FIX

- **P2** `ghostreader/canon.py:265` — ghostreader/canon.py:265–282 — Historical canon accuracy bug. Readers relying on chapter-specific canon are hurt: when `state_since_chapter` is missing or invalid, the live state and knowers are shown for earlier chapters, potentially revealing changes that had not yet occurred. (confirmed-bug: ghostreader/canon.py:277-284 prints the live knowers whenever state_since_chapter is None or < N, but Autonomicon secret_registry.py:264-268,289-293 adds knowers from learned_by without changing state_since_chapter (it stays None for a never-revealed secret). Scenario: secret planted ch 2, stays hidden, character X learns it in ch 10 (knower_since={X:10}); checking ch 5 shows 'state hidden; known by X'. (The stated state leak with since=None is not the problem: None means it is still in the planted state.) Minimal fix: filter knowers by knower_since[slug] < N when knower_since is present, and, if state_history is present, take the last entry with chapter < N as the state.)

## 2. REPORTING DEBT (SLizard false / overstated)


## 3. WONTFIX CANDIDATES
