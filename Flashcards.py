from datetime import datetime
import streamlit as st
from median.database import (
    select_flashcard_by_name,
    select_flashcard_deck_summaries,
    update_flashcard_data,
)
from median.spaced_repetition import update_model, format_time_delta

st.set_page_config(
    page_title="Flashcard - Median",
    page_icon="M",
    layout="wide",
)


def deck_option_label(deck_summary: dict) -> str:
    """Formats deck names with a quick summary for the picker."""
    return (
        f"{deck_summary['flashcard_name']} "
        f"- {deck_summary['total_cards']} cards "
        f"- {deck_summary['new_cards']} new"
    )


def pick_current_card(deck_name: str, queue: list[dict]) -> dict | None:
    """Keeps the learner on the next best card for the current deck."""
    current_card_key = f"current_card_{deck_name}"
    queue_ids = {card["id"] for card in queue}
    current_card_id = st.session_state.get(current_card_key)
    if current_card_id not in queue_ids:
        due_cards = [card for card in queue if card["due"]]
        next_card = due_cards[0] if due_cards else queue[0]
        st.session_state[current_card_key] = next_card["id"]
        current_card_id = next_card["id"]
    return next((card for card in queue if card["id"] == current_card_id), None)


def submit_review(card: dict, rating: int, deck_name: str) -> None:
    """Persists a review result and advances the queue."""
    current_card_key = f"current_card_{deck_name}"
    show_answer_key = f"show_answer_{deck_name}"
    updated_model = update_model(
        model=card["model_tuple"],
        result=rating,
        total=card["total"] + 1,
        last_test=card["last_test"],
    )
    update_flashcard_data(
        id_=card["id"],
        question=card["question"],
        answer=card["answer"],
        model=updated_model,
        last_test=datetime.now(),
        total=card["total"] + 1,
        flashcard_name=deck_name,
    )
    st.session_state[show_answer_key] = False
    st.session_state[current_card_key] = None
    st.rerun()


st.title("🧠 Median — Your Smart Study Partner")
st.caption(
    "Developed by Sawnee Ghosh"
)

st.info("👋 Welcome back! Review your due cards to keep your memory sharp.")

search_query = st.text_input(
    "Search decks",
    placeholder="Quadratic equations, French Revolution, biology notes...",
)

deck_summaries = select_flashcard_deck_summaries(search_query)

if not deck_summaries:
    st.info("No decks yet. Create one from the 'Add New Flashcard' page.")
    st.stop()

st.subheader("Deck Library")
deck_preview_columns = st.columns(3)
for index, deck_summary in enumerate(deck_summaries[:6]):
    with deck_preview_columns[index % 3]:
        with st.container(border=True):
            st.markdown(f"#### {deck_summary['flashcard_name']}")
            st.caption(
                f"{deck_summary['total_cards']} cards - {deck_summary['new_cards']} new"
            )
            if deck_summary["last_review"]:
                st.caption(f"Last activity: {deck_summary['last_review']}")

deck_names = [summary["flashcard_name"] for summary in deck_summaries]
deck_summary_map = {
    summary["flashcard_name"]: summary for summary in deck_summaries
}

default_deck = st.session_state.get("selected_deck")
if not deck_names:
    st.info("No decks match your search.")
    st.stop()
if default_deck not in deck_names:
    default_deck = deck_names[0]

selected_deck_name = st.selectbox(
    "Choose a deck",
    deck_names,
    index=deck_names.index(default_deck),
    key="selected_deck",
    format_func=lambda deck_name: deck_option_label(deck_summary_map[deck_name]),
)

cards = select_flashcard_by_name(selected_deck_name)

for card in cards:
    card.setdefault("mastery", "new")
    card.setdefault("recall", 0.5)
    card.setdefault("due_at", None)
    card.setdefault("due", True)
    card.setdefault("model_tuple", None)
    card.setdefault("total", 0)
    card.setdefault("last_test", None)

progress = {
    "queue": cards,
    "due_count": len(cards),
    "total_cards": len(cards),
    "average_recall": 0.5,
    "mastery_ratio": 0.0,
    "next_due_at": None,
    "status_counts": {
        "new": len(cards),
        "learning": 0,
        "review": 0,
        "mastered": 0,
        "struggling": 0,
        "due": len(cards),
        "building": 0,
    },
}

queue = progress["queue"]
status_counts = progress["status_counts"]

st.markdown(f"## {selected_deck_name}")

daily_goal = 20
st.progress(
    min(progress["due_count"] / daily_goal, 1.0),
    text=f"{progress['due_count']}/{daily_goal} cards today",
)

