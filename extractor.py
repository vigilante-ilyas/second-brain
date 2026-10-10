import json
import re
from datetime import date
import ollama

MODEL_NAME = "qwen3:1.7b"

VALID_CATEGORIES = {
    "Finance",
    "Health",
    "Home",
    "Education",
    "Work",
    "Family",
    "Identity",
    "Travel",
    "Other"
}

VALID_STATUSES = {
    "Pending",
    "Paid",
    "Completed",
    "Planned",
    "Active",
    "Unknown"
}


def detect_expense_payment(text):
    """Recognize only a single, explicit grocery expense in the source text.

    Abstain on loans, future/negative statements, questions and multiple events.
    Never infer a payment from the model's generated summary.
    """
    text = ' '.join(text.split())
    if '?' in text or '؟' in text or re.search(
        r'\b(?:not|never|will|would|should|borrowed|lent|loan|debt|and|but)\b|'
        r'(?:نہیں|ادھار|قرض|دوں|دینا|اور|لیکن)', text, re.IGNORECASE
    ):
        return None
    money = r'(?:Rs\.?\s*[0-9][0-9,]*|PKR\s*[0-9][0-9,]*|[0-9][0-9,]*\s+rupees)'
    name = r"(?P<person>[A-Za-z][A-Za-z .'-]{0,70}?)"
    # Accept known recording/date prefixes, not arbitrary preceding events.
    prefix = r'(?:(?:On|This is a test voice note on)\s+(?:[0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}|[A-Za-z]+\s+[0-9]{1,2},\s*[0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2}),?\s*)?'
    for payment in (rf'I paid {name}\s+{money}', rf'I gave {money}\s+to {name}'):
        match = re.fullmatch(prefix + payment + r'\s+for groceries(?:\s+in [A-Za-z][A-Za-z .\'-]*)?[.!]?', text, re.IGNORECASE)
        if match:
            person = match.group('person').strip()
            if person.lower() not in {'me', 'myself', 'someone', 'him', 'her', 'them', 'you'} and len(person.split()) <= 3:
                return {'person': person, 'status': 'Paid'}
    months = 'جنوری|فروری|مارچ|اپریل|مئی|جون|جولائی|اگست|ستمبر|اکتوبر|نومبر|دسمبر'
    urdu_prefix = rf'(?:(?:آج\s+)?[0-9۰-۹٠-٩]{{1,2}}\s+(?:{months})\s+[0-9۰-۹٠-٩]{{4}}\s+کو\s+)?'
    match = re.fullmatch(
        urdu_prefix + r'میں نے (?P<person>[^،,.!?؟۔]{1,70}?) کو '
        r'(?:(?:[^،,.!?؟۔]+?) میں )?(?:گروسریز|گروسریس|گروسری|راشن|کریانہ) کے لیے '
        r'[0-9۰-۹٠-٩][0-9۰-۹٠-٩,]* روپے (?:دیے|دئے|ادا کیے)[۔.!]?', text
    )
    if match:
        person = match.group('person').strip()
        if (1 <= len(person.split()) <= 3 and
                all(c.isalpha() or c in " '-" for c in person) and
                person not in {'مجھے', 'خود', 'کسی', 'اس', 'ان', 'آپ'}):
            return {'person': person, 'status': 'Paid'}
    return None


