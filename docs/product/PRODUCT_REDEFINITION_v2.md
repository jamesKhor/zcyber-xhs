# Product Redefinition: zcyber-xhs v2

**From:** Alex — Product Lead, zcyber-xhs
**To:** Vincent (Principal Architect), Raymond (Engineering Lead), Ken (Design Lead)
**Cc:** Maya (Marketing Lead)
**Date:** 2026-04-15
**Re:** Post-Maya-handoff product redefinition, roadmap, and parallel team briefs

---

## Preamble — Why We're Redefining Now

Maya's brief gives us two gifts and one demolition.

**The demolition:** CTF is dead. Not "underperforming" — structurally broken. It's jargon-gated, algorithmically hostile (delayed reveal), and funnel-orphaned. We kill it, not tune it.

**The gifts:**
1. A replacement archetype (`hacker_pov`) that is the single format which wins on BOTH XHS and Instagram — a rare unification.
2. A viral hook taxonomy (10 patterns, 5 per platform) that turns prompt engineering from vibes into a system.

Together these force a bigger question: **what is this product, actually?** We've been describing zcyber-xhs as "an XHS publishing pipeline." That was true in v1. It's no longer true. Reframing below.

---

# OUTPUT 1 — Product Vision & North Star

## 1.1 What zcyber-xhs IS

> **zcyber-xhs is a multi-profile, multi-platform top-of-funnel content engine that converts expert knowledge into verifiable, shareable, narrative content for discovery-stage audiences — and funnels them to owned destinations (zcybernews today, future verticals tomorrow).**

Three words matter in that sentence:

- **Engine**, not pipeline. An engine is reusable across domains. Cybersec is the first fuel; pets is the second; a third vertical is plausible within 12 months.
- **Multi-platform.** XHS is the beachhead. Instagram/TikTok is the adjacent market. The engine produces platform-native artifacts from one content spine.
- **Verifiable.** Maya's #1 XHS hook is "verifiable personal risk." This is not decoration — it's the product's defining content principle. If a post cannot be verified or acted on by the reader in <30 seconds, it's off-brand.

What we are NOT:
- Not a social media scheduler (Buffer/Hootsuite do that better).
- Not a generalist LLM content tool (ChatGPT does that).
- Not a news aggregator (zcybernews does that).

## 1.2 North Star Metric

**Weekly Qualified Funnel Arrivals (WQFA)** = unique visitors to `zcybernews` from zcyber-xhs traffic sources (link-in-bio clicks + `#zcybernews` tag referrals + UTM-tagged article links) who read ≥1 article.

Why this metric:
- It's the only number that proves the funnel works. Follower count, likes, even engagement rate are proxies. Arrivals are the product.
- It's cross-platform from day one — XHS and Instagram both contribute to the same number.
- It forces us to instrument the zcybernews → zcyber-xhs loop that's currently unbuilt.

**Supporting metrics (guardrails, not targets):**
- Save rate (XHS native signal for high-quality content) — floor: 8%
- Post-level engagement rate per archetype — used for archetype health
- Shadowban incidence — must stay at 0
- Human review queue aging — approval SLA <24h

## 1.3 The Three Personas

### Persona 1 — The Operator (Primary user of the product)
**Who:** James, solo founder running zcybernews + zcyber-xhs. Technical. Time-starved. Uses the tool daily for ~20 minutes.
**Job-to-be-done:** "Get tomorrow's post approved, see whether yesterday's is working, and know if there's anything hot I should hijack the schedule for."
**What he needs from the product:** A single-screen dashboard answer to "am I on track this week?" + frictionless review/approve + cross-project signal ("zcybernews just published something big — want to retheme Friday?").

### Persona 2 — The XHS Audience (ZH, discovery-stage, non-expert)
**Who:** Chinese-speaking XHS user, 22–35, curious about cyber/tech but not a professional. Likely a student, office worker, or adjacent-tech professional (designer, PM, marketer) who's had a scare (phishing attempt, leaked password, account takeover).
**Job-to-be-done:** "Help me feel safer online in 30 seconds without condescending to me."
**Content they reward:** Immediately actionable, personally verifiable, outrage-worthy, identity-signaling.
**Conversion trigger:** They tap link-in-bio when a card gives them a problem they now want to understand deeper — Friday's `news_hook` and Sunday's `hacker_pov` are the prime conversion surfaces.

