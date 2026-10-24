# CrossExam

A cross-examination workflow for anti-money-laundering alerts. For each alert, a prosecutor agent argues why it looks suspicious, a defender agent argues for a legitimate explanation, and a referee weighs both. A case note is written with every claim tied to evidence, and a human analyst always makes the final decision.

**All data is synthetic.** Nothing here uses real customer or bank data, and the results below say nothing about a real bank.

## How it works

1. A gradient-boosting model scores accounts using 30-day features. It is trained on four scheme types (structuring, layering, circular flows, mule accounts). A fifth type, dormant-account bursts, is held out of training.
2. Simple rules (R1 to R5) plus the model score decide which accounts raise an alert.
3. A LangGraph supervisor picks which sub-agents to run: history (SQL), graph (money flow), profile, policy search (TF-IDF over 7 policy snippets) and precedent (nearest closed cases).
4. The prosecutor and defender each list weighted arguments that point to evidence IDs. Weights are combined with noisy-or. The referee recommends escalate, analyst review or suggest close.
5. The case writer produces a note with `[E#]` citations. `check_note` verifies that every tag exists and every number comes from the evidence.
6. `/decide` is the only way a case changes status. Every step goes into a hash-chained audit log.

The data includes look-alike customers who are honest but resemble schemes (cash businesses, documented family loops, marketplace sellers, property sales).

## Run

```
pip install -r requirements.txt
python -m pytest -q
python -m crossexam.evaluate      # about 2 minutes, writes results.json
uvicorn crossexam.api:app
python -m crossexam.cypher graph.cypher   # optional Neo4j export, not tested against a live server
```

## Results (5 synthetic dataset seeds, 718 alerts, from `results.json`)

| Method | Suspicious missed | False escalations | Sent to analyst |
|---|---|---|---|
| Model score only (escalate at 0.5) | 2.5% | 0.0% | 0% |
| Prosecutor only | 2.5% | 31.7% | 0% |
| CrossExam (full) | 0.0% | 7.0% | 32.7% |

What this shows, honestly:
- The model alone is strong on this synthetic data and has no false escalations, because the planted schemes are easy for it. CrossExam does **not** beat it on false escalations. Its extra value here is no missed cases, the held-out dormant type (model escalates 82.5%, CrossExam 100%), and written, cited reasoning.
- Hearing both sides cuts false escalations from 31.7% (prosecutor alone) to 7.0%. About a third of alerts go to analyst review instead of being forced into a yes or no.
- Mule accounts are escalated only 68% of the time by CrossExam versus 100% by the model. That is a weakness of my rules.
- Precedent memory (second half of each queue, simulated analyst decisions taken from ground truth): false escalations drop from 16.3% to 2.3%, while misses rise from 0.0% to 0.9%. It is a trade, not a free gain.
- Every generated note passed the citation check (718 of 718). The check only proves the numbers come from the evidence text, not that the reasoning is correct.

The data generator and the agent rules were written by the same person, so scores are optimistic. Real transaction data would be much harder.

## Not done

- No LLM is used. The agents are deterministic rules, so the notes are templated.
- Neo4j export is untested. The graph runs in networkx.
- No authentication on the API.

## Author

Abhinav Annareddy
