# AR Automation Prototype 

## What it does
A rules-based Python engine that automates the core loop of a generic
Accounts Receivable process: ingest an aging report, classify each account
into an escalation tier, prioritize the worklist, and auto-draft the
appropriate outreach — so a human just reviews and hits send instead of
starting from scratch on every account.

## Key design decision
Patient balances and insurance claims are escalated on **separate tracks**,
because they behave differently in the real world: patient balances need
reminders and payment plan offers, while insurance claims need payer
follow-up, EOB requests, and formal appeals. Treating them identically is a
common failure mode in naive AR automation — this prototype avoids it by
running two distinct rule sets.

## How it works
1. **Ingest** — reads an AR aging CSV (account, payer type, balance,
   invoice/due dates, claim status).
2. **Classify** — computes days overdue and maps each account to an
   escalation tier using payer-specific rules (e.g., a patient balance 61-90
   days overdue gets a pre-collections notice; an insurance claim 61+ days
   out gets a formal appeal).
3. **Prioritize** — scores each account by dollars at stake, weighted up as
   the claim ages (since the probability of ever collecting decays over
   time — this is the same logic as discounting a cash flow, applied to
   collections effort).
4. **Draft** — auto-generates the tier-appropriate email from a template,
   personalized with the account's details.
5. **Output** — writes a summary report (balance by payer type & tier), a
   prioritized worklist (sorted by score), and one email draft per
   actionable account.

## Tools used
- I asked Claude to generate some fake data to work with
- I used python and pandas for data cleaning
- Plain string templates for email drafting (no LLM dependency)
- Output to CSV + flat text files so it's easy to plug into any CRM,
  spreadsheet, or ticketing system as a next step

## What I'd build next
- Swap the static templates for a lightweight LLM pass that personalizes
  tone while keeping the underlying rule/tier deterministic (matches
  Amigo's philosophy: control + observability over the AI layer, not just
  raw automation)
- Add a feedback loop — track which auto-drafted emails actually resulted
  in payment/response, and use that to re-weight the priority score
- Real EHR/clearinghouse integration to pull aging data automatically
  instead of a static CSV
