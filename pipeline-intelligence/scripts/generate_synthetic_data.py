"""
Synthetic data generator for Pipeline Intelligence System .
Builds 4 datasets with consistent deal_ids across all files.

Slip signals intentionally seeded in ~5 deals:
  - activity gaps > 14 days on open deals
  - champion contact_role goes blank mid-cycle
  - transcript tone shifts negative on last call

Run: python scripts/generate_synthetic_data.py
"""

import json
import csv
import random
from pathlib import Path
from datetime import datetime, timedelta

import yaml
from faker import Faker

ROOT = Path(__file__).resolve().parent.parent
config = yaml.safe_load((ROOT / "company_config.yaml").read_text())

SEED = config["data_faker"]["seed"]
NUM_DEALS = config["data_faker"]["num_deals"]
STAGES = config["pipeline_stages"]
ACTIVITY_TYPES = config["activity_types"]
CONTACT_ROLES = [r for r in config["contact_roles"] if r]  # non-blank roles only
GAP_DAYS = config["scoring"]["activity_gap_days"]

fake = Faker()
Faker.seed(SEED)
random.seed(SEED)

SYNTHETIC_DIR = ROOT / "data" / "synthetic"
SAMPLE_DIR = ROOT / "data" / "sample"
SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

TODAY = datetime.today()

# slip deal_ids picked upfront — logic references deal_id, not loop index
ALL_DEAL_IDS = [f"DEAL-{1000 + i}" for i in range(NUM_DEALS)]
SLIP_DEAL_IDS = set(random.sample(ALL_DEAL_IDS, 5))

# rep turns: asking questions, moving things forward — mostly neutral
REP_TURNS = [
    "Thanks for the time today — wanted to follow up on the security questionnaire, did you get a chance to look at it?",
    "Happy to loop in our solutions engineer if that would help unblock the technical review.",
    "Just checking in — any update from your side on the internal review?",
    "We can be flexible on the implementation timeline if that helps. What's the blocker right now?",
    "I heard back from our legal team — they're fine with the liability cap language you proposed.",
    "Can we get 30 minutes on the calendar with your IT lead? I think one call would close the loop.",
    "I want to make sure we're set up for success here — what would make this an easy yes for your team?",
]

# buyer turns: these carry the sentiment signal
POSITIVE_BUYER_TURNS = [
    "Yeah so we showed the demo to the broader team last Thursday and honestly the reaction was pretty positive.",
    "I think we're close — finance signed off on the budget range, just need legal to do their thing.",
    "Our VP pulled me aside after the call and said you guys came out on top in the eval.",
    "We're moving fast on our end. Can we target a contract signature before end of month?",
    "The ROI model you sent over — our CFO actually liked it, which is rare, so that's a good sign.",
]

NEUTRAL_BUYER_TURNS = [
    "Uh, we're still in the evaluation phase — a couple other vendors we're still looking at.",
    "Can you resend the security questionnaire? I think it got buried in my inbox.",
    "We need legal to review the MSA before anything moves forward, that's just our process.",
    "Timeline is honestly a bit up in the air right now — there's some internal stuff going on.",
    "Let me check with my team and get back to you — maybe early next week?",
    "Yeah I saw your follow-up — I'll loop in our IT lead and get you an answer this week.",
]

DECLINING_BUYER_TURNS = [
    "Honestly, we're not seeing the differentiation we need — the other vendors are hitting most of the same checkboxes.",
    "Budget situation has changed. There's a freeze in place and I don't know when that lifts.",
    "So — and I probably should have told you sooner — our main champion just left the company last week.",
    "Leadership wants us to pause all new vendor decisions until Q3. It's not specific to you, it's across the board.",
    "The evaluation committee met and there are some concerns around the integration lift. It's more than we thought.",
    "I'm going to be straight with you — internally the priority has shifted and this isn't top of the list right now.",
]

# real sales email templates
EMAIL_TEMPLATES = [
    (
        "Re: Next steps after the demo",
        "Hey {name}, thanks again for the time on Thursday — the team had good things to say. "
        "Wanted to follow up on the integration question {contact} raised. "
        "Happy to set up a 30-min technical call with our solutions engineer if that helps move things forward. "
        "What does next week look like?"
    ),
    (
        "Checking in — any update on your end?",
        "Hi {name}, just wanted to touch base since we spoke a couple weeks ago. "
        "I know you mentioned the internal review was wrapping up around now. "
        "No pressure — just wanted to see if there's anything I can help unblock on our side. Let me know."
    ),
    (
        "Security questionnaire — updated version",
        "Hey {name}, our security team finished the updated questionnaire you requested. "
        "I've attached it here. Most of the SOC 2 questions are in section 3 — "
        "let me know if your IT team needs anything else or wants to jump on a call."
    ),
    (
        "Contract redlines — v2",
        "Hi {name}, our legal team turned around the redlines faster than expected. "
        "Main changes are in sections 4.2 (liability cap) and 7.1 (data retention). "
        "Both are pretty standard for us. Happy to get on a call if it's easier to talk through."
    ),
    (
        "Intro: our VP wants to connect",
        "Hey {name}, I mentioned our conversation to our VP and she'd love to jump on a quick call — "
        "15-20 mins, just to hear more about where you're headed strategically. "
        "No pitch, she's just genuinely interested. Would that be useful?"
    ),
    (
        "Quick question on implementation timeline",
        "Hi {name}, as we get closer to contract I want to make sure we're aligned on timeline. "
        "Our implementation team typically needs 3-4 weeks to get you fully stood up. "
        "If you're targeting a go-live before end of quarter we should probably kick that off soon."
    ),
    (
        "Following up from last week",
        "Hey {name}, circling back on our conversation. I know things have been busy on your end. "
        "I still think the timing makes sense for Q3 given what you shared about your roadmap. "
        "Even a quick 15 min call to check in would be helpful. Does Thursday work?"
    ),
]


