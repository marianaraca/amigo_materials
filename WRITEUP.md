# AR Automation Prototype 

## What it does
A rules-based Python pipeline that automates the core loop of an
Accounts Receivable process: grabs an aging report, classifies each account
into a priority tier, and auto-drafts the
appropriate outreach. This is so a human can just review and hit send. 

## Steps
1. **Input** — reads an AR aging CSV (account, payer type, balance,
   invoice/due dates, claim status).
2. **Classify** — computes days overdue and maps each account to an
   escalation tier using specific rules depending on type of payer. 
3. **Prioritize** — scores each account by dollars at stake, weighted up as
   the claim ages (idea: econ discounting) 
4. **Draft** — auto-generates the tier-appropriate email from a template,
   personalized with the account's details.
5. **Output** — writes a summary report.

## Tools used
- I asked Claude to generate some fake data to work with
- I used python and pandas for data cleaning
- Plain string templates for email drafting 
- Output to CSV and text files 
