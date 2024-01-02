from __future__ import annotations
from collections import UserList
from typing import Optional, Union
from edsl.scenarios.Scenario import Scenario


class ScenarioList(UserList):
    def __init__(self, data: Optional[list] = None):
        if data is not None:
            super().__init__(data)

    def to(self, question_or_survey: Union["Question", "Survey"]):
        return question_or_survey.by(*self)

    @classmethod
    def from_csv(cls, filename):
        import csv

        observations = []
        with open(filename, "r") as f:
            reader = csv.reader(f)
            header = next(reader)
            for row in reader:
                observations.append(Scenario(dict(zip(header, row))))
        return cls(observations)

    def to_dict(self):
        return {"scenarios": [s.to_dict() for s in self]}

    @classmethod
    def from_dict(cls, data):
        return cls([Scenario.from_dict(s) for s in data["scenarios"]])

    def code(self):
        ## TODO: Refactor to only use the questions actually in the survey
        "Creates the Python code representation of a survey"
        header_lines = [
            "from edsl.scenarios.Scenario import Scenario",
            "from edsl.scenarios.ScenarioList import ScenarioList",
        ]
        lines = ["\n".join(header_lines)]
        names = []
        for index, scenario in enumerate(self):
            lines.append(f"scenario_{index} = " + repr(scenario))
            names.append(f"scenario_{index}")
        lines.append(f"scenarios = ScenarioList([{', '.join(names)}])")
        return lines


if __name__ == "__main__":
    from edsl.questions.QuestionMultipleChoice import QuestionMultipleChoice
    from edsl.scenarios.Scenario import Scenario

    q = QuestionMultipleChoice(
        question_text="Do you enjoy the taste of {{food}}?",
        question_options=["Yes", "No"],
        question_name="food_preference",
    )

    scenario_list = ScenarioList(
        [Scenario({"food": "wood chips"}), Scenario({"food": "wood-fired pizza"})]
    )

    print(scenario_list.code())

    results = scenario_list.to(q).run()
    print(results)
