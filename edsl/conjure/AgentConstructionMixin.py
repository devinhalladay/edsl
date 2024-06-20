from typing import Generator, List, Optional, Union, Callable
from edsl.agents.Agent import Agent
from edsl.agents.AgentList import AgentList
from edsl.questions import QuestionBase
from edsl.results.Results import Results

class AgentConstructionMixin:

    def agent(self, index) -> Agent:
        """Return an agent constructed from the data."""
        responses = [responses[index] for responses in self.raw_data]
        traits = {qn: r for qn, r in zip(self.question_names, responses)}

        a = Agent(traits=traits, codebook=self.names_to_texts)

        def construct_answer_dict_function(traits: dict) -> Callable:
            def func(self, question: "QuestionBase", scenario=None):
                return traits.get(question.question_name, None)

            return func

        a.add_direct_question_answering_method(construct_answer_dict_function(traits))
        return a

    def _agents(self, indices) -> Generator[Agent, None, None]:
        """Return a generator of agents, one for each index."""
        for idx in indices:
            yield self.agent(idx)

    def to_agent_list(
        self,
        indices: Optional[List] = None,
        sample_size: int = None,
        seed: str = "edsl",
        remove_direct_question_answering_method:bool=True,
    ) -> AgentList:
        """Return an AgentList from the data.

        :param indices: The indices of the agents to include.
        :param sample_size: The number of agents to sample.
        :param seed: The seed for the random number generator.
        """
        if indices and (sample_size or seed != "edsl"):
            raise ValueError(
                "You cannot pass both indices and sample_size/seed, as these are mutually exclusive."
            )

        if indices:
            if len(indices) == 0:
                raise ValueError("Indices must be a non-empty list.")
            if max(indices) >= self.num_observations:
                raise ValueError(
                    f"Index {max(indices)} is greater than the number of agents {self.num_observations}."
                )
            if min(indices) < 0:
                raise ValueError(f"Index {min(indices)} is less than 0.")

        if indices is None:
            if sample_size is None:
                indices = range(self.num_observations)
            else:
                random.seed(seed)
                indices = random.sample(range(self.num_observations), sample_size)

            if sample_size > self.num_observations:
                raise ValueError(
                    f"Sample size {sample_size} is greater than the number of agents {self.num_observations}."
                )
        agents = list(self._agents(indices))
        if remove_direct_question_answering_method:
            for a in agents:
                a.remove_direct_question_answering_method()
        return AgentList(agents)

    def to_results(
        self,
        indices: Optional[List] = None,
        sample_size: int = None,
        seed: str = "edsl",
        dryrun=False,
    ) -> Union[Results, None]:
        """Return the results of the survey.

        :param indices: The indices of the agents to include.
        :param sample_size: The number of agents to sample.
        :param seed: The seed for the random number generator.
        :param dryrun: If True, the survey will not be run, but the time to run it will be printed.
        """
        agent_list = self.to_agent_list(
            indices=indices,
            sample_size=sample_size,
            seed=seed,
            remove_direct_question_answering_method=False,
        )
        survey = self.to_survey()
        if dryrun:
            import time

            start = time.time()
            _ = survey.by(agent_list.sample(10)).run()
            end = time.time()
            print(f"Time to run 10 agents (s): {round(end - start, 2)}")
            time_per_agent = (end - start) / 10
            full_sample_time = time_per_agent * len(agent_list)
            if full_sample_time > 60:
                print(
                    f"Full sample will take about {round(full_sample_time / 60, 2)} minutes."
                )
            if full_sample_time > 3600:
                print(
                    f"Full sample will take about {round(full_sample_time / 3600, 2)} hours."
                )
            if full_sample_time < 60:
                print(
                    f"Full sample will take about {round(full_sample_time, 2)} seconds."
                )
            return None
        return survey.by(agent_list).run()
