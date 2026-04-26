# 9 Expert Study

We conducted a 75-minute semi-structured walkthrough with five domain experts (three historians, two computational genealogists) on the 1882 and 1903 cohorts. Each session covered the three use cases above and concluded with a Likert questionnaire on perceived usefulness, interpretability, and trust.

Median scores (1–7, higher better):

| Dimension | Median |
|---|---|
| Usefulness for marriage reconstruction | 6 |
| Interpretability of agent reasoning | 6 |
| Trust in **MAS**-only commits | 5 *(with a 4 from the most conservative reviewer)* |

Three salient qualitative observations emerged:

- *The hint console was the most appreciated affordance.* All five experts referenced its alignment with how they currently reason from partial archival evidence. Two experts requested finer-grained role addressing (e.g., `@household-head`).
- *The provenance chips changed how experts read V2.* Several spontaneously remarked that the convergent **HGT**+**MAS** chip rows were the ones they would trust without further inspection; **MAS**-only rows prompted them to expand the conversation transcript.
- *The restore button was used non-trivially.* Across the five sessions, restore was clicked 14 times, of which 9 led to a re-deliberation that produced a different commit. The cumulative-error guard is empirically used, not theoretical.
