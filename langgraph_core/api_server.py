"""
FastAPI Server wrapping LangGraph COMBA-PROMPT workflow.

Exposes OpenAI-compatible /v1/chat/completions API.
Open WebUI connects to this server as a custom model endpoint.

Usage:
    uvicorn api_server:app --host 0.0.0.0 --port 8100

Open WebUI config:
    Base URL: http://localhost:8100/v1
    Model:    comba-verilog-generator
"""

import os
import sys
import json
import re
import time
import datetime
import uuid
from typing import Optional, List

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI

from prompts import converterPromptTemplate, generatorPromptTemplate

# XML validation
try:
    from xmlDescription import Module, Modules
    XML_VALIDATION_AVAILABLE = True
except ImportError:
    XML_VALIDATION_AVAILABLE = False

# ──────────────────────────────────────────────────────────────
# Load env
# ──────────────────────────────────────────────────────────────
load_dotenv()

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_API_KEY  = os.environ.get("LLM_API_KEY", "ollama")
LLM_MODEL    = os.environ.get("LLM_MODEL", "qwen2.5-coder:7b")

COMBA_MODEL_NAME = "comba-verilog-generator"

# ──────────────────────────────────────────────────────────────
# LangGraph State & Nodes
# ──────────────────────────────────────────────────────────────
from typing_extensions import TypedDict

class GraphState(TypedDict):
    user_input: str
    xml_description: Optional[str]
    generated_code: Optional[dict]
    module_name: Optional[str]
    error: Optional[str]
    log: list  # step-by-step log for streaming


class CombaWorkflow:
    """Stateless COMBA-PROMPT workflow for API requests."""

    def __init__(self):
        self._llm = ChatOpenAI(
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY,
            model=LLM_MODEL,
            temperature=0.1,
        )
        self._llm_json = self._llm.bind(
            response_format={"type": "json_object"}
        )
        self._graph = self._build_graph()
        print(f"[COMBA] LLM: {LLM_MODEL} @ {LLM_BASE_URL}")

    def _build_graph(self):
        builder = StateGraph(GraphState)
        builder.add_node("converter", self._converter_node)
        builder.add_node("generator", self._generator_node)
        builder.add_edge(START, "converter")
        builder.add_edge("converter", "generator")
        builder.add_edge("generator", END)
        memory = MemorySaver()
        return builder.compile(checkpointer=memory)

    def _is_xml_input(self, text: str) -> bool:
        """Detect if user input is already COMBA XML."""
        stripped = text.strip()
        return stripped.startswith("<module") or stripped.startswith("<modules")

    def _validate_xml(self, xml_text: str):
        """Validate and extract module name from XML."""
        if not XML_VALIDATION_AVAILABLE:
            match = re.search(r'<module\s+id="([^"]+)"', xml_text)
            return True, match.group(1) if match else "module"

        try:
            mod = Module.from_xml(xml_text)
            return True, mod.id
        except Exception:
            try:
                mods = Modules.from_xml(xml_text)
                return True, mods.root[0].id if mods.root else "module"
            except Exception:
                return False, None

    def _converter_node(self, state: GraphState) -> dict:
        user_input = state["user_input"]

        # If already XML, skip conversion
        if self._is_xml_input(user_input):
            valid, name = self._validate_xml(user_input)
            return {
                "xml_description": user_input,
                "module_name": name or "module",
                "log": ["📂 XML input detected — skipping conversion."],
            }

        # NL → COMBA XML
        result = converterPromptTemplate.invoke({
            "user_input": user_input,
            "conversation": [],
        })
        response = self._llm.invoke(result)
        xml_text = response.content.strip()

        # Clean markdown fences
        if xml_text.startswith("```"):
            lines = xml_text.split("\n")
            xml_text = "\n".join(
                l for l in lines if not l.strip().startswith("```")
            )

        valid, name = self._validate_xml(xml_text)

        log_entry = f"🔄 **Converter:** Generated COMBA XML"
        if name:
            log_entry += f" for module `{name}`"
        if not valid:
            log_entry += " ⚠️ (validation failed)"

        return {
            "xml_description": xml_text,
            "module_name": name or "module",
            "log": [log_entry],
        }

    def _generator_node(self, state: GraphState) -> dict:
        xml_desc = state["xml_description"]

        result = generatorPromptTemplate.invoke({
            "user_input": xml_desc,
            "conversation": [],
        })

        code_output = None
        for attempt in range(3):
            try:
                response = self._llm_json.invoke(result)
                code_output = json.loads(response.content)
                break
            except Exception:
                try:
                    response = self._llm.invoke(result)
                    content = response.content.strip()
                    code_output = json.loads(content)
                    break
                except json.JSONDecodeError:
                    # Extract from markdown
                    code_match = re.search(
                        r'```(?:verilog|v)?\s*\n(.*?)\n```',
                        content, re.DOTALL
                    )
                    if code_match:
                        code_output = {
                            "code": code_match.group(1),
                            "description": "Extracted from markdown",
                        }
                        break
                    if attempt == 2:
                        code_output = {
                            "code": content,
                            "description": "Raw output",
                        }

        if code_output and code_output.get("code") and not code_output["code"].endswith("\n"):
            code_output["code"] += "\n"

        return {
            "generated_code": code_output,
            "log": ["⚡ **Generator:** Verilog code generated."],
        }

    def run(self, user_message: str) -> str:
        """Run the full workflow and return formatted response."""
        config = {
            "configurable": {"thread_id": str(uuid.uuid4())},
            "recursion_limit": 50,
        }

        initial_state: GraphState = {
            "user_input": user_message,
            "xml_description": None,
            "generated_code": None,
            "module_name": None,
            "error": None,
            "log": [],
        }

        final = self._graph.invoke(initial_state, config)

        # Format response
        parts = []

        # Logs
        for entry in final.get("log", []):
            parts.append(entry)

        # XML section
        xml = final.get("xml_description", "")
        if xml:
            parts.append(f"\n### COMBA XML Description\n```xml\n{xml}\n```")

        # Verilog code
        gen = final.get("generated_code", {})
        code = gen.get("code", "") if gen else ""
        desc = gen.get("description", "") if gen else ""

        if code:
            parts.append(f"\n### Generated Verilog Code\n```verilog\n{code}```")

        if desc:
            parts.append(f"\n> 📌 {desc}")

        module_name = final.get("module_name", "module")
        parts.append(f"\n✅ Module: `{module_name}` | Lines: {len(code.splitlines())}")

        return "\n".join(parts)


