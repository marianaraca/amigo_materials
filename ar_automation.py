"""
AR Automation Prototype
------------------------
A rules-based system that automates the core loop of a generic Accounts
Receivable (AR) process for a healthcare provider:

    1. Ingest an AR aging file (patient balances + insurance claims)
    2. Classify each account into an aging bucket and escalation tier
    3. Score & rank accounts by collection priority (expected $ recoverable
       per unit of effort, adjusted for how stale the claim is)
    4. Auto-draft the appropriate outreach (patient reminder, payer
       follow-up, appeal request, or collections referral)
    5. Output a summary report + a prioritized worklist + individual
       email drafts, so a human just has to review and hit send

Design choice: patient balances and insurance claims are escalated on
DIFFERENT tracks, because they behave differently in the real world —
insurance claims need payer follow-up / appeals, while patient balances
need reminders and payment plan offers. Treating them identically is a
common (and costly) mistake in naive AR automation.

Author: Marianne Ramirez Cabal
"""

import pandas as pd
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

AS_OF_DATE = datetime(2026, 7, 1)  # "today" for aging calculations
INPUT_FILE = "sample_ar_data.csv"
OUTPUT_DIR = Path("output")
EMAIL_DIR = OUTPUT_DIR / "generated_emails"

# ---------------------------------------------------------------------------
# Escalation rules
# ---------------------------------------------------------------------------
# Each rule set maps a range of days-overdue to a (tier_label, email_template_key)
# Patient and Insurance accounts use different rule sets on purpose.

PATIENT_RULES = [
    (float("-inf"), 30, "Friendly Reminder", "patient_reminder"),
    (31, 60, "Firm Reminder + Payment Plan", "patient_firm"),
    (61, 90, "Pre-Collections Notice", "patient_precollections"),
    (91, float("inf"), "Refer to Collections", "patient_collections"),
]

INSURANCE_RULES = [
    (float("-inf"), 30, "Within Normal Processing", "insurance_none"),
    (31, 45, "Claim Status Check", "insurance_status_check"),
    (46, 60, "Escalate / Request EOB", "insurance_escalate"),
    (61, float("inf"), "Formal Appeal / Payer Escalation", "insurance_appeal"),
]

EMAIL_TEMPLATES = {
    "patient_reminder": (
        "Subject: Friendly Reminder — Balance Due on Your Account\n\n"
        "Hi {name},\n\n"
        "This is a quick reminder that you have an outstanding balance of "
        "${balance:,.2f} from your recent visit (invoice date {invoice_date}). "
        "You can pay online, by phone, or set up a payment plan if that's "
        "easier.\n\n"
        "If you've already paid, please disregard this message.\n\n"
        "Thank you,\nBilling Team"
    ),
    "patient_firm": (
        "Subject: Action Needed — Balance Past Due\n\n"
        "Hi {name},\n\n"
        "Your balance of ${balance:,.2f} is now {days_overdue} days past due. "
        "We'd like to help you resolve this — we offer flexible payment "
        "plans starting as low as $25/month. Please reach out this week so "
        "we can set that up or answer any questions about your bill.\n\n"
        "Thank you,\nBilling Team"
    ),
    "patient_precollections": (
        "Subject: Important — Your Account Requires Immediate Attention\n\n"
        "Hi {name},\n\n"
        "Your balance of ${balance:,.2f} is significantly past due "
        "({days_overdue} days). To avoid referral to a collections agency, "
        "please contact us within 10 business days to make a payment or "
        "set up a payment plan.\n\n"
        "We're happy to work with you — please don't hesitate to call.\n\n"
        "Billing Team"
    ),
    "patient_collections": (
        "Subject: Final Notice Before Collections Referral\n\n"
        "Hi {name},\n\n"
        "Despite previous notices, your balance of ${balance:,.2f} remains "
        "unpaid after {days_overdue} days. If payment or a payment plan "
        "isn't arranged within 5 business days, this account will be "
        "referred to a third-party collections agency.\n\n"
        "Billing Team"
    ),
    "insurance_none": None,  # not actionable yet, no email generated
    "insurance_status_check": (
        "Subject: Claim Status Inquiry — Account {account_id}\n\n"
        "Hello {payer_name} Claims Team,\n\n"
        "We're following up on claim for account {account_id} "
        "(billed amount ${balance:,.2f}, submitted {invoice_date}). "
        "Current status on file is '{claim_status}'. Could you confirm "
        "expected processing timeline or flag any missing information "
        "needed from our end?\n\n"
        "Thank you,\nRevenue Cycle Team"
    ),
    "insurance_escalate": (
        "Subject: EOB Request — Claim Overdue {days_overdue} Days\n\n"
        "Hello {payer_name} Claims Team,\n\n"
        "The claim for account {account_id} (${balance:,.2f}, submitted "
        "{invoice_date}) is now {days_overdue} days outstanding with status "
        "'{claim_status}'. Please send the Explanation of Benefits (EOB) or "
        "confirm reason for delay so we can resolve this promptly.\n\n"
        "Revenue Cycle Team"
    ),
    "insurance_appeal": (
        "Subject: Formal Appeal — Claim {account_id}\n\n"
        "Hello {payer_name} Appeals Department,\n\n"
        "We are formally appealing the handling of claim {account_id} "
        "(${balance:,.2f}), submitted {invoice_date} and currently "
        "{days_overdue} days outstanding with status '{claim_status}'. "
        "Please treat this as a priority escalation and respond with next "
        "steps within 10 business days.\n\n"
        "Revenue Cycle Team"
    ),
}


