import getpass
import os
from typing import Annotated

from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import MemorySaver


class State(TypedDict):
    # Messages have the type "list". The `add_messages` function
    # in the annotation defines how this state key should be updated
    # (in this case, it appends messages to the list, rather than overwriting them)
    messages: Annotated[list, add_messages]


class LLMCodeAgent:
    def __init__(self, modulePath: str):
        if not os.environ.get("GROQ_API_KEY"):
            os.environ["GROQ_API_KEY"] = getpass.getpass("Enter API key for Groq: ")

        self._llm = init_chat_model("llama3-8b-8192", model_provider="groq")

        graph_builder = StateGraph(State)

        graph_builder.add_node("chatbot", self.chatbot)
        graph_builder.add_edge(START, "chatbot")
        graph_builder.add_edge("chatbot", END)

        #
        # memory
        memory = MemorySaver()

        self._graph = graph_builder.compile(checkpointer=memory)

        #
        # config
        self._config = {"configurable": {"thread_id": "1"}}

    def chatbot(self, state: State):
        # print("messages update:", state["messages"])
        return {"messages": [self._llm.invoke(state["messages"])]}

    def stream_graph_updates(self, user_input: str):
        # for event in self._graph.stream(
        #     {"messages": [{"role": "user", "content": user_input}]},
        #     self._config,
        #     stream_mode="values",
        # ):
        #     for value in event.values():
        #         print("Assistant:", value["messages"][-1].content)
        events = self._graph.stream(
            {"messages": [{"role": "user", "content": user_input}]},
            self._config,
            stream_mode="values",
        )
        for event in events:
            event["messages"][-1].pretty_print()

    def __next__(self):
        confirm = input(f"Next? (y/n) ")
        if confirm == "n" or confirm == "N":
            print("End Agent")
            raise StopIteration

        try:
            user_input = input("User: ")
            if user_input.lower() in ["quit", "exit", "q"]:
                print("Goodbye!")
                raise StopIteration

            self.stream_graph_updates(user_input)
        except:
            # fallback if input() is not available
            user_input = "What do you know about LangGraph?"
            print("User: " + user_input)
            self.stream_graph_updates(user_input)
            raise StopIteration

        x = self.a
        self.a += 1
        return (x, "Nope")

    def __iter__(self):
        self.a = 1
        self.status = "error"
        return self

    def __call__(self):
        print("Start agent")
        myiter = iter(self)
        currentStatus = None
        for x in myiter:
            currentStatus = x
            print("iter status", currentStatus[1], ". iter times: ", currentStatus[0])

        print("last status", currentStatus[1], ". iter times: ", currentStatus[0])
