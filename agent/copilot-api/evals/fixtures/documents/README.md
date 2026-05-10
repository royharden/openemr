# Synthetic Document Fixtures

These eight files are the synthetic documents used by Wk2 eval cases and
the demo. They are committed to git on purpose — graders need them to
reproduce the demo, and the assignment explicitly calls them "synthetic
demo data" (Plan §3 decision #20, antipattern §13.14).

## Contents

| Patient | Document type | File |
|---|---|---|
| p01 (Mr. Chen) | Lab — lipid panel (typed PDF) | `p01-chen-lipid-panel.pdf` |
| p01 (Mr. Chen) | Intake form (typed PDF) | `p01-chen-intake-typed.pdf` |
| p02 (Whitaker) | Lab — CBC (typed PDF) | `p02-whitaker-cbc.pdf` |
| p02 (Whitaker) | Intake form (typed PDF) | `p02-whitaker-intake.pdf` |
| p03 (Reyes) | Lab — HbA1c (handwritten PNG) | `p03-reyes-hba1c.png` |
| p03 (Reyes) | Intake form (handwritten PNG) | `p03-reyes-intake.png` |
| p04 (Kowalski) | Lab — CMP (dirty/scanned PDF) | `p04-kowalski-cmp.pdf` |
| p04 (Kowalski) | Intake form (handwritten PNG) | `p04-kowalski-intake.png` |

## What each one is for

- **p01 (Chen)** — happy-path demo. Typed PDFs with clean text layers.
  Used by the demo recording and the lowest-difficulty eval cases.
- **p02 (Whitaker)** — secondary happy-path. Same difficulty as p01.
- **p03 (Reyes)** — stress: handwritten / OCR-required. Eval cases here
  expect `bbox_unit="approximate"` and `confidence < 1.0`.
- **p04 (Kowalski)** — stress: dirty scan + handwriting mix. Verifies
  that vision extraction correctly drops claims it cannot ground in the
  PDF text layer (anti-pattern §13.6: never trust VLM-emitted bbox).

## Identity

These are **synthetic** — not PHI, not derived from real patients.
They live in version control. Do not gitignore them.

If a future contributor is tempted to swap in real-world examples,
that is a HIPAA violation in this repo. Synthetic only.
