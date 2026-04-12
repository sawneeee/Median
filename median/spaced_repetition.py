import ast
from datetime import datetime, timedelta
from typing import Any

import ebisu

from median.utils import median_logger

DEFAULT_MODEL = (4.0, 4.0, 24.0)
REVIEW_RECALL_TARGET = 0.82
MASTERED_RECALL_TARGET = 0.93
STRUGGLING_RECALL_TARGET = 0.55


def convert_to_datetime(date_value, date_format="%Y-%m-%d %H:%M:%S.%f"):
    """
    Converts a date string to a datetime object.

    Args:
        date_value (str | datetime): The date value to convert.
        date_format (str): The format of the date string (default is "%Y-%m-%d %H:%M:%S.%f").

    Returns:
        datetime: The datetime object representing the converted date.
    """

    if isinstance(date_value, datetime):
        return date_value
    if not date_value:
        return datetime.now()

    for fmt in (date_format, "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(str(date_value), fmt)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(str(date_value))
    except ValueError:
        median_logger.error(f"Unable to parse datetime value: {date_value}")
        return datetime.now()


def parse_model(model_value) -> tuple[float, float, float]:
    """Parses a stored Ebisu model into a tuple."""

    if isinstance(model_value, tuple):
        return model_value
    if isinstance(model_value, list):
        return tuple(float(item) for item in model_value)
    if not model_value:
        return DEFAULT_MODEL

    try:
        parsed_model = ast.literal_eval(str(model_value))
        if isinstance(parsed_model, (list, tuple)) and len(parsed_model) == 3:
            return tuple(float(item) for item in parsed_model)
    except (ValueError, SyntaxError):
        median_logger.error(f"Unable to parse model value: {model_value}")

    return DEFAULT_MODEL


def hours_since(date_last_test, now: datetime | None = None):
    """
    Calculates the number of hours since a given date.

    Args:
        date_last_test (datetime): The date to calculate the hours since.
        now (datetime | None): The current time to compare against.

    Returns:
        float: The number of hours elapsed since the given date.
    """

    now = now or datetime.now()
    one_hour = timedelta(hours=1)
    return max((now - date_last_test) / one_hour, 0.0)


def predict_recall(model, last_test, now: datetime | None = None) -> float:
    """Predicts how likely a learner is to remember a card right now."""

    model_tuple = parse_model(model)
    elapsed_hours = hours_since(convert_to_datetime(last_test), now=now)

    try:
        return float(ebisu.predictRecall(model_tuple, elapsed_hours, exact=True))
    except Exception as error:
        median_logger.error(f"Unable to predict recall with Ebisu: {error}")
        half_life = max(model_tuple[2], 1.0)
        return max(min(2 ** (-(elapsed_hours / half_life)), 1.0), 0.0)


def estimate_review_hours(model, target_recall: float = REVIEW_RECALL_TARGET) -> float:
    """Estimates when a card should next be reviewed for a target recall level."""

    model_tuple = parse_model(model)
    high = max(model_tuple[2], 1.0)

    while predict_recall(model_tuple, datetime.now() - timedelta(hours=high)) > target_recall:
        high *= 2
        if high > 24 * 365:
            break

    low = 0.0
    for _ in range(24):
        midpoint = (low + high) / 2
        recall = predict_recall(
            model_tuple,
            datetime.now() - timedelta(hours=midpoint),
        )
        if recall > target_recall:
            low = midpoint
        else:
            high = midpoint

    return high


def next_review_at(model, last_test, target_recall: float = REVIEW_RECALL_TARGET):
    """Returns the datetime when the card should next appear for review."""

    last_test_at = convert_to_datetime(last_test)
    return last_test_at + timedelta(
        hours=estimate_review_hours(model, target_recall=target_recall)
    )


def mastery_bucket(recall: float, total_reviews: int) -> str:
    """Maps card performance to simple learner-facing states."""

    if total_reviews == 0:
        return "new"
    if recall < STRUGGLING_RECALL_TARGET:
        return "struggling"
    if recall < REVIEW_RECALL_TARGET:
        return "due"
    if recall < MASTERED_RECALL_TARGET:
        return "building"
    return "mastered"


def build_card_state(card: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """Builds recall, mastery, and scheduling metadata for a flashcard."""

    now = now or datetime.now()
    recall = predict_recall(card["model"], card["last_test"], now=now)
    due_at = next_review_at(card["model"], card["last_test"])
    total_reviews = int(card.get("total", 0) or 0)

    return {
        **card,
        "model_tuple": parse_model(card["model"]),
        "last_test_at": convert_to_datetime(card["last_test"]),
        "recall": recall,
        "due_at": due_at,
        "due": total_reviews == 0 or recall <= REVIEW_RECALL_TARGET,
        "mastery": mastery_bucket(recall, total_reviews),
    }


def review_queue(cards: list[dict[str, Any]], now: datetime | None = None):
    """Orders cards so the student sees the most urgent reviews first."""

    now = now or datetime.now()
    queue = [build_card_state(card, now=now) for card in cards]
    queue.sort(
        key=lambda card: (
            0 if card["due"] else 1,
            card["recall"],
            card["total"],
            card["last_test_at"],
        )
    )
    return queue


def deck_progress(cards: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any]:
    """Computes deck-level progress information for the dashboard."""

    queue = review_queue(cards, now=now)
    total_cards = len(queue)
    status_counts = {
        "new": 0,
        "struggling": 0,
        "due": 0,
        "building": 0,
        "mastered": 0,
    }

    for card in queue:
        status_counts[card["mastery"]] += 1

    total_recall = sum(card["recall"] for card in queue)
    due_cards = [card for card in queue if card["due"]]
    mastered_cards = status_counts["mastered"]
    mastery_ratio = (mastered_cards / total_cards) if total_cards else 0.0

    return {
        "total_cards": total_cards,
        "due_count": len(due_cards),
        "average_recall": (total_recall / total_cards) if total_cards else 0.0,
        "mastery_ratio": mastery_ratio,
        "status_counts": status_counts,
        "next_due_at": due_cards[0]["due_at"] if due_cards else None,
        "queue": queue,
    }


def format_time_delta(target_time: datetime | None, now: datetime | None = None) -> str:
    """Formats time deltas in a compact, readable way for the UI."""

    if target_time is None:
        return "No review scheduled"

    now = now or datetime.now()
    delta = target_time - now
    seconds = int(delta.total_seconds())

    if seconds <= 0:
        return "Due now"

    minutes = seconds // 60
    if minutes < 60:
        return f"In {minutes} min"

    hours = minutes // 60
    if hours < 48:
        return f"In {hours} hr"

    days = hours // 24
    return f"In {days} days"


def recall_prediction(database):
    """
    Predicts recall for each factID based on the database information.

    Args:
        database: The database containing information for each factID.

    Returns:
        list: A list of dictionaries with 'factID' and 'recall' values, sorted by 'recall' in ascending order.
    """

    median_logger.info("Recall prediction for each factID")
    recall_list = [
        {
            "factID": row.get("factID", row.get("id")),
            "recall": predict_recall(
                row["model"],
                row.get("lastTest", row.get("last_test")),
            ),
        }
        for row in database
    ]
    # Sort the recall_list by 'recall' value in ascending order outside the loop
    recall_list.sort(key=lambda x: x["recall"])
    return recall_list


def update_model(model, result, total, last_test):
    """
    Updates a model based on the result, total, and last test information.

    Args:
        model: The current model to update.
        result: The result of the update.
        total: The total number of updates.
        last_test: The date of the last test.

    Returns:
        str: The updated model after the modifications.
    """

    median_logger.info("Update model based on the result")
    model_tuple = parse_model(model)
    elapsed_hours = hours_since(convert_to_datetime(last_test))
    success_score = 0 if result == 0 else 1

    try:
        new_model = ebisu.updateRecall(model_tuple, success_score, 1, elapsed_hours)
    except Exception as error:
        median_logger.error(f"Unable to update model with Ebisu: {error}")
        new_model = model_tuple

    if result == 0:
        new_model = ebisu.rescaleHalflife(new_model, 0.6)
    if result == 2:
        new_model = ebisu.rescaleHalflife(new_model, 1.8)

    return str(tuple(float(value) for value in new_model))
