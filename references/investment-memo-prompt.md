# Investment Memo Philosophy & Prompt Guide

This document defines the philosophical principles and quality standards that underpin Mode D (Investment Memo) analysis. The Analyst agent reads this alongside `analysis-framework-memo.md` for Mode D.

---

## The Variant View Principle

The Variant View is the intellectual core of every investment memo. Without a genuine variant view, a memo is a data summary — not an investment thesis.

### Definition

A **Variant View** is a specific, well-reasoned disagreement with the current market consensus — not about whether the stock is "cheap" or "expensive" but about **what the market believes vs. what is actually happening**.

The market consensus is embedded in the current price. To have a variant view, you must:
1. Know what the market is pricing in (reverse-engineer the assumptions)
2. Identify where you disagree and why
3. Have a falsifiable belief — one that can be proven right or wrong by observable events

### The "Replace the Company Name" Test

After writing every Variant View statement, apply this test:

*Replace the company name with its #1 direct competitor. Is the statement still true?*

- If YES → the statement is generic. It says nothing specific about *this* company. Rewrite.
- If NO → the statement is company-specific. Acceptable.

**Examples of failed Variant Views (generic)**:
> "The market is underpricing the company's long-term growth potential in a large and expanding TAM."
→ This could be said about any growth company. FAIL.

> "Management has a track record of disciplined capital allocation and shareholder value creation."
→ This is PR copy, not an investment view. FAIL.

> "The stock is undervalued relative to peers on a P/E basis."
→ "Cheap" is not a thesis. Why is it cheap? Why should it re-rate? FAIL.

**Examples of passing Variant Views (specific)**:
> "Consensus models NVDA's Data Center at 42% revenue growth, but H100 export restrictions to China (announced Nov 2023) have been partially offset by A800/H800 deployments, and the Q2 datacenter order backlog disclosed on the last earnings call implies $14B+ in committed shipments through Q3 2025 — 35% above consensus. The market has not updated models for this backlog conversion timeline."
→ Specific company data, specific market assumption, specific disagreement. PASS.

> "삼성전자는 현재 PBR 1.1배에 거래중으로, HBM3 수율 문제가 지속될 것을 반영. 그러나 2024 Q3 실적 발표에서 공시된 HBM3E 전환율 65%는 당초 시장 예상(40%)보다 25pp 높았으며, 이는 2025년 AI 메모리 ASP 하락이 시장 예상보다 완만할 것임을 시사."
→ Specific metric (HBM3E 전환율), specific market assumption (40%), specific data point (65%). PASS.

---

## The Mechanism Requirement

Every risk identified in the memo must have a **mechanism** — a step-by-step causal chain from the risk event to the stock price impact.

### Why Mechanisms Matter

"Competition risk" is not actionable. It doesn't tell you:
- What specifically competes
- How the competition affects unit economics
- At what revenue scale the impact becomes material
- What the stock multiple compression would be

**Mechanism formula**:
```
[Risk Event] → [Operational Impact] → [Financial Impact ($)] → [Multiple Compression / Re-rating]
```

**Example without mechanism (FAIL)**:
> "Competition from Google Cloud is a risk."

**Example with mechanism (PASS)**:
> "GCP's enterprise storage product, launched Q3 2024 at ~35% below {ticker}'s list price, is targeting the same Fortune 500 buyer cohort that accounts for 42% of {ticker}'s revenue ($X.XB of $X.XB TTM). If GCP displaces 15% of this segment over 24 months, {ticker}'s revenue falls ~$XB (6% of TTM), operating leverage compresses EBITDA by ~$XB (12% of TTM EBITDA), and the stock would likely re-rate from 22x to 17x EV/EBITDA, implying ~28% downside from current price."

---

## The Exit Conditions Framework

Investment memos must pre-define exit conditions before entering a position. This prevents anchoring (holding a losing position because you don't want to admit you're wrong) and prevents premature exits (selling a winning position because it looks "expensive").

### Three Types of Exit Conditions

