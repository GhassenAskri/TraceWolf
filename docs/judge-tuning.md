# Judge tuning

Part of the [TraceWolf design](trace-wolf-design-paper.md). Runs beside the loop and serves [Mistake detection and clustering](mistake-detection-and-clustering.md) and [Regression tests and verification](regression-tests.md).

Judge tuning checks the LLMJ and makes it better. The same LLMJ writes the notes in **[Mistake detection and clustering](mistake-detection-and-clustering.md)** and decides the test results in **[Regression tests and verification](regression-tests.md#3-assertion)**, so both depend on it. It runs beside the loop and never blocks it: a note no human checked keeps the LLMJ's status.

```mermaid
flowchart LR
    N(["Notes<br/>(Mistake detection<br/>and clustering)"]) --> S["Sampling (1)"]
    S --> H["Judge review (2)"]
    H -- "status changes" --> AX(["Axial coding<br/>(Mistake detection<br/>and clustering)"])
    H -- "corrections" --> EX(["Examples (3)"])
    H --> SC(["Scores (4)"])
    EX -. "read before judging" .-> L(["LLMJ<br/>(Mistake detection<br/>and clustering)"])
```

## 1. Sampling

The LLMJ writes too many notes for humans to check them all, so we prepare three samples, each a list of notes:

```
UncertainSample = [Note]    // notes where status = "uncertain_mistake"
AccuracySample  = [Note]    // random notes where status = "mistake" or "uncertain_mistake"
RecallSample    = [[Note]]  // random conversations, each the list of its notes, where every status = "not_mistake"
```

Each sample has its own purpose: the Uncertain sample settles the notes the LLMJ doubted, the Accuracy sample measures how often its notes are right, and the Recall sample looks for mistakes it missed.

## 2. Judge review

For each note in a sample, a human answers whether it is a real mistake. The answer is then sent to up to three destinations: axial coding, where a changed status moves the note out of its cluster or into one ([final status](mistake-detection-and-clustering.md#1-open-coding)), examples ([3](#3-examples)) and scores ([4](#4-scores)). Sections [2.1](#21-uncertain-sample-review) to [2.3](#23-recall-sample-review) show this routing for each sample. Whole issues are reviewed in **[Issue review](issue-review.md)**.

### 2.1 Uncertain sample review

Notes where status = `uncertain_mistake`. The human decides whether each one is a real mistake.

```mermaid
flowchart LR
    US["Uncertain sample"] --> U1["uncertain_mistake → mistake"]
    US --> U2["uncertain_mistake → not_mistake"]
    AX(["Axial coding"])
    EX(["Examples"])
    U1 --> EX
    U2 -- "leaves its cluster" --> AX
    U2 --> EX
```

### 2.2 Accuracy sample review

Random notes where status = `mistake` or `uncertain_mistake`. The human decides whether each one is a real mistake and, if so, whether its evidence is right.

```mermaid
flowchart LR
    AS["Accuracy sample"] --> A1["mistake → mistake<br/>evidence right"]
    AS --> A2["mistake → mistake<br/>evidence wrong"]
    AS --> A3["mistake → not_mistake"]
    AS --> A4["uncertain_mistake → mistake"]
    AS --> A5["uncertain_mistake → not_mistake"]
    AX(["Axial coding"])
    EX(["Examples"])
    SC(["Scores"])
    A1 --> SC
    A2 --> EX & SC
    A3 -- "leaves its cluster" --> AX
    A3 --> EX & SC
    A4 --> EX & SC
    A5 -- "leaves its cluster" --> AX
    A5 --> EX & SC
```

### 2.3 Recall sample review

Random conversations where all notes = `not_mistake`. The human looks for a missed mistake; if there is one, they mark that span's note as `mistake` and write its evidence.

```mermaid
flowchart LR
    RS["Recall sample"] --> R1["one note: not_mistake → mistake<br/>evidence written by the human"]
    RS --> R2["nothing changed"]
    AX(["Axial coding"])
    EX(["Examples"])
    SC(["Scores"])
    R1 -- "joins a cluster" --> AX
    R1 --> EX & SC
    R2 --> SC
```

## 3. Examples

Human corrections the LLMJ reads before judging new spans. An example is created when the human answer differs from the LLMJ's status, or when the evidence is wrong:

```
Examples = [Example]
```

```jsonc
// Example
{
  "note_id": string,                 // the note the human checked
  "llmj_status": Status,
  "human_status": Status,
  "evidence_right": boolean | null,  // Accuracy sample only
  "human_evidence": string | null    // Recall sample only
}
```

## 4. Scores

Reliability measures of the LLMJ, computed from the Accuracy and Recall samples. Each score counts right and wrong answers; its value is right ÷ (right + wrong):

```
ScoreType = "precision_score" | "evidence_score" | "miss_score"
```

```
Scores = [Score]
```

```jsonc
// Score
{
  "type": ScoreType,
  "right": int,
  "wrong": int   // for miss_score: conversations with a missed mistake
}
```