def classify(days_overdue: int, rules: list) -> tuple[str, str]:
    """Map days_overdue to (tier_label, template_key) using the given rule set."""
    for low, high, tier, template_key in rules:
        if low <= days_overdue <= high:
            return tier, template_key
    return "Uncategorized", None


def priority_score(balance: float, days_overdue: int) -> float:
    """
    Simple prioritization heuristic: dollars at stake, weighted up as an
    account gets older (because the probability of ever collecting decays
    over time — a $1 today is worth more in expectation than a $1 you
    might collect after 6 months of chasing).
    """
    urgency_weight = 1 + (max(days_overdue, 0) / 30)
    return round(balance * urgency_weight, 2)


def draft_email(row: pd.Series) -> str | None:
    template_key = row["template_key"]
    if template_key is None or EMAIL_TEMPLATES.get(template_key) is None:
        return None
    template = EMAIL_TEMPLATES[template_key]
    return template.format(
        name=row["patient_name"],
        balance=row["balance"],
        invoice_date=row["invoice_date"].strftime("%Y-%m-%d"),
        days_overdue=row["days_overdue"],
        account_id=row["account_id"],
        payer_name=row["payer_name"],
        claim_status=row["claim_status"],
    )


def run():
    OUTPUT_DIR.mkdir(exist_ok=True)
    EMAIL_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(INPUT_FILE, parse_dates=["invoice_date", "due_date"])
    df["days_overdue"] = (AS_OF_DATE - df["due_date"]).dt.days

    tiers, template_keys = [], []
    for _, row in df.iterrows():
        rules = PATIENT_RULES if row["payer_type"] == "Patient" else INSURANCE_RULES
        tier, template_key = classify(row["days_overdue"], rules)
        tiers.append(tier)
        template_keys.append(template_key)

    df["tier"] = tiers
    df["template_key"] = template_keys
    df["priority_score"] = df.apply(
        lambda r: priority_score(r["balance"], r["days_overdue"]), axis=1
    )
    df["drafted_email"] = df.apply(draft_email, axis=1)

    # --- Worklist: sorted by priority, highest first ---
    worklist = df.sort_values("priority_score", ascending=False)[
        ["account_id", "patient_name", "payer_type", "payer_name", "balance",
         "days_overdue", "tier", "priority_score"]
    ]
    worklist.to_csv(OUTPUT_DIR / "priority_worklist.csv", index=False)

    # --- Summary: totals by payer_type + tier ---
    summary = (
        df.groupby(["payer_type", "tier"])
        .agg(accounts=("account_id", "count"), total_balance=("balance", "sum"))
        .reset_index()
        .sort_values(["payer_type", "total_balance"], ascending=[True, False])
    )
    summary.to_csv(OUTPUT_DIR / "ar_summary_report.csv", index=False)

    # --- Emails: one .txt file per actionable account ---
    emails_generated = 0
    for _, row in df.iterrows():
        if isinstance(row["drafted_email"], str):
            safe_tier = row["tier"].replace(" / ", "_").replace(" ", "_").replace("/", "_")
            filename = EMAIL_DIR / f"{row['account_id']}_{safe_tier}.txt"
            filename.write_text(row["drafted_email"])
            emails_generated += 1

    # --- Console summary ---
    print("=" * 70)
    print(f"AR AUTOMATION RUN — as of {AS_OF_DATE.date()}")
    print("=" * 70)
    print(f"Accounts processed:   {len(df)}")
    print(f"Total AR balance:     ${df['balance'].sum():,.2f}")
    print(f"Emails auto-drafted:  {emails_generated}")
    print()
    print("Balance by tier:")
    print(summary.to_string(index=False))
    print()
    print("Top 5 priority accounts:")
    print(worklist.head(5).to_string(index=False))
    print()
    print(f"Full outputs written to: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    run()