### Persona 3 — The Instagram/TikTok Audience (EN, narrative-seeking, identity-performing)
**Who:** English-speaking Gen-Z/younger-millennial, US/UK/SEA. Consumes cyber content as infotainment and identity ("I'm the friend who knows about security").
**Job-to-be-done:** "Give me a story I can retell at brunch."
**Content they reward:** Cinematic POV, stakes escalators, expert contradiction of US/EU brands.
**Conversion trigger:** Saves > shares > swipe-through on carousel. Link-in-bio for deep dives.

## 1.4 What "Winning" Looks Like in 12 Months (by April 2027)

1. **WQFA ≥ 2,000/week sustained for 8 consecutive weeks.**
2. **Two profiles in production.** `cybersec` is mature; `pets` has 90 days of consistent publishing and its own measurable funnel.
3. **Instagram channel live with ≥ 5k followers.**
4. **Friday `news_hook` auto-triggered by zcybernews events ≥ 70% of weeks.**
5. **Zero shadowbans, zero manual rescues.**
6. **Founder can run the whole thing in ≤ 15 min/day.**

## 1.5 The Three Biggest Product Bets

**Bet #1 — The Viral Hook Framework is a system, not taste.**
Maya's 10 hook patterns, baked into prompts and testable via A/B, produce measurably better content than the current "LLM free-writes a hook."

**Bet #2 — The profile abstraction generalizes.**
Cybersec and pets share >80% of the engine with <20% vertical-specific config.

**Bet #3 — `hacker_pov` is the bridge archetype to Instagram.**
The POV narrative format is sufficient to bootstrap Instagram presence without a full platform-specific playbook.

---

# OUTPUT 2 — Roadmap: Now / Next / Later

Effort sizing: XS (<1 day), S (1–3 days), M (1–2 weeks), L (3–6 weeks), XL (>6 weeks).

## 2.1 NOW (weeks 1–6, by end of May 2026)

**Theme: Kill CTF, ship hook framework, professionalize the daily-use surface.**

| # | Item | Owner | Metric | Effort |
|---|------|-------|--------|--------|
| N1 | Replace CTF with `hacker_pov` (ZH + EN prompts, 20-topic bank, Sunday slot) | Raymond + Prompt Engineer | `hacker_pov` saves ≥ 2x CTF baseline within 4 weeks | M |
| N2 | Bake Maya's 5 XHS hook patterns into all 6 remaining ZH prompts | Raymond + Prompt Engineer | Per-archetype engagement lift measurable after 14 days | M |
| N3 | Content calendar week view in web UI | Raymond | Operator answers "am I on track?" in 1 screen | S |
| N4 | Dashboard v1 — this-week counts, topics remaining, 30d engagement, needs-review | Raymond | Replaces current home page | M |
| N5 | Bulk approve / bulk render buttons in Review page | Raymond | Review session time drops 40% | S |
| N6 | Visual audit + cybersec profile identity lock | Ken | "Feels like a product, not a script" | M |
| N7 | Web UI polish pass based on Ken's audit | Raymond (from Ken's specs) | Audit P0+P1 issues closed | M |
| N8 | 5 ADRs from Vincent (profile arch, multi-platform, A/B, analytics, event bus) | Vincent | 5 ADRs merged | M |

**Exit criteria for NOW:** `hacker_pov` publishing Sundays, all ZH prompts carry explicit hook pattern, operator uses dashboard as daily home, Vincent's ADRs unblock NEXT.

## 2.2 NEXT (weeks 7–16, by end of July 2026)

**Theme: Prove the engine generalizes (pets profile) and go multi-platform (Instagram).**

| # | Item | Owner | Metric | Effort |
|---|------|-------|--------|--------|
| X1 | Profile system refactor per ADR-001 | Raymond | Cybersec pipeline identical pre/post | L |
| X2 | `pets` profile — 2 archetypes, topic banks, visual identity, own CTA | Raymond + Ken + Prompt Engineer | 14 days consistent pets publishing | L |
| X3 | Instagram carousel output — 1080×1080, 5-slide, EN-native hook patterns | Ken + Raymond | First 10 IG posts published | L |
| X4 | Cross-platform analytics schema + ingestion (XHS + IG side-by-side) | Raymond (per ADR-004) | Can compare hook patterns across platforms | M |
| X5 | A/B hook testing infrastructure | Raymond (per ADR-003) | 20 A/B-tested posts with statistical read | L |
| X6 | Reels script format output (20s vertical, EN, from `hacker_pov`) | Raymond + Prompt Engineer | Script output exists for manual recording | M |
| X7 | New templates: stakes escalator cascade, tribe signal | Ken + Raymond | 2 new templates in prod use | M |
| X8 | Dashboard v2 — cross-platform, cross-archetype performance | Ken (spec) + Raymond (build) | Founder spots underperforming archetype in 10 seconds | M |

