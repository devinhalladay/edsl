import os
import pytest
import re
from edsl.exceptions import QuestionSerializationError
from edsl.questions.question_registry import get_question_class, CLASS_REGISTRY


def test_get_question_class_with_valid_types():
    # Test with each registered question type
    for question_type in CLASS_REGISTRY.keys():
        # check that module exists
        question_class = get_question_class(question_type)
        assert question_class is not None


def test_get_question_class_with_invalid_type():
    invalid_type = "invalid_type"
    invalid_module = "edsl.questions.QuestionInvalid"
    invalid_class = "QuestionInvalid"
    # try to import question class that's not registered
    with pytest.raises(QuestionSerializationError) as excinfo:
        get_question_class(invalid_type)
    assert f"No question class registered for type: {invalid_type}" in str(
        excinfo.value
    )
    # add an invalid question type to class registry, and check that import fails
    CLASS_REGISTRY[invalid_type] = (invalid_module, invalid_class)
    with pytest.raises(ModuleNotFoundError) as excinfo:
        get_question_class(invalid_type)
    CLASS_REGISTRY.pop(invalid_type)


def test_forgot_to_register_question():
    """Test fails if a question is added to edsl/questions but not registered in edsl/questions/question_registry.py"""
    paths = ["edsl/questions", "edsl/questions/derived"]
    pattern = re.compile(r"^Question([A-Za-z]+)\.py$")
    for path in paths:
        for file_name in os.listdir(path):
            match = pattern.match(file_name)
            if match:
                class_name = f"Question{match.group(1)}"
                assert any(
                    class_name in pair for pair in CLASS_REGISTRY.values()
                ), f"Forgot to register {class_name} in edsl/questions/question_registry.py"
