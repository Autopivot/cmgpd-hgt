# 6 Multi-Agent Negotiation Protocol

## 6.1 Persona instantiation

For each actor (husband + each top-K candidate) we render the persona prompt with the following fields drawn from data:

- **profile**: sex, birth year, banner affiliation as English label, geographic region as English label, community ID, household ID;
- **HGT pre-score** against the husband;
- **event block** formatted as `{year}: {event_1_label} / {event_2_label}` constructed from DS0003 `EVENT_1/2` codes substituted via `event_value_labels.json` (e.g., 1=Death, 7=In-Marriage, 13=Returned-after-absconding);
- **income block** formatted as `{year}: {income} ({level})` bucketed at the cohort's 33rd / 66th percentiles;
- the **SEAL motif** tag set;
- and any **hints** addressed to this role drained from the queue.

The LLM returns a JSON object with four fixed fields — `headline`, `traits`, `values`, `red_flags` — which the client renders verbatim as chips (V5).

## 6.2 Round structure

> **Algorithm 1.** The six-round bilateral negotiation.
>
> ```
> Input: husband h, candidate set C, cohort year y, ablation a
>
>  1: publish stage:profile, stage:filter
>  2: load DS0003 narratives for h and each c ∈ C
>  3: π_h ← chat_json(persona.txt | h);  publish persona, motifs ∅
>  4: for each c ∈ C in parallel:
>  5:    π_c ← chat_json(persona.txt | c)
>  6:    publish persona, motifs = M(h, c)
>  7: wait for advance_event;  drain hint queue
>
>  8: for round r = 2, 3, 4, 5:                          # focus rotates
>  9:    (S_r, Q_r) ← chat_json(query.txt | h, π_h, {π_c}, r)
> 10:    for each c ∈ C in parallel:
> 11:       (a_{c,r}, s_{c,r}) ← chat_json(answer.txt | c, π_c, π_h, q_{c,r}, r)
> 12:       publish query, answer
> 13:    publish round_scores for round r
> 14:    publish round_paused;  wait;  drain hints
>
> 15: compute score_i per Eq. 1 using s_{i,5}, t_{i,5};  rank descending
> 16: publish final_ranking
> 17: on user accept:  commit_match;  broadcast match-accepted
> ```

Algorithm 1 formalises the round loop. Round 1 generates personas in parallel; rounds 2–5 walk through canonical deliberation foci (*impressions*, *deep-dive*, *rebuttals*, *alignment*) by interpolating the focus description into the prompt; round 6 computes Eq. 1.

Critically, every round terminates at a `round_paused` frame and the orchestrator suspends on an `asyncio.Event` that is set only when the operator clicks **Approve & Advance**. This gating realises DG4: hints submitted during the pause are processed before the next round begins. Per-call exception handling falls back to a deterministic heuristic so the protocol remains complete and the frame stream remains contiguous when the LLM endpoint errors.

## 6.3 Hint semantics

Hint addresses parse as:

| Address | Routing |
|---|---|
| `@target` | husband's prompt only |
| `@c-XX` | candidate `XX` only |
| `@everyone` *(or no address)* | all actors |

Verbs (**boost**, **penalise**, **eliminate**, **accept**) trigger client-side mirror effects (e.g., the candidate card greys out on **eliminate**) so the operator's intent is visible immediately, even before the next prompt materialises.