metric_columns = st.columns(4)
metric_columns[0].metric("Due now", progress["due_count"])
metric_columns[1].metric("Mastered", status_counts["mastered"])
metric_columns[2].metric(
    "Needs work",
    status_counts["struggling"] + status_counts["due"],
)
metric_columns[3].metric("Average recall", f"{progress['average_recall']:.0%}")

st.progress(
    progress["mastery_ratio"],
    text=f"{progress['mastery_ratio']:.0%} of this deck feels mastered",
)

if progress["next_due_at"]:
    st.caption(f"Next review window: {format_time_delta(progress['next_due_at'])}")

review_tab, progress_tab, cards_tab = st.tabs(
    ["Review now", "Progress", "All cards"]
)

with review_tab:
    if not queue:
        st.info("This deck is empty.")
    else:
        current_card = pick_current_card(selected_deck_name, queue)
        show_answer_key = f"show_answer_{selected_deck_name}"

        if show_answer_key not in st.session_state:
            st.session_state[show_answer_key] = False

        with st.container(border=True):
            st.caption(
                f"{current_card['mastery'].title()} card - "
                f"Recall {current_card['recall']:.0%} - "
                f"{format_time_delta(current_card['due_at'])}"
            )
            st.caption(f"Type: {current_card.get('type', 'concept')}")

            if current_card["recall"] < 0.5:
                st.warning("⚠️ You're struggling with this concept")

            st.markdown("### Question")
            st.write(current_card["question"])

            if not st.session_state[show_answer_key]:
                if st.button(
                    "Reveal Answer",
                    type="primary",
                    use_container_width=True,
                ):
                    st.session_state[show_answer_key] = True
                    st.rerun()

            if st.session_state[show_answer_key]:
                st.divider()
                st.markdown("### Answer")
                st.write(current_card["answer"])

                rating_columns = st.columns(3)
                if rating_columns[0].button("Again", use_container_width=True):
                    submit_review(current_card, 0, selected_deck_name)
                if rating_columns[1].button("Good", use_container_width=True):
                    submit_review(current_card, 1, selected_deck_name)
                if rating_columns[2].button("Easy", use_container_width=True):
                    submit_review(current_card, 2, selected_deck_name)

        upcoming_cards = [card for card in queue if card["id"] != current_card["id"]][:3]
        if upcoming_cards:
            st.markdown("### Up next")
            for card in upcoming_cards:
                with st.container(border=True):
                    st.write(card["question"])
                    st.caption(
                        f"{card['mastery'].title()} - "
                        f"Recall {card['recall']:.0%} - "
                        f"{format_time_delta(card['due_at'])}"
                    )

with progress_tab:
    summary_columns = st.columns(5)
    summary_columns[0].metric("New", status_counts["new"])
    summary_columns[1].metric("Struggling", status_counts["struggling"])
    summary_columns[2].metric("Due", status_counts["due"])
    summary_columns[3].metric("Building", status_counts["building"])
    summary_columns[4].metric("Mastered", status_counts["mastered"])

    st.markdown("### Deck health")
    for label in ["new", "struggling", "due", "building", "mastered"]:
        count = status_counts[label]
        ratio = (count / progress["total_cards"]) if progress["total_cards"] else 0.0
        st.write(f"{label.title()}: {count} cards")
        st.progress(ratio)

    st.markdown("### Review queue")
    for card in queue[:8]:
        with st.container(border=True):
            st.write(card["question"])
            st.caption(
                f"{card['mastery'].title()} - "
                f"Recall {card['recall']:.0%} - "
                f"Next review {format_time_delta(card['due_at'])}"
            )

    st.markdown("### Weak Areas")
    weak_cards = [c for c in queue if c["mastery"] == "struggling"]
    for card in weak_cards[:5]:
        st.write(f"- {card['question'][:60]}...")

with cards_tab:
    card_search_query = st.text_input(
        "Search within this deck",
        placeholder="definition, theorem, Napoleon...",
    ).strip()

    filtered_cards = queue
    if card_search_query:
        filtered_cards = [
            card
            for card in queue
            if card_search_query.casefold() in card["question"].casefold()
            or card_search_query.casefold() in card["answer"].casefold()
        ]

    if not filtered_cards:
        st.info("No cards match that search.")
    else:
        for card in filtered_cards:
            with st.expander(card["question"]):
                st.write(card["answer"])
                st.caption(
                    f"{card['mastery'].title()} - "
                    f"Recall {card['recall']:.0%} - "
                    f"Next review {format_time_delta(card['due_at'])}"
                )
st.markdown("---")
st.caption("Built by Sawnee Ghosh · Median v1.0")