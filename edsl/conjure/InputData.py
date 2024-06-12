from abc import ABC, abstractmethod
from typing import Dict, Callable, Optional, List
from collections import namedtuple, Counter
import pandas as pd

from edsl import ScenarioList
from edsl.conjure.SurveyResponses import SurveyResponses
from edsl.conjure.naming_utilities import sanitize_string
from edsl.conjure.utilities import convert_value, Missing

class InputData(ABC):
    """A class to represent the input data for a survey.
    
    This class can take inputs that will be used or it will infer them.
    Each of the inferred values can be overridden by passing them in.
    """

    NUM_UNIQUE_THRESHOLD = 15
    FRAC_NUMERICAL_THRESHOLD = 0.8
    MULTIPLE_CHOICE_OTHER_THRESHOLD = 0.5
    OTHER_STRING = "Other:"

    question_attributes = ["num_responses", "num_unique_responses", "missing", "unique_responses", "frac_numerical", "top_5", "frac_obs_from_top_5"]
    QuestionStats = namedtuple("QuestionStats", question_attributes)

    def __init__(self, 
                 datafile_name:str, 
                 config: dict, 
                 raw_data: Optional[Dict] = None,
                 question_names: Optional[List[str]] = None, 
                 question_texts: Optional[List[str]] = None, 
                 answer_codebook: Optional[Dict] = None, 
                 question_types: Optional[List[str]] = None, 
                 question_options: Optional[Dict] = None):
        
        self.datafile_name = datafile_name
        self.config = config

        # TO BE INFERRED 
        self.question_texts = question_texts
        self.question_names = question_names
        self.answer_codebook = answer_codebook
        self.raw_data = raw_data
        self.question_types = question_types
        self.question_options = question_options

    @abstractmethod
    def get_question_texts(self) -> Dict:
        """Get the text of the questions
        """
        raise NotImplementedError
    
    @abstractmethod
    def get_raw_data(self) -> SurveyResponses:
        """Returns a dataframe of responses by reading the datafile_name.
        """
        raise NotImplementedError
    
    def to_dict(self):
        return {
            "datafile_name": self.datafile_name,
            "config": self.config,
            "raw_data": self.raw_data,
            "question_names": self.question_names,
            "question_texts": self.question_texts,
            "answer_codebook": self.answer_codebook,
            "question_types": self.question_types
        }
    
    @property
    def num_responses(self):
        return [len(v) for _,v in self.raw_data.items()]
    
    @property
    def num_unique_responses(self):
        return [len(set(v)) for _,v in self.raw_data.items()]

    @property
    def missing(self):
        return [sum([1 for x in v if x == Missing().value()]) for k,v in self.raw_data.items()]
    
    @property
    def frac_numerical(self):
        return [sum([1 for x in v if isinstance(x, (int, float))])/len(v) for k,v in self.raw_data.items()]
    
    def top_k(self, k):
        return [Counter(value).most_common(k) for _ , value in self.raw_data.items()]
    
    def frac_obs_from_top_k(self, k):
        return [round(sum([x[1] for x in Counter(value).most_common(k) if x[0] != 'missing'])/len(value), 2) for key,value in self.raw_data.items()]

    @property
    def frac_obs_from_top_5(self):
        return self.frac_obs_from_top_k(5)
    
    @property
    def top_5(self):
        return self.top_k(5)

    def print(self):
        sl = (ScenarioList.from_list("question_name", self.question_names)
              .add_list("question_text", self.question_texts)
              .add_list("inferred_question_type", [v for k,v in self.question_types.items()])
              .add_list("num_responses", self.num_responses)
              .add_list("num_unique_responses", self.num_unique_responses)
              .add_list("missing", self.missing)
              .add_list("frac_numerical", self.frac_numerical)
              .add_list("top_5_items", self.top_k(5))
              .add_list("frac_obs_from_top_5", self.frac_obs_from_top_k(5)) 
        )
        sl.print()

    def _question_statistics(self, question_name):
        idx = self.question_names.index(question_name)
        return {attr: getattr(self, attr)[idx] for attr in self.question_attributes}
    
    def question_statistics(self, question_name) -> 'QuestionStats':    
        qt = self.QuestionStats(**self._question_statistics(question_name))
        return qt
    
    @property
    def question_types(self):
        return self._question_types
        
    @question_types.setter
    def question_types(self, value):
        if value is None:
            value = {qn: self.infer_question_type(qn) for qn in self.question_names}
        self._question_types = value

    def infer_question_type(self, question_name) -> str:

        qt = self.question_statistics(question_name)
        if qt.num_unique_responses > self.NUM_UNIQUE_THRESHOLD:
            if qt.frac_numerical > self.FRAC_NUMERICAL_THRESHOLD:
                return "numerical"
            if qt.frac_obs_from_top_5 > self.MULTIPLE_CHOICE_OTHER_THRESHOLD:
                return "multiple_choice_with_other"
            return "free_text"
        else:
            return "multiple_choice"

    @property
    def question_options(self):
        return self._question_options
    
    @question_options.setter
    def question_options(self, value):
        if value is None:
            value = {qn: self.get_question_options(qn) for qn in self.question_names}
        self._question_options = value

    def get_question_options(self, question_name):
        qt = self.question_statistics(question_name)
        question_type = self.question_types[question_name]
        if question_type == "multiple_choice":
            return qt.unique_responses
        else:
            if question_type == "multiple_choice_with_other":
                return self.unique_responses_more_than_k(2)[self.question_names.index(question_name)] + [self.OTHER_STRING]
            else:
                return None
                
    @classmethod
    def from_dict(cls, d: Dict):
        return cls(**d)
    
    @staticmethod
    def filter_missing(value):
        return [v for v in value if v != Missing().value() and v != 'missing' and v != '']

    def order_options(self):
        from edsl import QuestionList
        from edsl import ScenarioList
        import textwrap

        scenarios = (ScenarioList
             .from_list("example_question_name", self.question_names)
             .add_list("example_question_text", self.question_texts)
             .add_list("example_question_type",  self.question_types.values())
             .add_list("example_question_options",  self.question_options.values())
             ).filter('example_question_type == "multiple_choice" or example_question_type == "multiple_choice_with_other"')
        
        question = QuestionList(
            question_text=textwrap.dedent("""\
            We have a survey question: `{{ example_question_text }}`.
            
            The survey had following options: '{{ example_question_options }}'.
            The options might be out of order. Please put them in the correct order.
            If there is not natural order, just put then in order they were presented.
            """)
            ,
            question_name="ordering",
        )
        proposed_ordering = question.by(scenarios).run()
        return dict(proposed_ordering.select("example_question_name", "ordering").to_list())
        
        
    @property
    def unique_responses(self) -> dict:
        return [list(set(self.filter_missing(v))) for k, v in self.raw_data.items()]
    
    def unique_responses_more_than_k(self, k, remove_missing = True):
        counters = [Counter(value) for _ , value in self.raw_data.items()]
        new_counters = []
        for question in counters:
            top_options = []
            for option, count in question.items():
                if count > k and (option != 'missing' or not remove_missing):
                    top_options.append(option)
            new_counters.append(top_options)
        return new_counters
     
    @property
    def raw_data(self):
        return self._raw_data
    
    @raw_data.setter
    def raw_data(self, value):
        if value is None:
            value = self.get_raw_data()
        self._raw_data = value

    @property
    def question_texts(self):
        return self._question_texts
    
    @question_texts.setter
    def question_texts(self, value):
        if value is None:
            value = self.get_question_texts()
        self._question_texts = value

    @property
    def question_names(self):
        return self._question_names
    
    @question_names.setter
    def question_names(self, value):
        if value is None:
            value = self.get_question_names()
        self._question_names = value

    @property
    def names_to_texts(self):
        return {n: t for n, t in zip(self.question_names, self.question_texts)}
    
    @property
    def texts_to_names(self):
        return {t: n for n, t in self.names_to_texts.items()}
  
    def get_question_names(self, naming_function: Callable = sanitize_string) -> list:
        return [naming_function(q) for q in self.question_texts]

class InputDataCSV(InputData):

    def get_df(self) -> pd.DataFrame:
        df = pd.read_csv(self.datafile_name, skiprows=self.config['skiprows'])
        df.fillna("", inplace=True)
        df = df.astype(str)
        return df 
    
    def get_raw_data(self) -> SurveyResponses:
        df = self.get_df()
        data = {k: [convert_value(obs) for obs in v] for k, v in df.to_dict(orient="list").items()}
        return SurveyResponses(data)
    
    def get_question_texts(self):
        return list(self.get_df().columns)
    
if __name__ == "__main__":
    config = {
        "skiprows": 1
    }
    #sloan = InputDataCSV("sloan_search.csv", config = {'skiprows': [0, 2]})

    #id2 = InputDataCSV.from_dict(id.to_dict())

    lenny = InputDataCSV("lenny.csv", config = {'skiprows': None})
    #print(data.raw_data)