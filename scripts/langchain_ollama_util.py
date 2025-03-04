from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM

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
 
# model = OllamaLLM(model="llama3",base_url="http://192.168.109.50:32320")
model = OllamaLLM(model="llama3",base_url="http://desiot.io.vn:20099")

chain = prompt | model

# async def message_user_input(messages:list):
#     conversation = list(map(lambda message: (message['role'], message['content']), messages[:-1]))
#     user_input = (messages[-1]['role'], messages[-1]['content'])

#     async for chunk in chain.astream({"user_input": user_input, "conversation":conversation}):
#         yield f"{chunk}"

def generate(user_input:str):
    return chain.invoke({"user_input": user_input,})