def detect_expense_event_date(text):
    """Keep valid explicit dates attached to supported single grocery payments.

    Recording dates, relative-only expressions and ambiguous/multiple events
    do not override the model. Never use this computer's current date.
    """
    if not detect_expense_payment(text):
        return None
    text = ' '.join(text.split())
    english = dict(zip(
        'january february march april may june july august september october november december'.split(),
        range(1, 13)))
    urdu = dict(zip(
        'جنوری فروری مارچ اپریل مئی جون جولائی اگست ستمبر اکتوبر نومبر دسمبر'.split(),
        range(1, 13)))
    match = re.match(r'^(?:آج )?(\d{1,2}) (' + '|'.join(urdu) + r') (\d{4}) کو ', text)
    if match:
        day, month, year = int(match[1]), urdu[match[2]], int(match[3])
    else:
        match = re.match(r'^On (\d{4})-(\d{2})-(\d{2}),? ', text, re.I)
        if match:
            year, month, day = map(int, match.groups())
        else:
            match = re.match(r'^On (\d{1,2}) ([A-Za-z]+) (\d{4}),? ', text, re.I)
            if match:
                day, month, year = int(match[1]), english.get(match[2].lower()), int(match[3])
            else:
                match = re.match(r'^On ([A-Za-z]+) (\d{1,2}), (\d{4}),? ', text, re.I)
                if not match:
                    return None
                month, day, year = english.get(match[1].lower()), int(match[2]), int(match[3])
    if month is None:
        return None
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def detect_relationship_person(text):
    """
    Identify the other person in clear financial relationships.
    Return None when the relationship is unclear.
    """

    text = text.strip()

    patterns = [
        r"^([A-Za-z][A-Za-z .'-]*?)\s+borrowed\b.*\bfrom\s+me\b",
        r"^I\s+borrowed\b.*\bfrom\s+([A-Za-z][A-Za-z .'-]*?)(?:[.,]|$)",
        r"^([A-Za-z][A-Za-z .'-]*?)\s+paid\s+me\b",
        r"^I\s+paid\s+([A-Za-z][A-Za-z .'-]*?)(?:\s+Rs\.?|\s+PKR|\s+\d|[.,]|$)"
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            person = match.group(1).strip()

            if person.lower() not in {
                "i", "me", "my", "myself"
            }:
                return person

    return None


def extract_memory(text, *, chat=None):

    prompt = f"""
You extract structured information for a personal Second Brain.

Return ONLY valid JSON.

Use exactly these fields:
person
what
money_amount
value
category
status
event_date
location

GENERAL RULES:
1. Never invent information.
2. If unknown, use null.
3. Preserve important details.
4. Relationship direction is critical.
5. Do not confuse a purpose with a location.

PERSON:
- Identify the named person the memory is about.
- "Sajid borrowed money from me" -> Sajid.
- "I borrowed money from Sajid" -> Sajid.
- "Sajid paid me" -> Sajid.
- "I paid Sajid" -> Sajid.
- "I gave Rs. 500 to Ahmed for groceries" -> Ahmed, not Me.
- "میں نے احمد کو گروسریز کے لیے 500 روپے دیے" -> احمد, not Me.
- "Mom asked me" -> Mom.
- "Dad paid" -> Dad.
- Do not use "Me" when another person is clearly identified.

WHAT:
- Describe what happened concisely.
- Preserve relationship direction.
- Never remove important phrases such as:
  "from me", "to me", "I borrowed", "I lent",
  "owes me", "I owe", "paid me", "I paid".

Example:
Original:
"Sajid borrowed Rs. 2,500 from me for groceries."

Correct:
person = Sajid
what = "Sajid borrowed Rs. 2,500 from me for groceries"

MONEY:
- money_amount is only for money.
- Remove currency symbols and commas.
- Rs. 8,500 -> 8500.
- Do not put marks, ages or scores in money_amount.

VALUE:
- Use value for an important non-money numeric value.
- Example: 74 marks -> value = 74.
- If multiple values exist, preserve them in what.
- Otherwise use null.

CATEGORY:
Choose exactly one:
Finance
Health
Home
Education
Work
Family
Identity
Travel
Other

Choose based on the main subject.

Examples:
- Home repair -> Home
- Medicine -> Health
- Travel plans -> Travel
- University marks -> Education
- Borrowed money -> Finance

STATUS:
Choose exactly one:
Pending
Paid
Completed
Planned
Active
Unknown

Rules:
- Money borrowed and not yet returned -> Pending.
- Future repayment does not mean Planned.
- Planned means the main event has not happened yet.
- Explicitly paid expense -> Paid.
- Giving money to someone for groceries is a paid expense: Paid, not Completed.
- "میں نے احمد کو گروسریز کے لیے 500 روپے دیے" -> Paid.
- Future, negated, loan or unclear statements must not be treated as paid expenses.
- Future travel intention -> Planned.
- If unclear -> Unknown.

EVENT_DATE:
- When the event happened or is expected.
- Preserve relative dates exactly.
- "next Friday" stays "next Friday".
- "yesterday" stays "yesterday".
- "next summer" stays "next summer".
- For a pending debt, use its stated repayment date.
- If no event date is stated, use null.
- Do not invent dates.
- Do not automatically use the recording date.
- If the event explicitly says "today, 10 October 2026" or "آج 10 اکتوبر 2026 کو",
  preserve the stated calendar date as 2026-10-10, not merely "today".
- When multiple dates describe different events, do not silently choose one.

LOCATION:
- Include only an explicitly stated physical or geographic place.
- Do not confuse the purpose of an activity with a location.
- "for groceries" is a purpose, NOT a location.
- "for laptop repair" is a purpose, NOT a location.
- "at home" is a location.
- "in Peshawar" is a location.
- "visit Turkey" identifies Turkey as a destination.
- If no location is stated, use null.

Memory:
{text}
"""

    response = (chat or ollama.chat)(
        model=MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    raw_output = response["message"]["content"].strip()

    try:
        data = json.loads(raw_output)
    except json.JSONDecodeError:
        return None

    structured = {
        "person": data.get("person"),
        "what": data.get("what"),
        "money_amount": data.get("money_amount"),
        "value": data.get("value"),
        "category": data.get("category"),
        "status": data.get("status"),
        "event_date": data.get("event_date"),
        "location": data.get("location")
    }

    # Correct clearly identifiable relationship participants.
    detected_person = detect_relationship_person(text)

    if detected_person:
        structured["person"] = detected_person

    payment = detect_expense_payment(text)
    if payment:
        structured.update(payment)
        explicit_date = detect_expense_event_date(text)
        if explicit_date:
            structured['event_date'] = explicit_date

    # Normalize missing event dates.
    if isinstance(structured["event_date"], str):
        if structured["event_date"].strip().lower() in {
            "unknown", "none", "null", ""
        }:
            structured["event_date"] = None

    # Normalize missing locations.
    if isinstance(structured["location"], str):
        if structured["location"].strip().lower() in {
            "unknown", "none", "null", ""
        }:
            structured["location"] = None

    # Reject invalid categories.
    if structured["category"] not in VALID_CATEGORIES:
        structured["category"] = "Other"

    # Reject invalid statuses.
    if structured["status"] not in VALID_STATUSES:
        structured["status"] = "Unknown"

    return structured
