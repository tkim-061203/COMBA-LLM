"""
FastAPI Server wrapping LangGraph COMBA-PROMPT v2 Pipeline.

Exposes OpenAI-compatible /v1/chat/completions API with real SSE streaming.
Each pipeline node (Converter, Generator, Syntax Check, etc.) emits an SSE
event so Open WebUI shows progressive updates.

Usage:
    uvicorn api_server:app --host 0.0.0.0 --port 8100

    # With stub LLM (testing):
    COMBA_USE_STUB=1 uvicorn api_server:app --host 0.0.0.0 --port 8100

Open WebUI config:
    Base URL: http://localhost:8100/v1
    Model:    comba-verilog-pipeline
"""

import os
import json
import re
import time
import uuid
import asyncio
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from comba_pipeline import build_comba_graph, make_initial_state, COMBAState

load_dotenv()

COMBA_MODEL_NAME = "comba-verilog-pipeline"

# Thread pool for running synchronous LangGraph in async context
_executor = ThreadPoolExecutor(max_workers=4)


# ──────────────────────────────────────────────────────────────
# LLM Initialization
# ──────────────────────────────────────────────────────────────

def create_llm():
    """Create LLM based on environment configuration."""
    use_stub = os.environ.get("COMBA_USE_STUB", "").lower() in ("1", "true", "yes")

    if use_stub:
        from stub_llm import create_stub_llm
        print("[COMBA API] Using StubLLM (testing mode)")
        return create_stub_llm()

    # Try COMBALlm (dual-GPU) first
    try:
        from llm_interface import COMBALlm
        llm = COMBALlm.from_env()
        print(f"[COMBA API] Using COMBALlm: {llm}")
        return llm
    except Exception as e:
        print(f"[COMBA API] COMBALlm failed ({e}), falling back to ChatOpenAI")

    # Fallback to ChatOpenAI
    from langchain_openai import ChatOpenAI
    base_url = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
    api_key = os.environ.get("LLM_API_KEY", "ollama")
    model = os.environ.get("LLM_MODEL", "qwen2.5-coder:7b")
    print(f"[COMBA API] Using ChatOpenAI: {model} @ {base_url}")
    return ChatOpenAI(base_url=base_url, api_key=api_key, model=model, temperature=0.1)


# ──────────────────────────────────────────────────────────────
# SSE Helpers
# ──────────────────────────────────────────────────────────────

def make_sse_chunk(completion_id: str, content: str, finish_reason=None) -> str:
    """Create an OpenAI-compatible SSE chunk."""
    chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": COMBA_MODEL_NAME,
        "choices": [{
            "index": 0,
            "delta": {"content": content} if content else {},
            "finish_reason": finish_reason,
        }],
    }
    return f"data: {json.dumps(chunk)}\n\n"


def format_node_event(node_name: str, state_update: dict, full_state: dict) -> str:
    """Format a pipeline node's output as a human-readable SSE message."""

    if node_name == "node_converter":
        module_name = state_update.get("module_name") or "module"
        xml = state_update.get("xml_description", "")
        lines = len(xml.splitlines()) if xml else 0
        return f"🔄 **Converter:** Generated COMBA XML for `{module_name}` ({lines} lines)\n\n"

    elif node_name == "node_generator":
        gvd = state_update.get("gvd", "")
        lines = len(gvd.splitlines()) if gvd else 0
        return f"⚡ **Generator:** Produced {lines} lines of Verilog\n\n"

    elif node_name == "node_syntax_check":
        trial = state_update.get("sc_trial", "?")
        errors = state_update.get("sc_exception_count", 0)
        if errors == 0:
            return f"🔍 **Syntax Check #{trial}:** Pass ✅\n\n"
        else:
            exc = state_update.get("sc_exception", "")
            return f"🔍 **Syntax Check #{trial}:** {errors} error(s) ❌\n> `{exc[:100]}`\n\n"

    elif node_name == "node_ted_syntax":
        exc = state_update.get("sc_exception", "")
        return f"📋 **TED-SC:** Topmost error → `{exc[:120]}`\n\n"

    elif node_name == "node_debugger":
        patch = state_update.get("debugger_patch")
        if patch:
            buggy = patch.get("buggy_code", "")[:80]
            return f"🐛 **Debugger:** Generated JSON patch\n> buggy: `{buggy}...`\n\n"
        return "🐛 **Debugger:** No patch produced ⚠️\n\n"

    elif node_name == "node_patcher":
        rollback = state_update.get("rollback_triggered", False)
        if rollback:
            return "🩹 **Patcher:** Patch skipped (no match or rollback) ⚠️\n\n"
        return "🩹 **Patcher:** Patch applied ✅\n\n"

    elif node_name == "node_tb_sim":
        trial = state_update.get("ts_trial", "?")
        failure = state_update.get("tb_failure")
        if not failure:
            return f"🧪 **TB Simulation #{trial}:** Pass ✅\n\n"
        return f"🧪 **TB Simulation #{trial}:** Failed ❌\n> `{failure[:100]}`\n\n"

    elif node_name == "node_ted_tb":
        failure = state_update.get("tb_failure", "")
        return f"📋 **TED-TB:** Topmost failure → `{failure[:120]}`\n\n"

    elif node_name.startswith("end_"):
        status = state_update.get("final_status", node_name)
        emoji = "🎉" if status == "pass" else "❌"
        return f"\n---\n{emoji} **Pipeline Result:** `{status}`\n\n"

    return ""


