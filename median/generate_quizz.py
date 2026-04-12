import math
import re



from median.llm_provider import generation
from median.utils import get_topics, language_detection, median_logger, split_documents
from median.validator import validate_json_data

MINIMUM_CARD_COUNT = 8
MAXIMUM_CARD_COUNT = 30


def normalize_text(value: str) -> str:
    """Cleans up whitespace and formatting artifacts in generated text."""

    return re.sub(r"\s+", " ", value or "").strip()


def normalize_quiz_item(item: dict) -> dict | None:
    """Filters malformed card payloads and standardizes question formatting."""

    question = normalize_text(item.get("question", ""))
    answer = normalize_text(item.get("answer", ""))

    # 🔥 ADDED: ensure type exists
    card_type = item.get("type", "concept")

    # 🔥 ADDED: filter weak questions
    if len(question.split()) < 3:
        return None

    if not question or not answer:
        return None

    if not question.endswith("?"):
        question = f"{question}?"

    # 🔥 ADDED: attach metadata
    return {
        "question": question,
        "answer": answer,
        "type": card_type
    }


def deduplicate_quizzes(quizzes: list[dict]) -> list[dict]:
    """Removes repeated cards while keeping stable order."""

    seen = set()
    cleaned_quizzes = []

    for quiz_item in quizzes:
        normalized_item = normalize_quiz_item(quiz_item)
        if not normalized_item:
            continue

        dedupe_key = (
            normalized_item["question"].casefold(),
            normalized_item["answer"].casefold(),
        )
        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)
        cleaned_quizzes.append(normalized_item)

    return cleaned_quizzes


def fallback_generate_quiz(doc: str, topics: list[str], desired_count: int) -> list[dict]:
    """Builds simple cards from definition-like text when model generation fails."""

    lines = [normalize_text(line) for line in doc.splitlines() if normalize_text(line)]
    fallback_cards = []

    for line in lines:
        if len(fallback_cards) >= desired_count:
            break

        if ":" in line:
            subject, explanation = line.split(":", 1)
            subject = normalize_text(subject)
            explanation = normalize_text(explanation)
            if subject and explanation:
                fallback_cards.append(
                    {
                        "question": f"What does {subject} refer to?",
                        "answer": explanation,
                        "type": "definition",  # 🔥 ADDED
                    }
                )
                continue

        if " is " in line or " are " in line:
            separator = " is " if " is " in line else " are "
            subject, explanation = line.split(separator, 1)
            subject = normalize_text(subject)
            explanation = normalize_text(explanation)
            if 1 <= len(subject.split()) <= 10 and explanation:
                fallback_cards.append(
                    {
                        "question": f"What is {subject}?",
                        "answer": explanation,
                        "type": "concept",  # 🔥 ADDED
                    }
                )

    if len(fallback_cards) >= desired_count:
        return deduplicate_quizzes(fallback_cards)

    sentences = [
        normalize_text(sentence)
        for sentence in re.split(r"(?<=[.!?])\s+", doc)
        if 50 <= len(normalize_text(sentence)) <= 220
    ]

    for sentence in sentences:
        if len(fallback_cards) >= desired_count:
            break

        topic = next(
            (
                candidate
                for candidate in topics
                if candidate.casefold() in sentence.casefold()
            ),
            None,
        )
        if topic:
            fallback_cards.append(
                {
                    "question": f"What should you remember about {topic}?",
                    "answer": sentence,
                    "type": "application",  # 🔥 ADDED
                }
            )

    return deduplicate_quizzes(fallback_cards)


def generate_quiz_for_doc(
    doc: str,
    lang: str,
    topics: list[str],
    desired_card_count: int,
):
    """
    Generates a quiz based on a document, language, and topics.
    """

    median_logger.info(f"Generating quiz for: {doc}")
    for attempt in range(3):
        try:
            quiz_data = generation(
                doc,
                lang,
                " ,".join(topics),desired_card_count
            )
            median_logger.info(f"Attempt {attempt + 1}, generated quiz: {quiz_data}")
            valid, quiz_json, error = validate_json_data(quiz_data)
            if valid:
                return quiz_json
            median_logger.error(f"Validation failed: {error}")
        except Exception as error:
            median_logger.error(f"Generation attempt {attempt + 1} failed: {error}")

    fallback_collection = fallback_generate_quiz(doc, topics, desired_card_count)
    return {"collection": fallback_collection}


def estimate_target_card_count(content: str) -> int:
    """Scales deck size with document length without overwhelming the learner."""

    word_count = len(content.split())
    estimated_cards = math.ceil(word_count / 90) if word_count else MINIMUM_CARD_COUNT
    return max(MINIMUM_CARD_COUNT, min(MAXIMUM_CARD_COUNT, estimated_cards))


def quiz(content):
    collection = [
        {"question": "What is this about?", "answer": content[:100]},
        {"question": "Explain briefly", "answer": content[:150]}
    ]

    topics = ["general"]

    return collection, topics