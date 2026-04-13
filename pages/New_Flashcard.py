from datetime import datetime

import streamlit as st

from median.database import insert_flashcard_data, select_all_unique_flashcard_names
from median.file_reader import main as read_file
from median.generate_quizz import quiz

st.set_page_config(
    page_title="Add New Flashcard - Median",
    page_icon="M",
    layout="wide",
)


def initialize_session_state():
    """Initializes the draft deck state used while generating cards."""

    defaults = {
        "flashcard_data": [],
        "topics": [],
        "source_summary": {},
        "draft_deck_name": "",
    }

    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


def reset_draft_state():
    """Clears the in-progress deck once cards are saved."""

    st.session_state["flashcard_data"] = []
    st.session_state["topics"] = []
    st.session_state["source_summary"] = {}
    st.session_state["draft_deck_name"] = ""


def generate_cards(deck_name: str, data, append: bool = False):
    """Reads the uploaded file and generates a teacher-style card set."""

    extension_to_mime = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "md": "text/markdown",
    "txt": "text/plain",
}
    file_type = extension_to_mime.get(data.name.split(".")[-1].lower())
    content = read_file(data, file_type)
    st.write("DEBUG CONTENT:", content)
    st.write("CONTENT TYPE:", type(content))

    if not content:
        st.error("We could not extract readable text from that file.")
        return

    quiz_collection, topics = quiz(content)

    st.write("DEBUG QUIZ OUTPUT:", quiz_collection)
    st.write("QUIZ TYPE:", type(quiz_collection))
    if not quiz_collection:
        st.error("No flashcards could be generated from this file.")
        return

    st.session_state["draft_deck_name"] = deck_name
    st.session_state["topics"] = topics
    st.session_state["source_summary"] = {
        "file_name": data.name,
        "word_count": len(content.split()),
        "card_count": len(quiz_collection),
    }

    if append:
        st.session_state["flashcard_data"].extend(quiz_collection)
    else:
        st.session_state["flashcard_data"] = quiz_collection


initialize_session_state()

st.title("Create New Flashcard Deck")
st.caption(
    "Upload a PDF, DOCX, Markdown, or TXT file and Median will turn it into a spaced-repetition deck."
)

existing_decks = set(select_all_unique_flashcard_names())

with st.form("new_flashcard_form"):
    draft_name = st.session_state["draft_deck_name"]
    flashcard_name = st.text_input("Deck name", value=draft_name)
    data = st.file_uploader(
        "Upload study material",
        type=["pdf", "docx", "md", "txt"],
        help="PDF chapters, lecture notes, revision sheets, and text exports all work.",
    )

    if flashcard_name and flashcard_name in existing_decks:
        st.info("Saving with an existing deck name will add cards to that deck.")

    col1, col2 = st.columns(2)
    with col1:
        generate_clicked = st.form_submit_button(
            "Generate Smart Deck",
            type="primary",
            use_container_width=True,
        )
    with col2:
        regenerate_clicked = st.form_submit_button(
            "Add More Cards",
            use_container_width=True,
        )

    if generate_clicked or regenerate_clicked:
        if not flashcard_name.strip():
            st.error("A deck name is required.")
        elif data is None:
            st.error("Please upload a file first.")
        else:
            generate_cards(
                flashcard_name.strip(),
                data,
                append=regenerate_clicked and bool(st.session_state["flashcard_data"]),
            )


if st.session_state["flashcard_data"]:
    summary = st.session_state["source_summary"]
    metrics = st.columns(4)
    metrics[0].metric("Draft cards", len(st.session_state["flashcard_data"]))
    metrics[1].metric("Topics", len(st.session_state["topics"]))
    metrics[2].metric("Source words", summary.get("word_count", 0))
    metrics[3].metric(
        "Review rounds",
        max(1, len(st.session_state["flashcard_data"]) // 5),
    )

    if st.session_state["topics"]:
        topic_badges = " ".join(f"`{topic}`" for topic in st.session_state["topics"])
        st.markdown(f"**Coverage:** {topic_badges}")

    source_name = summary.get("file_name")
    if source_name:
        st.caption(f"Draft built from `{source_name}`.")

    with st.popover("Add Card", use_container_width=True):
        new_question = st.text_area("Question")
        new_answer = st.text_area("Answer")
        if st.button("Add to Draft", type="primary"):
            if new_question.strip() and new_answer.strip():
                st.session_state["flashcard_data"].insert(
                    0,
                    {
                        "question": new_question.strip(),
                        "answer": new_answer.strip(),
                    },
                )
                st.rerun()
            else:
                st.error("Both question and answer are required.")

    for quiz_index, flashcard_quiz in enumerate(st.session_state["flashcard_data"], start=1):
        st.divider()
        with st.container(border=True):
            st.markdown(f"### Card {quiz_index}")
            st.write(flashcard_quiz["question"])
            st.caption(flashcard_quiz["answer"])
            col1, col2 = st.columns(2)
            with col1:
                with st.popover("Edit Card", use_container_width=True):
                    new_question = st.text_area(
                        "Question",
                        flashcard_quiz["question"],
                        key=f"{quiz_index}_question",
                    )
                    new_answer = st.text_area(
                        "Answer",
                        flashcard_quiz["answer"],
                        key=f"{quiz_index}_answer",
                    )
                    if st.button("Update Card", key=f"{quiz_index}_update"):
                        if new_question.strip() and new_answer.strip():
                            st.session_state["flashcard_data"][quiz_index - 1] = {
                                "question": new_question.strip(),
                                "answer": new_answer.strip(),
                            }
                            st.rerun()
                        else:
                            st.error("Both question and answer are required.")
            with col2:
                if st.button(
                    "Delete Card",
                    use_container_width=True,
                    type="primary",
                    key=f"{quiz_index}_delete",
                ):
                    st.session_state["flashcard_data"].pop(quiz_index - 1)
                    st.rerun()

    st.divider()
    if st.button("Save Deck to Library", use_container_width=True, type="primary"):
        deck_name = st.session_state["draft_deck_name"].strip()
        if not deck_name:
            st.error("A deck name is required before saving.")
        else:
            for flashcard_quiz in st.session_state["flashcard_data"]:
                insert_flashcard_data(
                    question=flashcard_quiz["question"],
                    answer=flashcard_quiz["answer"],
                    model=str((4.0, 4.0, 24.0)),
                    last_test=datetime.now(),
                    total=0,
                    flashcard_name=deck_name,
                )

            saved_count = len(st.session_state["flashcard_data"])
            reset_draft_state()
            st.success(f"Saved {saved_count} cards to `{deck_name}`.")
