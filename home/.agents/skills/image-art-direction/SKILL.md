---
name: image-art-direction
description: >-
  Directs composition, likeness, light, and localized edits for still images.
  Use when choosing visual references, refining a portrait, or comparing drafts against
  someone's taste.
  Exact prompt submission without creative decisions belongs to the provider skill.
---

# Direct a still image

Read `~/.agents/references/communication-rules.md` before drafting instructions or reporting results.
Start with the intended display, what viewers should notice first, and what must remain unchanged.
For critique alone, inspect the supplied image without submitting jobs.

Read [visual practices](references/visual-practices.md) before choosing references, writing
creative instructions, or correcting a proof.
Distinguish the user's stated preference from your interpretation.

## Run a draft round

1. Choose one visual question and a baseline that preserves accepted details.
2. Brief a fresh worker for each authorized round. The lead reviews the result independently.
3. Target 960 pixels on the long edge. Choose the cheapest generation tier sufficient for review.
    Downsampling an expensive generation saves no generation credits.
4. For authorized Higgsfield jobs, read the installed `higgsfield-generate` skill before submission.
    If unavailable, report the limitation. Never silently switch providers or upload references.
    Local edits need no generation provider.
5. Inspect the result against its baseline. Keep intermediate files temporary.

## Deliver one image

Return one medium-sized image and a short credit line. Omit extra crops, variants, and comparisons.
Report the actual charge per generation, including attempts omitted from delivery.
For multiple generations, add the request total. Include opening and remaining balances each round.
For local edits, report zero generation credits.
Label unavailable figures; never substitute quotes for charges.
Exclude unrelated transactions from request totals.

Keep private references, proofs, prompts, and billing evidence in the owning project.
When results repeat a defect, change the method rather than repeating the same request.
Wait for the user to select a specific draft before upscaling or finishing it.
Compare the finished image against that draft for drift. Selection does not authorize publication.
