from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq

model = ChatGroq(
    model="llama3-70b-8192",
    temperature=0,
    max_tokens=None,
    timeout=None,
    max_retries=2,
    # other params...
)

defaultTemplate = ChatPromptTemplate([
    ("system", "Please act as a professional verilog designer."),
    # Means the template will receive an optional list of messages under
    # the "conversation" key
    ("placeholder", "{conversation}"),
    # Equivalently:
    # MessagesPlaceholder(variable_name="conversation", optional=True)
    ("user", "{user_input}")
])

prompt = defaultTemplate

chain = prompt | model

def generate(user_input:str):
    return chain.invoke({"user_input": user_input,}).content