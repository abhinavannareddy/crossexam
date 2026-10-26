# CrossExam

A cross-examination workflow for anti-money-laundering alerts. For each alert, a prosecutor agent argues why it looks suspicious, a defender agent argues for a legitimate explanation, and a referee weighs both. A case note is written with every claim tied to evidence, and a human analyst always makes the final decision.

**All data is synthetic.** Nothing here uses real customer or bank data, and the results below say nothing about a real bank.

## How it works

1. A gradient-boosting model scores accounts using 30-day features. It is trained on four scheme types (structuring, layering, circular flows, mule accounts). A fifth type, dormant-account bursts, is held out of training.
2. Simple rules (R1 to R5) plus the model score decide which accounts raise an alert.
3. A LangGraph supervisor picks which sub-agents to run: history (SQL), graph (money flow), profile, policy search (TF-IDF over 7 policy snippets) and precedent (nearest closed cases).
4. The prosecutor and defender each list weighted arguments that point to evidence IDs. Weights are combined with noisy-or. The referee recommends escalate, analyst review or suggest close.
5. The case writer produces a note with `[E#]` citations. `check_note` verifies that every tag exists, every number in the evidence list comes from the evidence, and the printed weights and referee scores match the arguments and verdict.
6. `/decide` is the only way a case changes status. Every step goes into a hash-chained audit log.

The data includes look-alike customers who are honest but resemble schemes (cash businesses, documented family loops, marketplace sellers, property sales).

## Run

```
pip install -r requirements.txt
python -m pytest -q
python -m crossexam.evaluate      # about 2 minutes, writes results.json
python -m crossexam.evaluate results_heldout.json 11 12 13 14 15   # other seeds
uvicorn crossexam.api:app         # audit log is kept in crossexam_audit.db (set CROSSEXAM_AUDIT_DB to change)
python -m crossexam.cypher graph.cypher   # optional Neo4j export, not tested against a live server
```

## Results (5 synthetic dataset seeds, 718 alerts, from `results.json`)

| Method | Suspicious missed | False escalations | Sent to analyst |
|---|---|---|---|
| Model score only (escalate at 0.5) | 2.5% | 0.0% | 0% |
| Prosecutor only | 0.0% | 31.7% | 0% |
| CrossExam (full) | 0.0% | 7.0% | 31.6% |

What this shows, honestly:
- The model alone is strong on this synthetic data and has no false escalations, because the planted schemes are easy for it. CrossExam does **not** beat it on false escalations. Its extra value here is no missed cases, the held-out dormant type (model escalates 82.5%, CrossExam 100%), and written, cited reasoning.
- Hearing both sides cuts false escalations from 31.7% (prosecutor alone) to 7.0%. About a third of alerts go to analyst review instead of being forced into a yes or no.
- Precedent memory (second half of each queue, simulated analyst decisions taken from ground truth): false escalations drop from 16.3% to 2.3%, while misses stay at 0.0% and fewer suspicious accounts are escalated outright (98.7% to 95.3%, the rest go to review). It is a trade, not a free gain.
- Every generated note passed the citation check (718 of 718). The check proves the tags exist, the numbers in the evidence list come from the evidence text and the printed weights and scores match the arguments. It does not prove the reasoning is correct.

### Mule accounts: a rule fix, and how it was checked

An earlier version escalated only 68% of mule accounts (45% on seeds 11 to 15). The cause: the mule rule required that money left within 72 hours of each inflow, but some mules forward everything to one recipient later than that, so that measure was 0. The rule now also accepts "at least 80% of the money received went out, mostly to one recipient" (`MULE_OUTFLOW_RATIO` in `agents.py`).

The fix was written after reading mule cases from seeds 1, 2, 3, 11 and 12. It was then measured on seeds 21 to 25, which nobody had looked at (`results_fresh.json`, 679 alerts):

| Mule accounts escalated | Before the fix | After the fix |
|---|---|---|
| Seeds 1 to 5 | 68% | 100% |
| Seeds 21 to 25 (not used for the fix) | 62% | 100% |

False escalations did not change (7.0% to 7.0% and 6.8% to 6.8%), and no other scheme type changed. Caveat: the generator creates mules, so a rule that fits the generator's mules fits by construction. Real mule behaviour is messier and this gain says nothing about it.

### Other seeds with the current code

| Seeds | Alerts | Method | Suspicious missed | False escalations | Sent to analyst |
|---|---|---|---|---|---|
| 11 to 15 (`results_heldout.json`) | 745 | Model only | 4.6% | 1.2% | 0% |
| | | CrossExam | 0.0% | 5.7% | 34.5% |
| 21 to 25 (`results_fresh.json`) | 679 | Model only | 4.6% | 0.8% | 0% |
| | | CrossExam | 0.0% | 6.8% | 33.4% |

The model escalates only 59% to 69% of the held-out dormant type on these seeds; CrossExam escalates 100%. I cannot show that the review thresholds were not adjusted while looking at seeds 1 to 5 (the repository has a single commit), so none of these is a clean held-out test of the whole system.

The data generator and the agent rules were written by the same person, so scores are optimistic. Real transaction data would be much harder.

## Not done

- No LLM is used. The agents are deterministic rules, so the notes are templated.
- Neo4j export is untested. The graph runs in networkx.
- No authentication on the API. The `analyst` field in `/decide` is free text, so the audit log records what was claimed, not a verified identity.
- The audit chain detects edits to stored entries. To detect deleted newest entries, keep the `head` value returned by `/audit/{case_id}` somewhere outside the database and pass it to `AuditLog.verify(anchor)`.
- Case state is held in memory and is lost on restart; only the audit log is persisted. A decided case cannot be investigated or decided again (the API returns 409).

## Author

Abhinav Annareddy