## 2.3 LATER (months 5–12)

**Theme: Close the cross-project funnel loop and mature the intelligence layer.**

| # | Item | Owner | Metric | Effort |
|---|------|-------|--------|--------|
| L1 | zcybernews → zcyber-xhs event bus — auto-trigger Friday `news_hook` | Vincent + Raymond | ≥70% of Fridays auto-triggered | L |
| L2 | UTM-tagged link-in-bio infrastructure — per-post, per-platform attribution | Raymond + zcybernews side | WQFA metric fully instrumented | M |
| L3 | Hook pattern recommender — ML-based, trained on A/B history | AI Engineer + Raymond | Beats random selection on engagement | L |
| L4 | Third profile (finance / travel safety / parenting tech — Maya decides) | Full team | 30 days publishing; WQFA contribution measurable | XL |
| L5 | TikTok native distribution | Maya + Ken + Raymond | First 30 TikToks published | L |
| L6 | Founder mobile companion — approve/reject from phone | Raymond | Review SLA drops below 6h | M |
| L7 | Content safety v2 — shadowban predictor model | AI Engineer | False negative rate <5% | L |
| L8 | Multi-operator support — delegate review to VA/team member | Vincent + Raymond | Founder delegates ≥50% of reviews | L |

## 2.4 Explicitly Not On The Roadmap

- Native XHS API integration — stay on xiaohongshu-mcp.
- Custom LLM fine-tuning — prompt engineering is sufficient through 12 months.
- Multi-language beyond ZH/EN — not until WQFA proves itself.
- User-generated content / community features — broadcast product, not platform.
- Monetization features — owned by zcybernews.

---

# OUTPUT 3 — Team Handoffs

## 3A — Handoff to Vincent (Principal Architect)

5 ADRs requested before week 3. Location: `docs/adr/`.

### ADR-001: Profile System Architecture
**Decision needed:** Directory convention vs. DB entity? Contract between profile components? How does CLI/web switch active profile? Single-process or multi-profile simultaneously? Migration path for cybersec.

**Product constraint:** Raymond must ship `pets` in weeks 9–12 without touching cybersec code.

### ADR-002: Multi-Platform Output Architecture
**Decision needed:** Canonical intermediate representation (IR)? Where does per-platform prompting happen? Playwright stays or different carousel renderer? Does `hacker_pov` get a special cross-platform path?

**Product constraint:** One operator approval action approves all platform variants. No per-platform review queue.

### ADR-003: A/B Hook Testing Architecture
**Decision needed:** Unit of A/B (alternating days same archetype)? Variant lineage data model? Stopping rule (Bayesian Beta-Binomial on save rate)? Where does variant selection happen — generation or post-generation? Control for day-of-week bias?

**Product constraint:** First live test running by week 10. Spreadsheet-readable output acceptable for v1.

### ADR-004: Analytics Data Model
**Decision needed:** Star schema or flat fact table? WQFA join to zcybernews arrivals (UTM deterministic or probabilistic)? Retention policy? Same SQLite or separate analytics DB? Who owns zcybernews-side UTM ingestion?

**Product constraint:** WQFA = one number per week, trivially, without SQL gymnastics.

### ADR-005: zcybernews → zcyber-xhs Event Bus
**Decision needed:** Transport (webhook POST vs. polling vs. file-based)? Event schema for `news_published`? Idempotency? Backpressure when multiple articles publish same day? Auth (HMAC shared secret).

**Product constraint:** Buildable in one zcyber-xhs session — full contract specified here, zcybernews emitter is a separate handoff.

---

## 3B — Handoff to Raymond (Engineering Lead)

### Priority 1 — Kill CTF, Ship `hacker_pov` [M, unblocked]
- Replace Sunday slot. Use `hacker_pov.j2` (ZH) + `hacker_pov_en.j2` (EN) + `hacker_pov.yaml` (20 topics).
- Use existing `terminal_dark` template.
- DB: map existing `ctf` rows to deprecated status — do not drop data.
- Tests: safety + generate tests pass; one golden-output test.

### Priority 2 — Viral Hook Framework in All ZH Prompts [M, needs Prompt Engineer week 1]

