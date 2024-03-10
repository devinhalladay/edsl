from edsl import Model
from edsl.questions import QuestionNumerical

m = Model('gpt-4-1106-preview', use_cache=True, temperature = 1)

q = QuestionNumerical(question_text = "Pick a number between 1 and 100", 
                     question_name = "number")

results = q.by(m).run(n = 20)

