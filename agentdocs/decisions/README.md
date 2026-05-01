# Agent Decision Records

This folder contains Agent Decision Records, abbreviated `AgDR`. These are short records of meaningful decisions made by agents while working on the project.

Rules for future agents:
- Create a new file for each durable or meaningful decision.
- Use the next sequential id and filename format: `AgDR-NNNN-short-kebab-description.md`.
- Never renumber existing records.
- Keep each record focused on one decision.
- Include YAML frontmatter with `id`, `timestamp`, `agent`, `model`, `trigger`, and `status`.
- Use `status: executed` for decisions already acted on, `status: proposed` for recommendations, and `status: superseded` only when a later AgDR replaces the decision.
- In the body, describe context, decision, accepted tradeoffs, alternatives considered, and verification when relevant.
- Do not store secrets, PHI, or private credentials in decision records.

Suggested body format:

```markdown
# Short decision title

> In the context of ...
> I decided to ...
> accepting ...
> to achieve ...
> Alternatives considered: ...

## Verification

- ...
```
