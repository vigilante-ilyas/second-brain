from datetime import datetime, timedelta
import re


DATE_FORMATS = [
    "%d %b %Y",
    "%d %B %Y",
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%B %d, %Y",
    "%b %d, %Y"
]


def parse_absolute_date(text):
    if not text:
        return None

    text = str(text).strip()

    if text.lower() in {
        "unknown", "none", "null", "n/a", ""
    }:
        return None

    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(
                text, date_format
            ).date()
        except ValueError:
            continue

    return None


def parse_recorded_date(text):
    return parse_absolute_date(text)


def interpret_date(event_date, recorded_date=None):
    if not event_date:
        return None

    expression = str(event_date).strip().lower()

    # First recognize absolute dates.
    # These do not require a recording date.
    absolute_date = parse_absolute_date(event_date)

    if absolute_date is not None:
        return absolute_date.isoformat()

    # Relative dates require a reliable recording date.
    base_date = parse_recorded_date(recorded_date)

    if base_date is None:
        return None

    if expression == "today":
        return base_date.isoformat()

    if expression == "tomorrow":
        return (
            base_date + timedelta(days=1)
        ).isoformat()

    if expression == "yesterday":
        return (
            base_date - timedelta(days=1)
        ).isoformat()

    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6
    }

    match = re.fullmatch(
        r"next (monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        expression
    )

    if match:
        target_weekday = weekdays[match.group(1)]

        # "Next Friday" is interpreted as Friday
        # in the following calendar week.
        days_ahead = (
            7 - base_date.weekday()
            + target_weekday
        )

        return (
            base_date + timedelta(days=days_ahead)
        ).isoformat()

    # Never guess unsupported dates.
    return None


if __name__ == "__main__":

    tests = [
        ("tomorrow", "7 Oct 2026"),
        ("yesterday", "7 Oct 2026"),
        ("next Friday", "7 Oct 2026"),
        ("5 October 2026", "Unknown"),
        ("6 October 2026", None),
        ("20 September 2026", "Unknown"),
        ("next Friday", "Unknown"),
        ("next summer", "15 September 2026")
    ]

    print("\nDATE INTERPRETER TEST")
    print("=" * 40)

    for event_date, recorded_date in tests:
        result = interpret_date(
            event_date,
            recorded_date
        )

        print(
            f"{event_date} -> "
            f"{result or 'Not resolved'}"
        )