from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_milvus import Milvus
from langchain_ollama import OllamaEmbeddings
# from langchain import hub
import getpass
import os
from langchain.chat_models import init_chat_model
from uuid import uuid4
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.chains.history_aware_retriever import create_history_aware_retriever
from langchain.chains.retrieval import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.messages import HumanMessage

if not os.environ.get("GROQ_API_KEY"):
  os.environ["GROQ_API_KEY"] = getpass.getpass("Enter API key for Groq: ")

URI = "http://localhost:19530"

llm = init_chat_model("llama3-70b-8192", model_provider="groq")

embeddings = OllamaEmbeddings(model="llama3", base_url="http://127.0.0.1:32320", )

vector_store = Milvus(embedding_function=embeddings,connection_args={"uri": URI, "token": "root:Milvus", "db_name": "milvus_demo"},index_params={"index_type": "FLAT", "metric_type": "L2"},
    consistency_level="Strong",
    drop_old=False,  # set to True if seeking to drop the collection with that name if it exists
    )


def ragCreate(file_path:str):

    loader = PyPDFLoader(file_path)
    docs = loader.load()

    # <MilvusException: (code=1701, message=Invalid field name: ptex.fullbanner. Field name can only contain numbers, letters, and underscores.: field name invalid[field=ptex.fullbanner])>
    for doc in docs:
        if 'ptex.fullbanner' in doc.metadata:
            del doc.metadata['ptex.fullbanner']

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    all_splits = text_splitter.split_documents(docs)

    # for i in range(5):
    #    print("sample doc: ", docs[i])

    uuids = [str(uuid4()) for _ in range(len(all_splits))]

    # Index chunks
    _ = vector_store.add_documents(documents=all_splits, ids=uuids)
