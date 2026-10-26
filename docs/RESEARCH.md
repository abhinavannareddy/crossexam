# Research notes

Prepared for Abhinav Annareddy. This note checks which design choices in CrossExam rest on published work, which rest only on my own judgement, and what I could not verify.

## Question

Are the main design choices of CrossExam (two-sided argument, weighted combination, human final decision, hash-chained audit, the money-laundering patterns it looks for, and the way it is evaluated) supported by published sources? Where not, say so.

## Method and limits

I searched the web in October 2026 and opened the primary page of each source where one existed. This is a focused check of about a dozen sources, not a systematic literature review. Items marked **not verified** could not be confirmed against a primary document. Search summaries were never treated as proof on their own.

## Sources checked

| # | Design choice | Source | What it supports | What it does not support |
|---|---|---|---|---|
| 1 | A prosecutor and a defender argue, then a referee decides | Du, Li, Torralba, Tenenbaum, Mordatch. *Improving Factuality and Reasoning in Language Models through Multiagent Debate.* arXiv:2305.14325 (May 2023); ICML 2024 (proceedings.mlr.press, vol. 235). https://arxiv.org/abs/2305.14325 | Several language-model instances proposing answers, then critiquing each other over rounds, improved reasoning and factual accuracy on the tasks the authors tested. | CrossExam uses no language model. Its agents are fixed rules with hand-set weights, and there is one round, not a debate to consensus. The paper gives no evidence about money laundering or about CrossExam's numbers. |
| 2 | Combining argument weights with noisy-OR | Pearl, *Probabilistic Reasoning in Intelligent Systems* (1988), as described in later papers (for example https://arxiv.org/pdf/1303.1481). I did not open the book. | Noisy-OR combines independent causes: the chance that none has an effect is the product of each one's failure probability. | Pearl's weights are probabilities. CrossExam's weights (0.15 to 0.45) are hand-chosen, so the combined score is a ranking aid, **not a calibrated probability**. |
| 3 | Layering, placement, integration; mule recruitment | FATF, *Professional Money Laundering* (July 2018). https://www.fatf-gafi.org/content/dam/fatf/documents/Professional-Money-Laundering.pdf (read through search excerpts, not the full report) | Describes the placement, layering and integration stages, and money mule herders who recruit and manage mules. | It does not define CrossExam's specific rules (for example "outflow of at least 80% of inflow to one recipient"). Those rules are my heuristics. |
| 4 | Structuring just under a threshold | Only vendor and trade-press pages found (for example https://financialcrimeacademy.org/red-flags-in-smurfing/). | The general idea is widely described. | **Not verified** against FATF or a regulator. Vendor pages disagree on the difference between "structuring" and "smurfing". |
| 5 | Human analyst makes the final call | EU AI Act, Article 14, on the European Commission AI Act Service Desk. https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-14 | For systems it covers, the people overseeing must be able to understand limits, avoid over-reliance (automation bias), interpret output, override it, and stop the system. CrossExam's `/decide`-only design follows the same spirit. | I did not check whether AML alert triage is a regulated high-risk use. Sources I found disagreed on application dates, so I state none. |
| 6 | Hash-chained audit log | Crosby and Wallach. *Efficient Data Structures for Tamper-Evident Logging.* USENIX Security 2009. https://www.usenix.org/conference/usenixsecurity09/technical-sessions/presentation/efficient-data-structures-tamper-evident (the page showed title, authors and venue; the abstract was not shown, the description of the method comes from search results and the authors' slides) | Tamper-evident logging with an untrusted logger and outside auditors, using a Merkle tree. | CrossExam uses a plain linear hash chain, the simpler older design. Checking it means reading the whole log. The external `head` anchor in this project is the same basic idea (an outside commitment), not the paper's scheme. |
| 7 | Alert volume and false positives as the problem | NICE Actimize AML/AI insights report (https://www.niceactimize.com/Documents/aml_ai_in_aml_insights_report.pdf), quoted by search as "almost 95 percent of alerts are false positives". | Motivation only. | Widely repeated 90 to 95% figures are credited to PwC by vendor pages, but I could not find the PwC document. Definitions of "false positive" differ between sources. I make no comparison with CrossExam's rates. |
| 8 | Evaluation on synthetic data with known labels | Altman et al. *Realistic Synthetic Financial Transactions for Anti-Money Laundering Models.* arXiv:2306.16424 (2023). https://arxiv.org/abs/2306.16424 | Real labelled laundering data is rarely available, so calibrated synthetic generators with full ground truth are an accepted approach. | CrossExam's generator is hand-written and has not been calibrated or compared with this one. |
| 9 | Graph-based money-flow features; strong tabular baseline | Weber et al. *Anti-Money Laundering in Bitcoin: Experimenting with Graph Convolutional Networks for Financial Forensics.* arXiv:1908.02591 (2019). https://arxiv.org/abs/1908.02591 | Reports a random forest outperforming graph networks on a labelled transaction graph, consistent with a strong tabular model doing well. | That dataset is Bitcoin, not bank accounts. The numbers are not comparable with CrossExam's. |
| 10 | Swedish context (SEK, Finansinspektionen, police FIU) | Finansinspektionen, money laundering pages. https://www.fi.se/en/bank/money-laundering | The FI supervises compliance and firms report suspected laundering to the Financial Intelligence Unit of the Swedish Police. | I found **no** SEK threshold for suspicious-transaction or cash reporting. |
| 11 | Model governance | Federal Reserve SR 11-7 (2011). According to the Fed's own page for its replacement, SR 26-2 (17 April 2026) supersedes it. I did not read SR 26-2. https://www.federalreserve.gov/supervisionreg/srletters/sr1107.htm | Nothing is claimed beyond: model risk guidance exists and has been revised. | It is US guidance. Whether it applies to a Swedish bank was not checked. |

## Findings

1. **The 9,000 to 9,999 SEK band and the 10,000 "reporting threshold" are assumptions.** The generator hard-codes `THRESHOLD = 10_000`, and the rules treat 9,000 to 9,999 as "just under". I found no Swedish rule that sets such a threshold. In this project the number is a stand-in for any reporting limit. The README and the policy snippets should not imply a real regulatory figure. (Corrected in the README.)
2. **The "policy" snippets are not sourced guidance.** The file says they were written for this project. They are my paraphrases of general typology descriptions, not quotations from FATF or a regulator.
3. **The strongest published support is for the process, not the results.** Debate-style adversarial roles, noisy-OR combination, human oversight and tamper-evident logging all have real literature behind them. None of it validates CrossExam's numbers.
4. **The weakest part is the evaluation.** All results come from a hand-written generator, scored by rules written by the same person. A fair next step is to run the workflow on a public benchmark such as the dataset in source 8. That has **not** been done, and I do not claim results on it.
5. **The weights are not probabilities.** Source 2 supports the arithmetic, not the meaning. Any claim that "suspicion 0.73" means a 73% chance would be wrong.

## Not researched

- The text of the Swedish Anti-Money Laundering Act and the police FIU's reporting guidance.
- Whether AML triage falls under the EU AI Act's high-risk categories.
- Explainability requirements for AML decisions from a regulator.
- Published comparisons of rule-based and learned alert triage on real bank data.

## Next steps for the research

1. Obtain the Swedish AML Act and FIU guidance and replace the placeholder threshold with a cited one, or keep it clearly labelled as synthetic.
2. Evaluate on a public synthetic benchmark (source 8) and report the result whatever it is.
3. Replace hand-set weights with weights estimated from labelled cases, and check calibration.
