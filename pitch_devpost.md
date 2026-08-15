# Moltex — the last WordPress plugin

> Install the Moltex Exporter plugin, download your site blueprint, and let Codex rebuild it as a fast,
> Git-managed Astro site that a machine can prove is correct.
> Continue development with natural language
> Host it on ChatGPT sites, or a potato, Astro runs everywhere including almost free serverless options (enough for most WP sites)

## Inspiration

WordPress powers more than 40% of the web. And you know why? Because WordPress is flexible to serve everyone, which means it satisfies NO ONE. Most of those sites are content-led and maintained by 1 or 2 persons:
- blogs
- portfolios
- brochure sites
- directories.

Leaving WordPress usually means a slow, artisanal, error-prone and EXPENSIVE rebuild where "done" is a matter of opinion. I wanted the
migration to be **repeatable and verifiable** instead — observe the real site,
preserve the evidence, generate a solid foundation, let an agent do the judgment
work, and have an independent checker decide when it's actually finished.

## What it does

Moltex turns a live WordPress site into a verified Astro 5 repository:

1. **Capture.** A WordPress plugin exports content, routes, menus, media, SEO, and
   visual evidence into a single versioned, privacy-filtered ZIP.
2. **Compile.** A local harness safely parses the ZIP and normalizes it into
   canonical migration contracts — every route, asset, redirect, and capability,
   each traceable back to source evidence.
3. **Generate.** It produces a conservative, buildable Astro baseline plus a bounded
   set of Codex tasks, each with its own evidence, scope, and acceptance checks.
4. **Rebuild.** Codex completes the tasks inside allowed file boundaries.
5. **Verify.** A self-contained Node verifier shipped inside the repo checks routes,
   links, assets, SEO, redirects, accessibility, and visual parity. The verifier —
   not the agent — is the final authority on completion.

The result is a normal Git-managed Astro project with a committed lockfile and local
assets that never calls WordPress at runtime.

## How we built it

The core idea is **deterministic boundaries, agentic middle**:

- **`moltex_exporter`** — a WordPress/PHP plugin that only observes and packages the
  source. It makes no migration decisions.
- **`moltex_harness`** — a local Python project for safe intake, normalization,
  contract compilation, Astro generation, and task planning. All of it is
  deterministic.
- **Generated Node verifier** — small, dependency-light TypeScript/JS shipped inside
  each Astro workspace, with stable JSON result schemas and no runtime dependency on
  Python, WordPress, or any model API.
- **Assurance layer** — mutation testing that injects one known defect at a time and
  proves the verifier fails on exactly the right check and passes cleanly otherwise.

The whole migration runs from one command (`moltex create-site`) with a pinned
toolchain (Astro 5, Node 24.14.0, npm 10.9.2) so every rebuild is reproducible.

## Challenges we ran into

- **Trusting untrusted input.** Every ZIP entry, HTML fragment, and JSON file is
  hostile until proven safe. We had to reject traversal, symlinks, oversized
  archives, and checksum mismatches without ever executing source content.
- **Defining "done" objectively.** Completion had to be a *state* — every route,
  asset, and capability reproduced or explicitly disposed — not a percentage or a
  model's opinion.
- **Keeping the agent in bounds.** Codex needed enough context to do real work while
  being blocked from editing contracts, verifier code, or expected results.
- **Determinism at the edges.** Making intake, normalization, and verification fully
  reproducible so results didn't drift between runs.

## Accomplishments that we're proud of

- A migration where completion is *proven*, not claimed — an independent verifier
  gates the result.
- A clean split between deterministic transformation and agentic reconstruction.
- Mutation testing that proves our own checks actually catch regressions.
- End-to-end from a real WordPress export to a buildable, verified Astro repo with a
  single command.

## What we learned

- The most convincing demo isn't a wall of green checks — it's breaking one thing on
  purpose and watching the verifier localize the exact failure.
- Agents are far more effective with **bounded, evidence-backed tasks** than with a
  vague "copy this website" instruction.
- Preserving *evidence over inference* keeps ambiguity honest: unknowns become
  explicit decisions instead of invented answers.
- "Buildable before beautiful" — a credible conservative site beats ambitious broken
  output every time.

## What's next for Moltex, the last WordPress plugin

- Broaden supported site types beyond content-led sites through explicit, tested
  adapters rather than best-effort guessing.
- Richer visual parity and automated review to reduce manual sign-off.
- More capability adapters (forms, integrations) with clear reproduce / replace /
  externalize dispositions.
- A smoother operator experience: from WordPress plugin to a verified, deployable
  Astro repo in minutes.