def random_close_date() -> str:
    # Q2-Q4 current year
    start = datetime(TODAY.year, 4, 1)
    end = datetime(TODAY.year, 12, 31)
    return (start + timedelta(days=random.randint(0, (end - start).days))).strftime("%Y-%m-%d")


def random_arr() -> int:
    return random.choice([25000, 50000, 75000, 100000, 150000, 200000, 250000])


def build_opportunities() -> list[dict]:
    rows = []
    for deal_id in ALL_DEAL_IDS:
        stage = random.choice(["Proposal", "Negotiation"]) if deal_id in SLIP_DEAL_IDS else random.choice(STAGES[:-2])
        rows.append({
            "deal_id": deal_id,
            "stage": stage,
            "close_date": random_close_date(),
            "arr": random_arr(),
            "rep_name": fake.name(),
            "account_name": fake.company(),
        })
    return rows


def build_transcripts() -> list[dict]:
    records = []
    for deal_id in ALL_DEAL_IDS:
        num_calls = random.randint(2, 4)
        for call_num in range(num_calls):
            call_date = (TODAY - timedelta(days=random.randint(5, 60))).strftime("%Y-%m-%d")
            rep_name = fake.first_name()
            buyer_name = fake.first_name()
            num_turns = random.randint(4, 7)
            is_last_call = call_num == num_calls - 1

            for turn_num in range(num_turns):
                is_rep = turn_num % 2 == 0
                speaker = f"{rep_name} (Rep)" if is_rep else f"{buyer_name} (Buyer)"

                if is_rep:
                    turn_text = random.choice(REP_TURNS)
                elif deal_id in SLIP_DEAL_IDS and is_last_call:
                    turn_text = random.choice(DECLINING_BUYER_TURNS)
                elif deal_id in SLIP_DEAL_IDS:
                    turn_text = random.choice(NEUTRAL_BUYER_TURNS + DECLINING_BUYER_TURNS)
                else:
                    turn_text = random.choice(POSITIVE_BUYER_TURNS + NEUTRAL_BUYER_TURNS)

                records.append({
                    "deal_id": deal_id,
                    "call_date": call_date,
                    "call_num": call_num + 1,
                    "turn_num": turn_num + 1,
                    "speaker": speaker,
                    "turn_text": turn_text,
                })
    return records


def build_email_threads() -> list[dict]:
    rows = []
    for deal_id in ALL_DEAL_IDS:
        num_emails = random.randint(3, 6)
        base_date = TODAY - timedelta(days=random.randint(3, 30))

        for i in range(num_emails):
            gap = random.randint(GAP_DAYS + 2, 28) if (deal_id in SLIP_DEAL_IDS and i > 0) else random.randint(1, 6)
            email_date = base_date - timedelta(days=gap * i)
            rep_email = fake.email()
            buyer_email = fake.company_email()

            subject, body_tpl = random.choice(EMAIL_TEMPLATES)
            body = body_tpl.format(name=fake.first_name(), contact=fake.first_name())

            rows.append({
                "deal_id": deal_id,
                "from": rep_email if i % 2 == 0 else buyer_email,
                "to": buyer_email if i % 2 == 0 else rep_email,
                "subject": subject,
                "body": body,
                "timestamp": email_date.strftime("%Y-%m-%d %H:%M:%S"),
            })
    return rows


def build_activity_log() -> list[dict]:
    rows = []
    for deal_id in ALL_DEAL_IDS:
        num_activities = random.randint(3, 6)
        base_date = TODAY - timedelta(days=random.randint(2, 20))

        for i in range(num_activities):
            if deal_id in SLIP_DEAL_IDS and i == 0:
                act_date = TODAY - timedelta(days=random.randint(GAP_DAYS + 2, 40))
                contact_role = ""  # champion departure signal
            else:
                act_date = base_date - timedelta(days=i * random.randint(2, 7))
                contact_role = random.choice(CONTACT_ROLES)

            rows.append({
                "deal_id": deal_id,
                "activity_type": random.choice(ACTIVITY_TYPES),
                "activity_date": act_date.strftime("%Y-%m-%d"),
                "contact_role": contact_role,
            })
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def write_json(data: list[dict], path: Path) -> None:
    path.write_text(json.dumps(data, indent=2))


def main() -> None:
    print(f"Generating synthetic data — {NUM_DEALS} deals, seed={SEED}")
    print(f"Slip deals: {sorted(SLIP_DEAL_IDS)}")

    opps = build_opportunities()
    transcripts = build_transcripts()
    emails = build_email_threads()
    activities = build_activity_log()

    write_csv(opps, SYNTHETIC_DIR / "sfdc_opportunities.csv")
    write_json(transcripts, SYNTHETIC_DIR / "gong_transcripts.json")
    write_csv(emails, SYNTHETIC_DIR / "email_threads.csv")
    write_csv(activities, SYNTHETIC_DIR / "sfdc_activity_log.csv")

    # 5-row samples committed to git
    write_csv(opps[:5], SAMPLE_DIR / "sfdc_opportunities.csv")
    write_json(transcripts[:10], SAMPLE_DIR / "gong_transcripts.json")
    write_csv(emails[:5], SAMPLE_DIR / "email_threads.csv")
    write_csv(activities[:5], SAMPLE_DIR / "sfdc_activity_log.csv")

    print(f"synthetic/ → {len(opps)} opps | {len(transcripts)} turns | {len(emails)} emails | {len(activities)} activities")
    print("sample/    → 5-row snapshots ready to commit")


if __name__ == "__main__":
    main()
