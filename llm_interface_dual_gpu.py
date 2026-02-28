#!/usr/bin/env python3
"""
VLLMInterface — Dual-GPU client for COMBA-PROMPT pipeline.

Optimized for 2× RTX 5880 Ada (48GB each):
  GPU 0 (:8000) → base model   → Process ⓪ + Agent 1 (generation)
  GPU 1 (:8001) → base + LoRA  → Process ① (correction/debugging)

Supports both modes:
  - Dual Instance: 2 vLLM servers on separate GPUs (recommended)
  - Single Instance: 1 vLLM server with LoRA hot-switching (simple)

Usage:
    # Dual instance (recommended for 2× GPU)
    llm = VLLMInterface(mode="dual")
    
    # Single instance (fallback / dev mode)
    llm = VLLMInterface(mode="single")
    
    # Generate Verilog (→ GPU 0)
    code = llm.generate_verilog(prompt)
    
    # Fix Verilog (→ GPU 1 with LoRA)
    fixed = llm.fix_verilog(edp_prompt)
"""

import os
import time
import logging
from typing import Optional, List, Dict, Any

from openai import OpenAI, APIConnectionError, APITimeoutError
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class VLLMInterface:

    def __init__(
        self,
        mode: str = None,  # "dual" or "single", auto-detect if None
        base_url: str = None,
        debugger_url: str = None,
        api_key: str = None,
        model_base: str = None,
        model_debugger: str = None,
        timeout: float = 120.0,
        max_retries: int = 3,
    ):
        """
        Initialize vLLM client.

        Args:
            mode: "dual" (2 servers) or "single" (1 server).
                  Auto-detects from env if None.
            base_url: URL for base model server (or single server)
            debugger_url: URL for debugger server (dual mode only)
        """
        self.api_key = api_key or os.getenv("LLM_API_KEY", "not-needed")
        self.model_base = model_base or os.getenv("LLM_MODEL_BASE", "qwen-base")
        self.model_debugger = model_debugger or os.getenv("LLM_MODEL_DEBUGGER", "debugger")
        self.timeout = timeout
        self.max_retries = max_retries

        # Auto-detect mode from env
        env_debugger_url = os.getenv("LLM_DEBUGGER_URL")
        if mode is None:
            mode = "dual" if env_debugger_url else "single"
        self.mode = mode

        # Setup clients
        self.base_url = base_url or os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")
        self.client_base = OpenAI(
            base_url=self.base_url, api_key=self.api_key, timeout=self.timeout
        )

        if self.mode == "dual":
            self.debugger_url = debugger_url or env_debugger_url or "http://localhost:8001/v1"
            self.client_debugger = OpenAI(
                base_url=self.debugger_url, api_key=self.api_key, timeout=self.timeout
            )
        else:
            self.debugger_url = self.base_url
            self.client_debugger = self.client_base

        logger.info(
            f"[VLLMInterface] mode={self.mode} | "
            f"base={self.base_url} ({self.model_base}) | "
            f"debugger={self.debugger_url} ({self.model_debugger})"
        )

    # ── Core Generation ──────────────────────────────────────

    def generate(
        self,
        messages: List[Dict[str, str]],
        mode: str = "base",
        temperature: float = 0.1,
        max_tokens: int = 2048,
        top_p: float = 0.95,
        stop: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Generate response, routing to correct GPU.

        Dual mode:
          - "base"     → GPU 0 (:8000) client, model=qwen-base
          - "debugger" → GPU 1 (:8001) client, model=debugger

        Single mode:
          - Both route to same server, different model= param
        """
        if mode == "debugger":
            client = self.client_debugger
            model = self.model_debugger
            gpu_label = "GPU1" if self.mode == "dual" else "GPU0+LoRA"
        else:
            client = self.client_base
            model = self.model_base
            gpu_label = "GPU0"

        for attempt in range(1, self.max_retries + 1):
            try:
                t0 = time.time()
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    stop=stop,
                )
                elapsed_ms = (time.time() - t0) * 1000

                text = resp.choices[0].message.content or ""
                result = {
                    "text": text,
                    "tokens_in": resp.usage.prompt_tokens if resp.usage else 0,
                    "tokens_out": resp.usage.completion_tokens if resp.usage else 0,
                    "time_ms": round(elapsed_ms, 1),
                    "model": model,
                    "gpu": gpu_label,
                    "finish_reason": resp.choices[0].finish_reason,
                }

                logger.info(
                    f"[{gpu_label}/{mode}] {result['tokens_out']} tok | "
                    f"{result['time_ms']}ms | {model}"
                )
                return result

            except (APIConnectionError, APITimeoutError) as e:
                logger.warning(
                    f"[{gpu_label}] Attempt {attempt}/{self.max_retries}: {e}"
                )
                if attempt == self.max_retries:
                    raise
                time.sleep(2 ** attempt)

    # ── Process ⓪ — Generation (→ GPU 0) ────────────────────

    def generate_verilog(
        self,
        prompt: str,
        system_prompt: str = "You are a professional Verilog designer. Generate the code only.",
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        """Process ⓪: Generate Verilog. Routes to GPU 0 (base model)."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        return self.generate(messages, mode="base", temperature=temperature, max_tokens=max_tokens)["text"]

    # ── Process ① — Correction (→ GPU 1 LoRA) ────────────────

    def fix_verilog(
        self,
        prompt: str,
        system_prompt: str = "You are a Verilog debugging expert. Fix the code based on the error information.",
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        """Process ①: Fix Verilog. Routes to GPU 1 (LoRA debugger)."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        return self.generate(messages, mode="debugger", temperature=temperature, max_tokens=max_tokens)["text"]

    # ── Agent 1 — NL → XML (→ GPU 0) ────────────────────────

    def convert_nl_to_xml(
        self,
        nl_input: str,
        converter_prompt_template: str,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        """Agent 1: NL → XML. Routes to GPU 0 (base model)."""
        prompt = converter_prompt_template.format(nl_input=nl_input)
        messages = [
            {"role": "system", "content": "You are a Verilog design specification expert."},
            {"role": "user", "content": prompt},
        ]
        return self.generate(messages, mode="base", temperature=temperature, max_tokens=max_tokens)["text"]

    # ── Health Check ─────────────────────────────────────────

    def health_check(self) -> Dict[str, Any]:
        """Check all vLLM server(s) health."""
        result = {"mode": self.mode, "servers": {}}

        for name, client, url in [
            ("generator", self.client_base, self.base_url),
            ("debugger", self.client_debugger, self.debugger_url),
        ]:
            try:
                models = client.models.list()
                model_ids = [m.id for m in models.data]
                result["servers"][name] = {
                    "status": "ok", "url": url, "models": model_ids
                }
            except Exception as e:
                result["servers"][name] = {
                    "status": "error", "url": url, "error": str(e)
                }

        return result

    def __repr__(self):
        return (
            f"VLLMInterface(mode={self.mode!r}, "
            f"base={self.base_url!r}, debugger={self.debugger_url!r})"
        )


# ── Standalone Test ──────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    llm = VLLMInterface()
    print(f"🔧 {llm}")
    print(f"📊 Health: {llm.health_check()}\n")

    # Test Process ⓪ → GPU 0
    print("=" * 60)
    print("🔵 Process ⓪ — Generation (GPU 0, base)")
    print("=" * 60)
    code = llm.generate_verilog(
        "Design a 4-bit synchronous counter with asynchronous reset and enable."
    )
    print(code[:500])

    # Test Process ① → GPU 1
    print("\n" + "=" * 60)
    print("🔴 Process ① — Correction (GPU 1, LoRA)")
    print("=" * 60)
    fixed = llm.fix_verilog(
        """The following Verilog module has a syntax error.

Current Code:
module counter(input clk, input rst, output [3:0] count);
reg [3:0] count;
always @(posedge clk)
    if (rst) count = 0;
    else count = count + 1;
endmodule

Compiler Error:
%Warning-BLKSEQ: counter.v:4: Blocking assignments (=) in sequential always block

Please fix the Verilog code."""
    )
    print(fixed[:500])

    print("\n✅ All tests passed — both GPUs responding!")