| Archetype | Primary Hook Pattern |
|-----------|---------------------|
| `problem_command` (Mon) | Verifiable Personal Risk |
| `tool_spotlight` (Tue) | Tribe Signal |
| `everyday_panic` (Wed) | Stakes Escalator |
| `before_after` (Thu) | Expert Contradiction |
| `news_hook` (Fri) | Insider Reveal |
| `mythbust` (Sat) | Expert Contradiction |
| `hacker_pov` (Sun) | POV/Cinematic (native) |

Create `config/prompts/_hook_patterns.j2` as partial library. Hook pattern is parameter, not LLM inference.

### Priority 3 — Web UI Maturity
- **R3** Calendar week view `/calendar` — 7-column grid, post status, quick-action links. [S, unblocked]
- **R4** Dashboard v1 — 4 tiles: this-week, topics-remaining, 30d sparkline, needs-review. [M, Ken spec unblocks polish]
- **R5** Bulk approve / render / reject in Review page — 2-wide concurrency. [S, unblocked]

### Priority 4 — Pets Proof of Concept [M, needs Prompt Engineer + Maya topic banks]
- `fluffy_moment` + `pet_tip_of_day` archetypes, 10 topics each.
- Flip `pets_example` status to active behind feature flag.
- **Do not over-invest** — will be refactored when ADR-001 lands.

### Priority 5 — EN Instagram Carousel v0 [S, needs Ken's square template]
- `--format carousel` flag. `terminal_dark_square.j2` at 1080×1080. 5 slides per post.
- Full IG pipeline (auto-publish, analytics) is NEXT — do not scope here.

### Priority 6 — Polish Pass [M, blocked on Ken's audit]
- Execute Ken's P0 + P1 audit findings.

### Dependency Map (NOW horizon)
```
Week 1-2: R1 (hacker_pov), R3 (calendar v1), R5 (bulk ops) — all unblocked
Week 1-2: Prompt Engineer delivers hook partials → unblocks R2
Week 1-2: Ken audit → unblocks R8
Week 2-4: R2 (hook framework), R4 (dashboard v1), R7 (carousel v0)
Week 3-5: R6 (pets proof)
Week 4-6: R8 (polish), baseline engagement measurement
Week 5-6: Vincent's 5 ADRs merged → unblocks NEXT horizon
```

---

## 3C — Handoff to Ken (Design Lead)

### Brief 1 — Visual Audit (deliver week 1)
Full audit of Generate, Review, Approved, Export pages. Inventory: fonts, spacing, colors, components. Prioritized findings: P0 (embarrassing) / P1 (inconsistent) / P2 (could be better).

### Brief 2 — Dashboard Redesign (deliver week 2)
Hi-fi mock of dashboard, default + alert states. Status visual language (draft/approved/published/failed) — legible at a glance, colorblind-safe. Minimal sparkline pattern. Layout must be palette-swappable for other profiles.

### Brief 3 — Content Calendar UI (deliver week 2)
Week-grid with 7 day columns. Archetype labels. Post-status pills. Hover/click affordances. Empty state. Prev/next week navigation.

### Brief 4 — Image Template Expansion
- **4A** (week 3, XS): `terminal_dark` POV review — does it serve `hacker_pov` or need adjustment?
- **4B** (week 4, S): Square-format (1080×1080) variant of `terminal_dark` for IG carousel.
- **4C** (week 5, M): Stakes Escalator cascade template — arrow-chained consequence cards.
- **4D** (week 5, M): Tribe Signal template — insider/outsider split identity visual.

### Brief 5 — Profile Identity System
- **5A** (week 5, S): Cybersec token spec — `#00B8FF` cyan, `#0d1117` navy, Geist fonts. JSON/CSS custom properties format.
- **5B** (weeks 5–6, M): Pets profile visual identity. Distinct palette + aesthetic. Coordinate with Maya.
- **5C** (week 6, S): Profile-switching chrome pattern in web UI — how UI communicates active profile.

---

## Closing Timeline

| Week | Key milestones |
|------|---------------|
| 1 | R1 (hacker_pov) live, R3+R5 in flight, Ken delivers audit, ADR-001+002 drafted |
| 2 | R2 (hook framework) starts, R4 starts, Ken delivers dashboard + calendar mocks |
| 3 | All 5 ADRs merged, dashboard v1 + calendar v1 live, `hacker_pov` publishing Sundays |
| 4 | Hook framework live in all archetypes, Ken's 4A+4B templates in review |
| 5 | Pets proof started, Ken's 4C+4D+5A in progress |
| 6 | NOW horizon complete. Retrospective + NEXT-horizon kickoff. |

Weekly 30-min product sync, Mondays. Alex owns agenda.

---

**— Alex**
**Product Lead, zcyber-xhs**
**2026-04-15**