**Type 1 — Thesis Achieved (Positive Exit)**
The original thesis played out. Target price reached. Valuation has re-rated. Time to capture gains.
- Trigger: specific price or multiple target + catalyst
- Example: "Exit when stock reaches $X (18x NTM P/E) OR when next quarter's Cloud ARR growth exceeds 35% (confirming the thesis) — whichever comes first"

**Type 2 — Thesis Broken (Stop-Loss / Risk Management)**
The thesis was wrong. Cut the position to stop the losses.
- Rules: Must be **specific and testable** — not price-based alone
- Must be **pre-defined** before entering the position
- Example of FAIL: "Exit if stock falls 20%." (Pure price-based — doesn't tell you if the thesis is broken)
- Example of PASS: "Exit if: (1) Revenue growth decelerates below 10% YoY for 2 consecutive quarters; OR (2) Operating margin contracts by more than 300bp in any quarter; OR (3) Management guides below consensus by >10% on the next earnings call"

**Type 3 — Better Opportunity (Opportunity Cost)**
Capital is better deployed elsewhere. Not about being wrong — about portfolio optimization.
- Example: "Consider replacing with {peer} if {peer}'s EV/EBITDA drops below {X}x while growth rate remains comparable"

---

## The Pre-Mortem Technique

Before finalizing a memo, write a **pre-mortem**: imagine it's 12 months from now and the investment has lost 30%. What happened?

This forces the analyst to think through the most likely failure modes *before* committing to a position, rather than rationalizing them away.

**Format**:
> "If this investment loses 30% over the next 12 months, the most likely cause would be: [specific scenario written in past tense, as if it already happened]. This would have been preceded by: [early warning indicator]. The decision to hold through these warning signs would have been wrong because: [reflection on what the stop-loss criteria should have been]."

---

## Quality Standards for Mode D

### Completeness
All 10 sections must be present. No section shorter than 50 words. Total 3,000–4,000 words.

### Specificity
Every paragraph that makes a claim about the company's competitive position, market opportunity, or risk must include ≥1 specific data point from the research.

### Consistency
- Scenario probabilities must sum to 100%
- R/R Score must be calculated correctly and match the narrative
- Bull case and Bear case assumptions must be mutually exclusive

### Non-fabrication
If data is unavailable (Grade D), it is excluded. The analyst notes the exclusion explicitly. No estimates, approximations, or "best guesses" for Grade D data.

### Attribution
Every claim based on external data has a source tag. Claims without source tags are either:
- Logical inferences from tagged data (acceptable, mark as [Calculated])
- Analyst judgment/opinion (acceptable, label as "Analyst estimate:" or "Assessment:")
- Fabrications (not acceptable — will be caught by the Critic quality check)

---

## L/S Fund Memo Style Principles

Mode D is modeled after long/short hedge fund investment memos. Key style differences from sell-side research:

| Dimension | Sell-Side Style | L/S Fund Style |
|-----------|----------------|----------------|
| Price target | Point estimate with specific methodology | Range with scenario weighting |
| Thesis | "We maintain our Buy rating..." | "Our variant view is X vs. market's Y" |
| Risk section | Brief, list format | Mechanistic, quantified |
| Conviction | Rating (Buy/Hold/Sell) | Position sizing + entry/exit conditions |
| Update frequency | Quarterly earnings | Event-driven, continuous monitoring |
| Writing style | Formal, hedged | Direct, specific, opinion-forward |

The memo should read as if written by an analyst presenting to an investment committee — not as if written for retail investors.

---

## What Good Mode D Output Looks Like

**The thesis can be tested**: Each scenario has specific, observable triggers. The reader knows what to look for.

**The analyst has a view**: Not "the stock may go up or down depending on macro conditions." A view is: "We believe X is mispriced because Y, and we expect Z catalyst to surface this within W months."

**The risks are real**: Not "competition, regulation, macro." Real risks with real mechanisms: "If {specific event}, then {specific financial impact}, then {stock goes to $X}."

**The writing is direct**: Eliminate hedge words that add no information: "relatively," "somewhat," "potentially," "may or may not." Make every sentence a claim that can be true or false.

**The data supports the thesis**: Every key claim has a source tag. The analyst's view is built on facts, not vibes.