# ──────────────────────────────────────────────────────────────
# FastAPI App
# ──────────────────────────────────────────────────────────────
app = FastAPI(title="COMBA-PROMPT Verilog Generator API")

# Lazy-init workflow (so import doesn't fail if LLM not available)
_workflow: Optional[CombaWorkflow] = None

def get_workflow():
    global _workflow
    if _workflow is None:
        _workflow = CombaWorkflow()
    return _workflow


# ── OpenAI-compatible models ──

class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int = 0
    owned_by: str = "comba"

class ModelsResponse(BaseModel):
    object: str = "list"
    data: List[ModelInfo]


@app.get("/v1/models")
async def list_models():
    return ModelsResponse(data=[
        ModelInfo(id=COMBA_MODEL_NAME, created=int(time.time())),
    ])


# ── OpenAI-compatible chat completions ──

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str = COMBA_MODEL_NAME
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.1
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False

class ChatChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"

class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatChoice]
    usage: Usage = Usage()


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    workflow = get_workflow()

    # Extract user message (last user message)
    user_message = ""
    for msg in reversed(request.messages):
        if msg.role == "user":
            user_message = msg.content
            break

    if not user_message:
        user_message = request.messages[-1].content if request.messages else ""

    # Run COMBA-PROMPT workflow
    try:
        response_text = workflow.run(user_message)
    except Exception as e:
        response_text = f"❌ Error running COMBA-PROMPT workflow:\n```\n{str(e)}\n```"

    completion_id = f"chatcmpl-comba-{uuid.uuid4().hex[:12]}"

    if request.stream:
        # Streaming response (SSE)
        async def stream_generator():
            # Send content in one chunk (LangGraph runs synchronously)
            chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": COMBA_MODEL_NAME,
                "choices": [{
                    "index": 0,
                    "delta": {"role": "assistant", "content": response_text},
                    "finish_reason": None,
                }],
            }
            yield f"data: {json.dumps(chunk)}\n\n"

            # Send finish
            done_chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": COMBA_MODEL_NAME,
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }],
            }
            yield f"data: {json.dumps(done_chunk)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
        )

    return ChatCompletionResponse(
        id=completion_id,
        created=int(time.time()),
        model=COMBA_MODEL_NAME,
        choices=[
            ChatChoice(
                message=ChatMessage(
                    role="assistant",
                    content=response_text,
                ),
            )
        ],
    )


# ── Health check ──
@app.get("/health")
async def health():
    return {"status": "ok", "model": COMBA_MODEL_NAME}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)
