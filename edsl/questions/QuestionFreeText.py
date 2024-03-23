"""A subclass of the `Question` class for creating free response questions.
Example usage:

.. code-block:: python

    from edsl.questions import QuestionFreeText

    q = QuestionFreeText(
        question_name = "food",
        question_text = "What is your favorite food?"
    )

Required parameters:

    :param question_name: The name of the question.
    :param question_text: The text of the question.

Optional parameters:

    :param instructions: Instructions for the question. If not provided, the default instructions are used. To view them, run `QuestionFreeText.default_instructions`.

To see an example:

    .. code-block:: python
    
        QuestionFreeText.example()

"""
from __future__ import annotations
import textwrap
from typing import Any, Optional
from edsl.questions import Question
from edsl.questions.descriptors import AllowNonresponseDescriptor
from edsl.scenarios import Scenario
from edsl.utilities import random_string


# TODO: should allow answer = {"answer": None} if allow_nonresponse is True
class QuestionFreeText(Question):
    """This question prompts the agent to respond with unstructured text."""

    question_type = "free_text"
    allow_nonresponse: bool = AllowNonresponseDescriptor()
    default_instructions = textwrap.dedent(
        """\
        You are being asked the following question: {{question_text}}
        Return a valid JSON formatted like this: 
        {"answer": "<put free text answer here>"}
        """
    )

    def __init__(
        self,
        question_text: str,
        question_name: str,
        allow_nonresponse: Optional[bool] = None,
        instructions: Optional[str] = None,
    ):
        """Instantiate a new QuestionFreeText."""
        self.question_text = question_text
        self.question_name = question_name
        self.allow_nonresponse = allow_nonresponse or False
        self.instructions = instructions

    ################
    # Answer methods
    ################
    def validate_answer(self, answer: Any) -> dict[str, str]:
        """Validate the answer."""
        self.validate_answer_template_basic(answer)
        self.validate_answer_key_value(answer, "answer", str)
        return answer

    def translate_answer_code_to_answer(self, answer, scenario: Scenario = None):
        """Do nothing, because the answer is already in a human-readable format."""
        return answer

    def simulate_answer(self, human_readable: bool = True) -> dict[str, str]:
        """Simulate a valid answer for debugging purposes."""
        return {"answer": random_string()}

    @classmethod
    def example(cls) -> QuestionFreeText:
        """Return an example instance of a free text question."""
        return cls(
            question_name="how_are_you",
            question_text="How are you?",
            allow_nonresponse=True,
        )

def main():
    """Create an example question and demonstrate its functionality."""
    from edsl.questions.QuestionFreeText import QuestionFreeText

    q = QuestionFreeText.example()
    q.question_text
    q.question_name
    q.instructions
    # validate an answer
    q.validate_answer({"answer": "I like custard"})
    # translate answer code
    q.translate_answer_code_to_answer({"answer"})
    # simulate answer
    q.simulate_answer()
    q.simulate_answer(human_readable=False)
    q.validate_answer(q.simulate_answer(human_readable=False))
    # serialization (inherits from Question)
    q.to_dict()
    assert q.from_dict(q.to_dict()) == q
