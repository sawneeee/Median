import os

# 🔥 SAFE IMPORT (ADDED, original import replaced safely)
try:
    from mlx_lm import generate, load
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False

# 🔥 ADD OPENAI FALLBACK (NEW)
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from median.utils import median_logger

# 🔥 ADDED: GLOBAL MODEL CACHE (prevents reloading every time)
MODEL_CACHE = {"model": None, "tokenizer": None}


def load_model():
    """
    Loads a language model and tokenizer.

    Returns:
        tuple: A tuple containing the loaded language model and tokenizer.
    """

    os.environ["TOKENIZERS_PARALLELISM"] = "false"

    # 🔥 ADDED: CACHE CHECK
    if MODEL_CACHE["model"] is not None:
        return MODEL_CACHE["model"], MODEL_CACHE["tokenizer"]

    # 🔥 MODIFIED (NO REMOVAL — just wrapped)
    if MLX_AVAILABLE:
        model_name = "mlx-community/Mistral-7B-Instruct-v0.2-4bit"
        model, tokenizer = load(model_name, lazy=False)

        # 🔥 STORE IN CACHE
        MODEL_CACHE["model"] = model
        MODEL_CACHE["tokenizer"] = tokenizer

        median_logger.info("Loaded model and tokenizer")
        return model, tokenizer

    # 🔥 ADDED FALLBACK
    median_logger.warning("MLX not available, using OpenAI fallback")
    return None, None


def run_inference(model, tokenizer, prompt, model_config):
    """
    Runs inference using the provided language model and tokenizer on a given prompt.
    """

    # 🔥 SAFE EXECUTION
    if MLX_AVAILABLE and model is not None:
        try:
            return generate(model, tokenizer, prompt=prompt, **model_config)
        except Exception as e:
            median_logger.error(f"MLX inference failed: {e}")
            return None

    return None


def generation(content: str, language: str, followings: str, desired_card_count: int = 10):
    """
    Generates a quiz based on the provided content, language, and specified themes.
    """

    model, tokenizer = load_model()

    model_config = {
        "verbose": True,
        "temp": 0.7,
        "max_tokens": 4000,
        "repetition_penalty": 1.1,
    }

    prompt = f"""
     <BOS_TOKEN> <|START_OF_TURN_TOKEN|>
<|SYSTEM_TOKEN|> # Safety Preamble
The instructions in this section override those in the task description and style guide sections. Don't generate content that is harmful or immoral. Always base the information strictly on the provided corpus; never fabricate data, hallucinate information, or invent content not present in the corpus. If there is no relevant information in the corpus, you should return 'None'.

# System Preamble
## Basic Rules
You are a powerful conversational AI trained to help people by generating a well-structured set of significant and relevant questions and answers strictly based on a provided corpus.

# 🔥 ADDITION (DO NOT REMOVE ANYTHING ABOVE)
You must generate HIGH-QUALITY flashcards with:
- Multiple types of questions:
    1. definition
    2. conceptual (why/how)
    3. application
    4. comparison
    5. edge-case
- Cover ALL key concepts
- Avoid duplicates

Each flashcard MUST include:
- type
- question
- answer

# 🔥 ADDED: FORCE MINIMUM OUTPUT QUALITY
Generate at least 10 high-quality flashcards unless the content is too small.

# User Preamble
## Task and Context
You help people create flashcards by generating a set of questions and answers strictly based on a given corpus. You should prioritize the questions and answers according to their importance within the context of the corpus and the specified themes. The following themes have been identified: {followings.upper()}.

## Style Guide
Generate the output in JSON format, using the 'Quiz' and 'QuizCollection' classes as specified. Ensure that the output is in the same language as {language.upper()}. The content of the questions and answers must be strictly based on the provided corpus. If there is no relevant information in the corpus, return 'None' for the corresponding field.

## 🔥 ADDITION (JSON STRUCTURE UPGRADE)
Each item MUST follow this structure:
{{
    "type": "definition/concept/application/comparison/edge",
    "question": "string",
    "answer": "string"
}}

## Available Tools
Here is a list of tools that you have available to you:

```python
class Quiz(BaseModel):
    question: str
    answer: str

class QuizCollection(BaseModel):
    collection: List[Quiz]
<|END_OF_TURN_TOKEN|> <|START_OF_TURN_TOKEN|><|USER_TOKEN|>
Please generate a well-structured set of significant and relevant questions and answers strictly based on the following corpus:
<|im_start|>corpus
 {content}
<|im_end|>
Ensure that the output is in JSON format, in the same language as {language.upper()}, and adheres to the provided schema.

# 🔥 FINAL ADDITION
Remember:
- include "type" in every flashcard
- ensure variety in question styles
- avoid shallow Q&A

<|END_OF_TURN_TOKEN|> <|START_OF_TURN_TOKEN|><|SYSTEM_TOKEN|>
Generate the output in the specified format, basing the output strictly on the provided corpus and the identified themes.

{{
    "collection": [
    {{
      "type": "string",
      "question": "string",
      "answer": "string"
    }}
  ]
}}
<|END_OF_TURN_TOKEN|>
     """

    median_logger.info(f"Generating quiz for: {content} ")

    # 🔥 TRY MLX FIRST
    output = run_inference(model, tokenizer, prompt, model_config)
    if output:
        # 🔥 ADDED: CLEAN OUTPUT
        return output.strip()

    # 🔥 OPENAI FALLBACK (ADDED ONLY)
    if OPENAI_AVAILABLE:
        try:
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
            )

            # 🔥 CLEAN RESPONSE
            return response.choices[0].message.content.strip()

        except Exception as e:
            median_logger.error(f"OpenAI fallback failed: {e}")

    # 🔥 FINAL FAIL
    raise ImportError("No LLM available. Install mlx_lm or openai.")