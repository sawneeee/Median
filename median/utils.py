import datetime
import logging
import os
os.environ["THINC_BACKEND"] = "numpy"
from logging.handlers import RotatingFileHandler
from typing import List, Optional

try:
    import spacy
except Exception:
    spacy = None


from langdetect import detect
#from pke.unsupervised import TopicRank
from spacy.language import Language


# Constants
EMBEDDING_MODEL_NAME = "thenlper/gte-small"
MARKDOWN_SEPARATORS = [
    "\n#{1,6} ",
    "```\n",
    "\n\\*\\*\\*+\n",
    "\n---+\n",
    "\n___+\n",
    "\n\n",
    "\n",
    " ",
    "",
]
SPACY_MODELS = {}


# Logging setup
def setup_logging():
    """
    Sets up logging configuration for the application.

    Returns:
        Logger: The configured logger object.
    """

    logging.basicConfig(
        format="%(asctime)s,%(msecs)03d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d:%H:%M:%S",
        level=logging.INFO,
    )
    script_dir = os.path.dirname(os.path.abspath(__file__))
    now = datetime.datetime.now()
    log_folder = os.path.join(script_dir, "median_logs")
    os.makedirs(log_folder, exist_ok=True)
    log_file_path = os.path.join(
        log_folder,
        f"median_{now.strftime('%Y-%m-%d_%H-%M-%S')}.log",
    )
    file_handler = RotatingFileHandler(
        log_file_path, maxBytes=5 * 1024 * 1024, backupCount=5
    )
    file_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s,%(msecs)03d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d:%H:%M:%S",
    )
    file_handler.setFormatter(formatter)

    logger = logging.getLogger("median")
    logger.addHandler(file_handler)
    return logger


median_logger = setup_logging()


# Utility Functions
def load_spacy_model(spacy_model: str) -> Language:
    """
    Loads a SpaCy language model and caches it for future use.

    Args:
        spacy_model (str): The name of the SpaCy model to load.

    Returns:
        Language: The loaded SpaCy language model.
    """

    if spacy_model not in SPACY_MODELS:
        try:
            SPACY_MODELS[spacy_model] = spacy.load(spacy_model)
            median_logger.info(f"Loaded SpaCy model: {spacy_model}")
        except Exception as e:
            median_logger.error(
                f"Error loading SpaCy model: {e}. Attempting to download."
            )
            spacy.cli.download(spacy_model)
            SPACY_MODELS[spacy_model] = spacy.load(spacy_model)
    return SPACY_MODELS[spacy_model]


def language_detection(content: str) -> str:
    """
    Detects the language of the provided content.

    Args:
        content (str): The content for language detection.

    Returns:
        str: The detected language.
    """

    return detect(content)


def get_topics(content: str, language: str, spacy_model: Optional[str] = "en_core_web_sm") -> List[str]:
    nlp = load_spacy_model(spacy_model)
    doc = nlp(content)

    topics = set()

    for chunk in doc.noun_chunks:
        text = chunk.text.strip()
        if len(text.split()) <= 4:
            topics.add(text.lower())

    if not topics:
        topics = set(content.split()[:10])

    return list(topics)[:5]
    
def split_documents(chunk_size, knowledge_base):
    chunks = []

    for doc in knowledge_base:
        text = doc if isinstance(doc, str) else str(doc)

        words = text.split()

        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i + chunk_size])
            chunks.append(chunk)

    return chunks