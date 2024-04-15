import time
import asyncio
import textwrap
from typing import Coroutine, List, AsyncGenerator

from rich.live import Live
from rich.console import Console

from edsl.results import Results, Result

# from edsl.jobs.runners.JobsRunner import JobsRunner
from edsl.jobs.interviews.Interview import Interview
from edsl.utilities.decorators import jupyter_nb_handler
from edsl.jobs.Jobs import Jobs
from edsl.utilities.utilities import is_notebook
from edsl.jobs.runners.JobsRunnerStatusMixin import JobsRunnerStatusMixin

# from edsl.jobs.runners.JobsRunHistory import JobsRunHistory

from edsl.data.Cache import Cache

# from edsl.jobs.tasks.task_status_enum import TaskStatus

from edsl.jobs.tasks.TaskHistory import TaskHistory


class JobsRunnerAsyncio(JobsRunnerStatusMixin):
    def __init__(self, jobs: Jobs):
        self.jobs = jobs

        self.interviews: List["Interview"] = jobs.interviews()
        self.bucket_collection: "BucketCollection" = jobs.bucket_collection
        self.total_interviews: List["Interview"] = []

    def populate_total_interviews(self, n=1) -> None:
        """Populates self.total_interviews with n copies of each interview.

        :param n: how many times to run each interview.
        """
        self.total_interviews = []
        for interview in self.interviews:
            for iteration in range(n):
                if iteration > 0:
                    new_interview = Interview(
                        agent=interview.agent,
                        survey=interview.survey,
                        scenario=interview.scenario,
                        model=interview.model,
                        debug=interview.debug,
                        iteration=iteration,
                        cache=self.cache,
                    )
                    self.total_interviews.append(new_interview)
                else:
                    interview.cache = self.cache
                    self.total_interviews.append(interview)

    async def run_async(
        self,
        cache,
        n: int = 1,
        debug: bool = False,
        stop_on_exception: bool = False,
        sidecar_model = None,
    ) -> AsyncGenerator[Result, None]:
        """Creates the tasks, runs them asynchronously, and returns the results as a Results object.

        Completed tasks are yielded as they are completed.

        :param n: how many times to run each interview
        :param debug:
        :param stop_on_exception:
        """
        tasks = []
        self.populate_total_interviews(
            n=n
        )  # Populate self.total_interviews before creating tasks

        for interview in self.total_interviews:
            interviewing_task = self._interview_task(
                interview=interview, debug=debug, stop_on_exception=stop_on_exception, sidecar_model=sidecar_model
            )
            tasks.append(asyncio.create_task(interviewing_task))

        for task in asyncio.as_completed(tasks):
            result = await task
            yield result

    async def _interview_task(
        self, *, interview: Interview, debug: bool, stop_on_exception: bool = False, sidecar_model = None
    ) -> Result:
        """Conducts an interview and returns the result.

        :param interview: the interview to conduct
        :param debug: prints debug messages
        """
        # the model buckets are used to track usage rates
        model_buckets = self.bucket_collection[interview.model]

        # get the results of the interview
        answer, valid_results = await interview.async_conduct_interview(
            debug=debug,
            model_buckets=model_buckets,
            stop_on_exception=stop_on_exception,
            sidecar_model=sidecar_model,
        )

        # we should have a valid result for each question
        answer_key_names = {k for k in set(answer.keys()) if not k.endswith("_comment")}

        assert len(valid_results) == len(answer_key_names)

        # TODO: move this down into Interview
        question_name_to_prompts = dict({})
        for result in valid_results:
            question_name = result["question_name"]
            question_name_to_prompts[question_name] = {
                "user_prompt": result["prompts"]["user_prompt"],
                "system_prompt": result["prompts"]["system_prompt"],
            }

        prompt_dictionary = {}
        for answer_key_name in answer_key_names:
            prompt_dictionary[
                answer_key_name + "_user_prompt"
            ] = question_name_to_prompts[answer_key_name]["user_prompt"]
            prompt_dictionary[
                answer_key_name + "_system_prompt"
            ] = question_name_to_prompts[answer_key_name]["system_prompt"]

        raw_model_results_dictionary = {}
        for result in valid_results:
            question_name = result["question_name"]
            raw_model_results_dictionary[
                question_name + "_raw_model_response"
            ] = result["raw_model_response"]

        result = Result(
            agent=interview.agent,
            scenario=interview.scenario,
            model=interview.model,
            iteration=interview.iteration,
            answer=answer,
            prompt=prompt_dictionary,
            raw_model_response=raw_model_results_dictionary,
            survey=interview.survey,
        )
        return result

    @property
    def elapsed_time(self):
        return time.monotonic() - self.start_time

    @jupyter_nb_handler
    async def run(
        self,
        cache,
        n: int = 1,
        debug: bool = False,
        stop_on_exception: bool = False,
        progress_bar=False,
        sidecar_model=None,
        batch_mode = False
    ) -> "Coroutine":
        """Runs a collection of interviews, handling both async and sync contexts."""
        console = Console()
        self.results = []
        self.start_time = time.monotonic()
        self.completed = False
        self.cache = cache
        self.sidecar_model = sidecar_model

        def generate_table():
            return self.status_table(self.results, self.elapsed_time)

        from contextlib import contextmanager

        @contextmanager
        def no_op_cm():
            """A no-op context manager with a dummy update method."""
            yield DummyLive()

        class DummyLive:
            def update(self, *args, **kwargs):
                """A dummy update method that does nothing."""
                pass

        progress_bar_context = (
            Live(generate_table(), console=console, refresh_per_second=5)
            if progress_bar
            else no_op_cm()
        )

        with cache as c:
            with progress_bar_context as live:

                async def update_progress_bar():
                    """Updates the progress bar at fixed intervals."""
                    while True:
                        live.update(generate_table())
                        await asyncio.sleep(0.1)  # Update interval
                        if self.completed:
                            break

                async def process_results():
                    """Processes results from interviews."""
                    async for result in self.run_async(
                        n=n, debug=debug, stop_on_exception=stop_on_exception, cache=c, 
                        sidecar_model=sidecar_model
                    ):
                        self.results.append(result)
                        live.update(generate_table())
                    self.completed = True

                # logger_task = asyncio.create_task(self.periodic_logger(period=0.01))
                progress_task = asyncio.create_task(update_progress_bar())

                try:
                    await asyncio.gather(process_results(), progress_task)
                except asyncio.CancelledError:
                    pass
                finally:
                    progress_task.cancel()  # Cancel the progress_task when process_results is done
                    await progress_task

                    await asyncio.sleep(1)  # short delay to show the final status

                    # one more update
                    live.update(generate_table())

        results = Results(survey=self.jobs.survey, data=self.results)
        results.task_history = TaskHistory(self.total_interviews)

        if results.task_history.has_exceptions and not batch_mode:
            print(
                textwrap.dedent(f"""\Exceptions were raised in the following interviews: {results.task_history.indices}"""
                )
            )
            show = input("Print exceptions? (y/n): ")
            if show == "y":
                if is_notebook():
                    print(results.task_history._repr_html_())
                else:
                    results.task_history.show_exceptions()

            upload = input("Ok to upload errors to us  - we can potentially help! (y/n): ")
            if upload == "y":
                try:
                    from edsl.jobs.interviews.ReportErrors import ReportErrors
                    report = ReportErrors(results.task_history)
                    report.get_email()
                    report.upload()
                except Exception as e:
                    print(f"Error uploading errors: {e}")
                # import json
                # import requests
                # email = input("Please enter your email address (if you want us to get in touch): ")
                # url = 'https://375b1a19-3a5b-444d-9925-a81164a5bd2c-00-23kgwodh3kmtc.picard.replit.dev/messages/'
                # # JSON object to send
                # data = {
                #     "text": results.task_history.to_dict(),
                #     "email": email,
                # }
                # # Convert the Python dictionary to a JSON string before sending
                # json_data = json.dumps(data)
                # #breakpoint()
                # headers = {
                #     "Content-Type": "application/json"
                # }

                # # Send the POST request
                # response = requests.post(url, data=json_data, headers=headers)
                # #breakpoint()
                # # Print the response from the server
                # print("Status Code:", response.status_code)
                # print("Response Content:", response.json())
                #results.task_history.upload_exceptions()
        return results
