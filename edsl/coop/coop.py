import json
import os
import requests
from typing import Any, Optional, Type, Union
from edsl import CONFIG
from edsl.agents import Agent, AgentList
from edsl.questions.QuestionBase import QuestionBase
from edsl.results import Results
from edsl.surveys import Survey
from edsl.data.CacheEntry import CacheEntry


api_url = {
    "development": "http://127.0.0.1:8000",
    "development-testrun": "http://127.0.0.1:8000",
    "production": "http://127.0.0.1:8000",
}


class Coop:
    """
    Client for the Expected Parrot API.
    """

    def __init__(self, api_key: str = None, run_mode: str = None) -> None:
        self.api_key = api_key or os.getenv("EXPECTED_PARROT_API_KEY")
        self.run_mode = run_mode or CONFIG.EDSL_RUN_MODE
        self._api_key_is_valid()

    ################
    # BASIC METHODS
    ################
    @property
    def headers(self) -> dict:
        """
        Returns the headers for the request.
        """
        return {"Authorization": f"Bearer {self.api_key}"}

    @property
    def url(self) -> str:
        """
        Returns the URL for the request.
        """
        return api_url[self.run_mode]

    def _send_server_request(
        self,
        uri: str,
        method: str,
        payload: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> requests.Response:
        """
        Sends a request to the server and returns the response.
        """
        url = f"{self.url}/{uri}"

        if method.upper() in ["GET", "DELETE"]:
            response = requests.request(
                method, url, params=params, headers=self.headers
            )
        else:
            response = requests.request(method, url, json=payload, headers=self.headers)

        return response

    def _resolve_server_response(self, response: requests.Response) -> None:
        """
        Checks the response from the server and raises appropriate errors.
        """
        if response.status_code >= 400:
            raise Exception(response.json().get("detail"))

    ################
    # VALIDATION METHODS
    ################
    def _api_key_is_valid(self) -> None:
        """
        Checks if the API key is valid.
        """
        if not self.api_key:
            raise ValueError("API key is required.")
        if not isinstance(self.api_key, str):
            raise ValueError("API key must be a string.")
        response = self._send_server_request(uri="api/v0/validate-apikey", method="GET")
        self._resolve_server_response(response)

    ################
    # CACHE METHODS
    ################
    def create_cache_entry(self, cache_entry: CacheEntry) -> dict:
        """
        Creates a CacheEntry object.
        """
        response = self._send_server_request(
            uri="api/v0/cache/create-cache-entry",
            method="POST",
            payload={
                "json_string": json.dumps(
                    {"key": cache_entry.key, "value": json.dumps(cache_entry.to_dict())}
                )
            },
        )
        self._resolve_server_response(response)
        return response.json()

    def get_cache_entries(
        self, exclude_keys: Optional[list[str]] = None
    ) -> list[CacheEntry]:
        """
        Returns CacheEntry objects from the server.
        - `exclude_keys`: exclude CacheEntry objects with these keys.
        """
        if exclude_keys is None:
            exclude_keys = []
        response = self._send_server_request(
            uri="api/v0/cache/get-cache-entries",
            method="POST",
            payload={"json_string": json.dumps(exclude_keys)},
        )
        self._resolve_server_response(response)
        return [
            CacheEntry.from_dict(json.loads(v.get("json_string")))
            for v in response.json()
        ]

    def send_cache_entries(self, cache_entries: dict[str, CacheEntry]) -> None:
        """
        Sends a dictionary of CacheEntry objects to the server.
        """
        response = self._send_server_request(
            uri="api/v0/cache/create-cache-entries",
            method="POST",
            payload={
                "json_string": json.dumps(
                    {k: json.dumps(v.to_dict()) for k, v in cache_entries.items()}
                )
            },
        )
        self._resolve_server_response(response)
        return response.json()

    ################
    # EDSL METHODS
    ################
    # TODO: Re-factor all methods to use this method.
    def _create_edsl_object(
        self,
        edsl_object: Union[Type[QuestionBase], Type[Survey]],
        uri: str,
        public: bool = False,
    ) -> dict:
        """
        General method to create EDSL objects

        - `edsl_object`:
        - `uri`: the API endpoint to send the request to.
        - `public`: whether the object should be public (defaults to False).
        """
        response = self._send_server_request(
            uri=uri,
            method="POST",
            payload={
                "json_string": json.dumps(edsl_object.to_dict()),
                "public": public,
            },
        )
        self._resolve_server_response(response)
        return response.json()

    def create_question(
        self, question: Type[QuestionBase], public: bool = False
    ) -> dict:
        """
        Create a Question object.

        - `question`: the EDSL Question to be sent.
        - `public`: whether the question should be public (defaults to False)
        """
        return self._create_edsl_object(question, "api/v0/questions", public)

    # QUESTIONS METHODS
    def create_question(
        self, question: Type[QuestionBase], public: bool = False
    ) -> dict:
        """
        Create a Question object.

        - `question`: the EDSL Question to be sent.
        - `public`: whether the question should be public (defaults to False)
        """
        response = self._send_server_request(
            uri="api/v0/questions",
            method="POST",
            payload={"json_string": json.dumps(question.to_dict()), "public": public},
        )
        self._resolve_server_response(response)
        return response.json()

    def get_question(self, id: int) -> Type[QuestionBase]:
        """Retrieve a Question object by id."""
        response = self._send_server_request(uri=f"api/v0/questions/{id}", method="GET")
        self._resolve_server_response(response)
        return QuestionBase.from_dict(json.loads(response.json().get("json_string")))

    @property
    def questions(self) -> list[dict[str, Union[int, QuestionBase]]]:
        """Retrieve all Questions."""
        response = self._send_server_request(uri="api/v0/questions", method="GET")
        self._resolve_server_response(response)
        questions = [
            {
                "id": q.get("id"),
                "question": QuestionBase.from_dict(json.loads(q.get("json_string"))),
            }
            for q in response.json()
        ]
        return questions

    def delete_question(self, id: int) -> dict:
        """Delete a question from the coop."""
        response = self._send_server_request(
            uri=f"api/v0/questions/{id}", method="DELETE"
        )
        self._resolve_server_response(response)
        return response.json()

    # Surveys METHODS
    def create_survey(self, survey: Type[Survey], public: bool = False) -> dict:
        """
        Create a Question object.

        - `survey`: the EDSL Survey to be sent.
        - `public`: whether the survey should be public (defaults to False)
        """
        response = self._send_server_request(
            uri="api/v0/surveys",
            method="POST",
            payload={"json_string": json.dumps(survey.to_dict()), "public": public},
        )
        self._resolve_server_response(response)
        return response.json()

    def get_survey(self, id: int) -> Type[Survey]:
        """Retrieve a Survey object by id."""
        response = self._send_server_request(uri=f"api/v0/surveys/{id}", method="GET")
        self._resolve_server_response(response)
        return Survey.from_dict(json.loads(response.json().get("json_string")))

    @property
    def surveys(self) -> list[dict[str, Union[int, Survey]]]:
        """Retrieve all Surveys."""
        response = self._send_server_request(uri="api/v0/surveys", method="GET")
        self._resolve_server_response(response)
        surveys = [
            {
                "id": q.get("id"),
                "survey": Survey.from_dict(json.loads(q.get("json_string"))),
            }
            for q in response.json()
        ]
        return surveys

    def delete_survey(self, id: int) -> dict:
        """Delete a Survey from the coop."""
        response = self._send_server_request(
            uri=f"api/v0/surveys/{id}", method="DELETE"
        )
        self._resolve_server_response(response)
        return response.json()

    # AGENT METHODS
    def create_agent(
        self, agent: Union[Agent, AgentList], public: bool = False
    ) -> dict:
        """
        Creates an Agent or AgentList object.
        - `agent`: the EDSL Agent or AgentList to be sent.
        - `public`: whether the agent should be public (defaults to False)
        """
        response = self._send_server_request(
            uri="api/v0/agents",
            method="POST",
            payload={"json_string": json.dumps(agent.to_dict()), "public": public},
        )
        self._resolve_server_response(response)
        return response.json()

    def get_agent(self, id: int) -> Union[Agent, AgentList]:
        """Retrieves an Agent or AgentList object by id."""
        response = self._send_server_request(uri=f"api/v0/agents/{id}", method="GET")
        self._resolve_server_response(response)
        agent_dict = json.loads(response.json().get("json_string"))
        if "agent_list" in agent_dict:
            return AgentList.from_dict(agent_dict)
        else:
            return Agent.from_dict(agent_dict)

    @property
    def agents(self) -> list[dict[str, Union[int, Agent, AgentList]]]:
        """Retrieves all Agents and AgentLists."""
        response = self._send_server_request(uri="api/v0/agents", method="GET")
        self._resolve_server_response(response)
        agents = []
        for q in response.json():
            agent_dict = json.loads(q.get("json_string"))
            if "agent_list" in agent_dict:
                agent = AgentList.from_dict(agent_dict)
            else:
                agent = Agent.from_dict(agent_dict)
            agents.append({"id": q.get("id"), "agent": agent})
        return agents

    def delete_agent(self, id: int) -> dict:
        """Deletes an Agent or AgentList from the coop."""
        response = self._send_server_request(uri=f"api/v0/agents/{id}", method="DELETE")
        self._resolve_server_response(response)
        return response.json()

    # RESULTS METHODS
    def create_results(self, results: Results, public: bool = False) -> dict:
        """
        Creates a Results object.
        - `results`: the EDSL Results to be sent.
        - `public`: whether the Results should be public (defaults to False)
        """
        response = self._send_server_request(
            uri="api/v0/results",
            method="POST",
            payload={"json_string": json.dumps(results.to_dict()), "public": public},
        )
        self._resolve_server_response(response)
        return response.json()

    def get_results(self, id: int) -> Results:
        """Retrieves a Results object by id."""
        response = self._send_server_request(uri=f"api/v0/results/{id}", method="GET")
        self._resolve_server_response(response)
        return Results.from_dict(json.loads(response.json().get("json_string")))

    @property
    def results(self) -> list[dict[str, Union[int, Results]]]:
        """Retrieves all Results."""
        response = self._send_server_request(uri="api/v0/results", method="GET")
        self._resolve_server_response(response)
        results = [
            {
                "id": r.get("id"),
                "survey": Results.from_dict(json.loads(r.get("json_string"))),
            }
            for r in response.json()
        ]
        return results

    def delete_results(self, id: int) -> dict:
        """Deletes a Results object from the coop."""
        response = self._send_server_request(
            uri=f"api/v0/results/{id}", method="DELETE"
        )
        self._resolve_server_response(response)
        return response.json()

    def push(self, object, public):
        if isinstance(object, QuestionBase):
            return self.create_question(object, public)
        elif isinstance(object, Survey):
            return self.create_survey(object, public)
        elif isinstance(object, Agent) or isinstance(object, AgentList):
            return self.create_agent(object, public)
        elif isinstance(object, Results):
            return self.create_results(object, public)
        else:
            raise ValueError("Object type not recognized")

    def pull(self, cls, id):
        if issubclass(cls, QuestionBase):
            return self.get_question(id)
        elif cls == Survey:
            return self.get_survey(id)
        elif cls == Agent or cls == AgentList:
            return self.get_agent(id)
        elif cls == Results:
            return self.get_results(id)
        else:
            raise ValueError("Class type not recognized")

    ################
    # DUNDER METHODS
    ################
    def __repr__(self):
        """Return a string representation of the client."""
        return f"Client(api_key='{self.api_key}', run_mode='{self.run_mode}')"


if __name__ == "__main__":
    from edsl.coop import Coop

    API_KEY = "a"
    RUN_MODE = "development"
    coop = Coop(api_key=API_KEY, run_mode=RUN_MODE)

    # basics
    coop
    coop.headers
    coop.url

    ##############
    # E. CACHE
    ##############
    from edsl.data.CacheEntry import CacheEntry

    # should be empty in the beginning
    coop.get_cache_entries()
    # now create one cache entry
    cache_entry = CacheEntry.example()
    coop.create_cache_entry(cache_entry)
    # see that if you try to create it again, you'll get the same id
    coop.create_cache_entry(cache_entry)
    # now get all your cache entries
    coop.get_cache_entries()
    coop.get_cache_entries(exclude_keys=[])
    coop.get_cache_entries(exclude_keys=["a"])
    # this will be empty
    coop.get_cache_entries(exclude_keys=[cache_entry.key])
    # now send many cache entries
    cache_entries = {}
    for i in range(10):
        cache_entry = CacheEntry.example(randomize=True)
        cache_entries[cache_entry.key] = cache_entry
    coop.send_cache_entries(cache_entries)

    ##############
    # A. QUESTIONS
    ##############
    from edsl.questions import QuestionMultipleChoice
    from edsl.questions import QuestionCheckBox
    from edsl.questions import QuestionFreeText

    # check questions on server (should be an empty list)
    coop.questions
    for question in coop.questions:
        coop.delete_question(question.get("id"))

    # get a question that does not exist (should return None)
    coop.get_question(id=1)

    # now post a Question
    coop.create_question(QuestionMultipleChoice.example())
    coop.create_question(QuestionCheckBox.example(), public=False)
    coop.create_question(QuestionFreeText.example(), public=True)

    # check all questions
    coop.questions

    # or get question by id
    coop.get_question(id=1)

    # delete the question
    coop.delete_question(id=1)

    # check all questions
    coop.questions

    ##############
    # B. Surveys
    ##############
    from edsl.surveys import Survey

    # check surveys on server (should be an empty list)
    coop.surveys
    for survey in coop.surveys:
        coop.delete_survey(survey.get("id"))

    # get a survey that does not exist (should return None)
    coop.get_survey(id=1)

    # now post a Survey
    coop.create_survey(Survey.example())
    coop.create_survey(Survey.example(), public=False)
    coop.create_survey(Survey.example(), public=True)
    coop.create_survey(Survey(), public=True)
    s = Survey().example()
    for i in range(10):
        q = QuestionFreeText.example()
        q.question_name = f"question_{i}"
        s.add_question(q)
    coop.create_survey(s, public=True)

    # check all surveys
    coop.surveys

    # or get survey by id
    coop.get_survey(id=1)

    # delete the survey
    coop.delete_survey(id=1)

    # check all surveys
    coop.surveys

    ##############
    # C. Agents and AgentLists
    ##############
    from edsl.agents import Agent, AgentList

    # check agents on server (should be an empty list)
    coop.agents
    for agent in coop.agents:
        coop.delete_agent(agent.get("id"))

    # get an agent that does not exist (should return None)
    coop.get_agent(id=2)

    # now post an Agent
    coop.create_agent(Agent.example())
    coop.create_agent(Agent.example(), public=False)
    coop.create_agent(Agent.example(), public=True)
    coop.create_agent(
        Agent(traits={"hair_type": "curly", "skil_color": "white"}), public=True
    )
    coop.create_agent(AgentList.example())
    coop.create_agent(AgentList.example(), public=False)
    coop.create_agent(AgentList.example(), public=True)

    # check all agents
    coop.agents

    # or get agent by id
    coop.get_agent(id=1)

    # delete the agent
    coop.delete_agent(id=1)

    # check all agents
    coop.agents

    ##############
    # D. Results
    ##############
    from edsl.results import Results

    # check results on server (should be an empty list)
    len(coop.results)
    for results in coop.results:
        coop.delete_results(results.get("id"))

    # get a result that does not exist (should return None)
    coop.get_results(id=2)

    # now post a Results
    coop.create_results(Results.example())
    coop.create_results(Results.example(), public=False)
    coop.create_results(Results.example(), public=True)

    # check all results
    coop.results

    # or get results by id
    coop.get_results(id=1)

    # delete the results
    coop.delete_results(id=1)

    # check all results
    coop.results