def format_final_output(final_state: dict) -> str:
    """Format the final Verilog code and summary after pipeline completes."""
    parts = []

    status = final_state.get("final_status", "unknown")
    module_name = final_state.get("module_name", "module")
    sc_trials = final_state.get("sc_trial", 0)
    ts_trials = final_state.get("ts_trial", 0)
    total_iter = final_state.get("total_iter", 0)

    # XML section
    xml = final_state.get("xml_description", "")
    if xml:
        parts.append(f"### COMBA XML Description\n```xml\n{xml}\n```\n")

    # Verilog code section
    gvd = final_state.get("gvd", "")
    if gvd:
        parts.append(f"### Generated Verilog Code\n```verilog\n{gvd}```\n")

    # Summary
    parts.append(
        f"| Metric | Value |\n"
        f"|--------|-------|\n"
        f"| Module | `{module_name}` |\n"
        f"| Status | `{status}` |\n"
        f"| SC Trials | {sc_trials} |\n"
        f"| TS Trials | {ts_trials} |\n"
        f"| Total Iterations | {total_iter} |\n"
        f"| Lines of Verilog | {len(gvd.splitlines()) if gvd else 0} |\n"
    )

    return "\n".join(parts)


# ──────────────────────────────────────────────────────────────
# Pipeline Runner
# ──────────────────────────────────────────────────────────────

_llm = None
_graph = None


def get_graph():
    """Lazy-init the pipeline graph."""
    global _llm, _graph
    if _graph is None:
        _llm = create_llm()
        _graph = build_comba_graph(_llm)
        print(f"[COMBA API] Pipeline graph compiled: {COMBA_MODEL_NAME}")
    return _graph


def is_xml_input(text: str) -> bool:
    """Detect if user input is already COMBA XML."""
    stripped = text.strip()
    return stripped.startswith("<module") or stripped.startswith("<modules")


def run_pipeline_streaming(user_message: str):
    """
    Run the full COMBA pipeline, yielding (node_name, state_update) per step.
    Uses graph.stream() for node-by-node execution.
    """
    graph = get_graph()

    state = make_initial_state(nl_input=user_message)

    # If user provides raw XML, inject it directly
    if is_xml_input(user_message):
        state["xml_description"] = user_message
        match = re.search(r'<module\s+id="([^"]+)"', user_message)
        if match:
            state["module_name"] = match.group(1)

    config = {"recursion_limit": 100}

    # graph.stream() yields dict: {node_name: state_update}
    for event in graph.stream(state, config):
        for node_name, state_update in event.items():
            yield node_name, state_update


def run_pipeline_sync(user_message: str) -> dict:
    """Run the full COMBA pipeline synchronously. Returns final state."""
    graph = get_graph()

    state = make_initial_state(nl_input=user_message)

    if is_xml_input(user_message):
        state["xml_description"] = user_message
        match = re.search(r'<module\s+id="([^"]+)"', user_message)
        if match:
            state["module_name"] = match.group(1)

    config = {"recursion_limit": 100}
    return graph.invoke(state, config)


# ──────────────────────────────────────────────────────────────
# FastAPI App
# ──────────────────────────────────────────────────────────────
app = FastAPI(title="COMBA-PROMPT v2 Verilog Pipeline API")


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
    # Extract user message (last user message)
    user_message = ""
    for msg in reversed(request.messages):
        if msg.role == "user":
            user_message = msg.content
            break

    if not user_message:
        user_message = request.messages[-1].content if request.messages else ""

    completion_id = f"chatcmpl-comba-{uuid.uuid4().hex[:12]}"

    if request.stream:
        # ── SSE Streaming: emit per-node events ──
        async def stream_generator():
            loop = asyncio.get_event_loop()
            final_state = {}

            try:
                # Run pipeline in thread pool to avoid blocking async
                def _stream_sync():
                    results = []
                    for node_name, state_update in run_pipeline_streaming(user_message):
                        results.append((node_name, state_update))
                    return results

                events = await loop.run_in_executor(_executor, _stream_sync)

                # Stream each node event
                for node_name, state_update in events:
                    final_state.update(state_update)
                    text = format_node_event(node_name, state_update, final_state)
                    if text:
                        yield make_sse_chunk(completion_id, text)
                        await asyncio.sleep(0.01)  # tiny delay for UI responsiveness

                # Send final formatted output
                final_output = format_final_output(final_state)
                if final_output:
                    yield make_sse_chunk(completion_id, final_output)

            except Exception as e:
                error_msg = f"\n❌ Pipeline error:\n```\n{str(e)}\n```\n"
                yield make_sse_chunk(completion_id, error_msg)

            # Finish
            yield make_sse_chunk(completion_id, "", finish_reason="stop")
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
        )

    # ── Non-streaming: run full pipeline, return formatted result ──
    try:
        loop = asyncio.get_event_loop()
        final = await loop.run_in_executor(_executor, run_pipeline_sync, user_message)

        # Build response text
        parts = []
        status = final.get("final_status", "unknown")
        emoji = "🎉" if status == "pass" else "❌"
        parts.append(f"{emoji} Pipeline completed: `{status}`\n")
        parts.append(format_final_output(final))
        response_text = "\n".join(parts)

    except Exception as e:
        response_text = f"❌ Error running COMBA pipeline:\n```\n{str(e)}\n```"

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
    """Health check endpoint."""
    return {
        "status": "ok",
        "model": COMBA_MODEL_NAME,
        "pipeline": "v2 (8-node, 6-route)",
    }


@app.get("/health/llm")
async def health_llm():
    """Detailed LLM health check."""
    try:
        graph = get_graph()
        if hasattr(_llm, 'health_check'):
            return _llm.health_check()
        return {"status": "ok", "llm_type": type(_llm).__name__}
    except Exception as e:
        return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)
