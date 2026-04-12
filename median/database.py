import sqlite3
from contextlib import contextmanager
from datetime import datetime
from sqlite3 import Error
from typing import Any

from median.utils import median_logger

DB_NAME = "flashcards.db"
FLASHCARD_TABLE_SQL = """CREATE TABLE IF NOT EXISTS flashcards
                         (id INTEGER PRIMARY KEY,
                          question TEXT,
                          answer TEXT,
                          model TEXT,
                          lastTest TEXT,
                          total INTEGER,
                          flashcardName TEXT)"""


def ensure_flashcards_table(conn: sqlite3.Connection) -> None:
    """Ensures the flashcards table exists before any read or write operation."""

    conn.execute(FLASHCARD_TABLE_SQL)
    conn.commit()


def normalize_flashcard_row(row: sqlite3.Row) -> dict[str, Any]:
    """Converts SQLite rows into a consistent dictionary shape for the app."""

    return {
        "id": row["id"],
        "question": row["question"],
        "answer": row["answer"],
        "model": row["model"],
        "last_test": row["lastTest"],
        "total": row["total"] or 0,
        "flashcard_name": row["flashcardName"],
    }


@contextmanager
def get_db_connection():
    """
    Context manager to establish a connection to the database.

    Yields:
        Connection: A connection to the database.

    Raises:
        Error: If there is a database error.
    """

    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        ensure_flashcards_table(conn)
        median_logger.info(f"Connected to {DB_NAME}")
        yield conn
    except Error as e:
        median_logger.error(f"Database error: {e}")
        raise
    finally:
        if conn:
            conn.close()
            median_logger.info(f"Connection to {DB_NAME} closed")


def create_table():
    """
    Creates a table in the database.

    Returns:
        None
    """

    with get_db_connection() as conn:
        try:
            ensure_flashcards_table(conn)
            median_logger.info("Table flashcards created")
        except Error as e:
            median_logger.error(f"Failed to create table: {e}")
            raise


def insert_flashcard_data(
    question: str,
    answer: str,
    model: str,
    last_test: datetime,
    total: int,
    flashcard_name: str,
):
    """
    Inserts flashcard data into the 'flashcards' table in the database.

    Args:
        question (str): The question for the flashcard.
        answer (str): The answer for the flashcard.
        model (str): The model associated with the flashcard.
        last_test (datetime): The date of the last test for the flashcard.
        total (int): The total number of tests taken for the flashcard.
        flashcard_name (str): The name of the flashcard.

    Returns:
        None

    Raises:
        Error: If there is an error inserting the flashcard data.
    """

    with get_db_connection() as conn:
        c = conn.cursor()
        try:
            c.execute(
                "INSERT INTO flashcards(question, answer, model, lastTest, total, flashcardName) VALUES (?,?,?,?,?,?)",
                (question, answer, model, last_test, total, flashcard_name),
            )
            conn.commit()
            median_logger.info("Flashcard data inserted")
        except Error as e:
            median_logger.error(f"Failed to insert flashcard data: {e}")
            raise


def select_flashcard_by_name(flashcard_name: str) -> list[dict[str, Any]]:
    """
    Selects flashcard data from the 'flashcards' table in the database based on the flashcard name.

    Args:
        flashcard_name (str): The name of the flashcard to select.

    Returns:
        list[dict[str, Any]]: A list of dictionaries containing the selected flashcard data.
    """

    with get_db_connection() as conn:
        c = conn.cursor()
        try:
            c.execute(
                """
                SELECT id, question, answer, model, lastTest, total, flashcardName
                FROM flashcards
                WHERE flashcardName = ?
                ORDER BY id
                """,
                (flashcard_name,),
            )
            median_logger.info(f"Selected flashcard by name: {flashcard_name}")
            return [normalize_flashcard_row(row) for row in c.fetchall()]
        except Error as e:
            median_logger.error(f"Failed to select flashcard by name: {e}")
            return []


def select_all_unique_flashcard_names(search_query: str = "") -> list[str]:
    """
    Selects all unique flashcard names from the 'flashcards' table in the database.

    Returns:
        list[str]: A list of unique flashcard names.
    """

    with get_db_connection() as conn:
        c = conn.cursor()
        try:
            wildcard_query = f"%{search_query.strip()}%"
            c.execute(
                """
                SELECT DISTINCT flashcardName
                FROM flashcards
                WHERE flashcardName LIKE ?
                ORDER BY flashcardName COLLATE NOCASE
                """,
                (wildcard_query,),
            )
            median_logger.info("Selected all unique flashcard names")
            return [i[0] for i in c.fetchall()]
        except Error as e:
            median_logger.error(f"Failed to select all unique flashcard names: {e}")
            return []


def select_flashcard_deck_summaries(
    search_query: str = "",
) -> list[dict[str, Any]]:
    """Returns aggregate deck information used by the dashboard."""

    with get_db_connection() as conn:
        c = conn.cursor()
        try:
            wildcard_query = f"%{search_query.strip()}%"
            c.execute(
                """
                SELECT
                    flashcardName,
                    COUNT(*) AS totalCards,
                    SUM(CASE WHEN total = 0 THEN 1 ELSE 0 END) AS newCards,
                    MAX(lastTest) AS lastReview
                FROM flashcards
                WHERE flashcardName LIKE ?
                GROUP BY flashcardName
                ORDER BY flashcardName COLLATE NOCASE
                """,
                (wildcard_query,),
            )
            rows = c.fetchall()
            return [
                {
                    "flashcard_name": row["flashcardName"],
                    "total_cards": row["totalCards"],
                    "new_cards": row["newCards"] or 0,
                    "last_review": row["lastReview"],
                }
                for row in rows
            ]
        except Error as e:
            median_logger.error(f"Failed to select flashcard deck summaries: {e}")
            return []


def update_flashcard_data(
    id_: int,
    question: str,
    answer: str,
    model: str,
    last_test: datetime,
    total: int,
    flashcard_name: str,
):
    """
    Updates the data of a flashcard in the 'flashcards' table in the database.

    Args:
        id_ (int): The ID of the flashcard to update.
        question (str): The updated question for the flashcard.
        answer (str): The updated answer for the flashcard.
        model (str): The updated model associated with the flashcard.
        last_test (datetime): The updated date of the last test for the flashcard.
        total (int): The updated total number of tests taken for the flashcard.
        flashcard_name (str): The updated name of the flashcard.
    """

    with get_db_connection() as conn:
        c = conn.cursor()
        try:
            c.execute(
                "UPDATE flashcards SET question = ?, answer = ?, model = ?, lastTest = ?, total = ?, flashcardName = ? WHERE id = ?",
                (question, answer, model, last_test, total, flashcard_name, id_),
            )
            conn.commit()
            median_logger.info("Flashcard data updated")
        except Error as e:
            median_logger.error(f"Failed to update flashcard data: {e}")
            raise
