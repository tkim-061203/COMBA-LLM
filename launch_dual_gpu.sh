#!/bin/bash
# ============================================================
# launch_dual_gpu.sh — 2× RTX 5880 Ada Deployment
# ============================================================
#
# Strategy: 2 vLLM instances, 1 per GPU
#   GPU 0 (port 8000): Base model → Process ⓪ + Agent 1
#   GPU 1 (port 8001): Base + LoRA → Process ① (Correcter)
#
# Tại sao KHÔNG dùng TP=2?
#   - Qwen 7B bf16 ≈ 14GB → 1 GPU 48GB dư sức
#   - PCIe 4.0 giữa 2 GPU (không NVLink) → TP gây thêm latency
#   - Dual instance cho phép generation + debugging đồng thời
#
# Usage:
#   ./launch_dual_gpu.sh                      # default
#   ./launch_dual_gpu.sh --adapter-path /path  # custom adapter
#   ./launch_dual_gpu.sh --stop                # stop cả 2 servers
#   ./launch_dual_gpu.sh --status              # check status

set -euo pipefail

# ── Config ──
BASE_MODEL="${BASE_MODEL:-Qwen/Qwen2.5-Coder-7B-Instruct}"
ADAPTER_PATH="${ADAPTER_PATH:-./qwen_debugger_final_lora}"
PORT_GEN=8000     # Generator port
PORT_DBG=8001     # Debugger port
MAX_MODEL_LEN=16384  # 16K context — Verilog code dài
GPU_MEM=0.92      # 92% of 48GB = ~44GB usable
DTYPE="bfloat16"
MAX_LORA_RANK=64
LOG_DIR="./logs"

# ── Parse Args ──
ACTION="start"
while [[ $# -gt 0 ]]; do
    case $1 in
        --adapter-path)  ADAPTER_PATH="$2"; shift 2 ;;
        --base-model)    BASE_MODEL="$2"; shift 2 ;;
        --stop)          ACTION="stop"; shift ;;
        --status)        ACTION="status"; shift ;;
        --restart)       ACTION="restart"; shift ;;
        -h|--help)
            echo "Usage: $0 [--adapter-path PATH] [--stop] [--status] [--restart]"
            exit 0 ;;
        *) echo "Unknown: $1"; exit 1 ;;
    esac
done

# ── Functions ──

check_gpu() {
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║    2× RTX 5880 Ada — COMBA-PROMPT Dual Instance        ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo ""

    if ! command -v nvidia-smi &> /dev/null; then
        echo "❌ nvidia-smi not found"; exit 1
    fi

    GPU_COUNT=$(nvidia-smi --query-gpu=name --format=csv,noheader | wc -l)
    if [[ $GPU_COUNT -lt 2 ]]; then
        echo "⚠️  Only $GPU_COUNT GPU(s) detected. Dual instance needs 2 GPUs."
        echo "   Falling back to single instance mode..."
        echo ""
        single_instance
        exit 0
    fi

    echo "🖥️  GPU Configuration:"
    nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader | while read line; do
        echo "   $line"
    done
    echo ""
}

stop_servers() {
    echo "🛑 Stopping vLLM servers..."
    
    # Kill by port
    for PORT in $PORT_GEN $PORT_DBG; do
        PID=$(lsof -ti:$PORT 2>/dev/null || true)
        if [[ -n "$PID" ]]; then
            kill $PID 2>/dev/null && echo "   Killed process $PID on port $PORT" || true
        fi
    done

    # Also kill by process name
    pkill -f "vllm.entrypoints.openai.api_server" 2>/dev/null && echo "   Killed vLLM processes" || true
    
    sleep 2
    echo "✅ All servers stopped"
}

check_status() {
    echo "📊 Server Status:"
    for PORT in $PORT_GEN $PORT_DBG; do
        LABEL="Generator"
        [[ $PORT == $PORT_DBG ]] && LABEL="Debugger "
        
        if curl -s "http://localhost:$PORT/health" > /dev/null 2>&1; then
            MODELS=$(curl -s "http://localhost:$PORT/v1/models" 2>/dev/null | python3 -c "import sys,json; [print(f'    model: {m[\"id\"]}') for m in json.load(sys.stdin)['data']]" 2>/dev/null || echo "    (unable to list models)")
            echo "   ✅ $LABEL (:$PORT) — RUNNING"
            echo "$MODELS"
        else
            echo "   ❌ $LABEL (:$PORT) — DOWN"
        fi
    done
}

single_instance() {
    echo "🔧 Single Instance Mode (1 GPU only)"
    echo "   GPU 0: Base + LoRA → all processes"
    echo ""
    
    mkdir -p $LOG_DIR
    
    CUDA_VISIBLE_DEVICES=0 python -m vllm.entrypoints.openai.api_server \
        --model $BASE_MODEL \
        --served-model-name qwen-base \
        --enable-lora \
        --lora-modules debugger=$ADAPTER_PATH \
        --max-lora-rank $MAX_LORA_RANK \
        --dtype $DTYPE \
        --max-model-len $MAX_MODEL_LEN \
        --gpu-memory-utilization $GPU_MEM \
        --port $PORT_GEN \
        --host 0.0.0.0 \
        --trust-remote-code \
        2>&1 | tee $LOG_DIR/vllm_single.log
}

start_dual() {
    # Validate adapter
    if [[ ! -d "$ADAPTER_PATH" ]]; then
        echo "❌ Adapter not found: $ADAPTER_PATH"
        echo "   Run stage3_ensemble_merge.py first."
        exit 1
    fi

    RANK=$(python3 -c "import json; print(json.load(open('$ADAPTER_PATH/adapter_config.json'))['r'])" 2>/dev/null || echo "?")
    
    echo "📋 Configuration:"
    echo "   Base Model:  $BASE_MODEL"
    echo "   LoRA Adapter: $ADAPTER_PATH (rank=$RANK)"
    echo "   Context:     $MAX_MODEL_LEN tokens"
    echo "   GPU Memory:  ${GPU_MEM} utilization (≈$((48 * ${GPU_MEM%.*} / 1))GB per GPU)"
    echo ""
    echo "📡 Endpoints:"
    echo "   GPU 0 → http://localhost:$PORT_GEN/v1  model=\"qwen-base\"    (Process ⓪ + Agent 1)"
    echo "   GPU 1 → http://localhost:$PORT_DBG/v1  model=\"debugger\"     (Process ① LoRA)"
    echo ""

    mkdir -p $LOG_DIR

    # ── GPU 0: Generator (base only, no LoRA) ──
    echo "🔵 Starting Generator on GPU 0 (port $PORT_GEN)..."
    CUDA_VISIBLE_DEVICES=0 nohup python -m vllm.entrypoints.openai.api_server \
        --model $BASE_MODEL \
        --served-model-name qwen-base \
        --dtype $DTYPE \
        --max-model-len $MAX_MODEL_LEN \
        --gpu-memory-utilization $GPU_MEM \
        --port $PORT_GEN \
        --host 0.0.0.0 \
        --trust-remote-code \
        > $LOG_DIR/vllm_gpu0_generator.log 2>&1 &
    
    PID_GEN=$!
    echo "   PID: $PID_GEN → log: $LOG_DIR/vllm_gpu0_generator.log"

    # ── GPU 1: Debugger (base + LoRA) ──
    echo "🔴 Starting Debugger on GPU 1 (port $PORT_DBG)..."
    CUDA_VISIBLE_DEVICES=1 nohup python -m vllm.entrypoints.openai.api_server \
        --model $BASE_MODEL \
        --served-model-name qwen-base \
        --enable-lora \
        --lora-modules debugger=$ADAPTER_PATH \
        --max-lora-rank $MAX_LORA_RANK \
        --dtype $DTYPE \
        --max-model-len $MAX_MODEL_LEN \
        --gpu-memory-utilization $GPU_MEM \
        --port $PORT_DBG \
        --host 0.0.0.0 \
        --trust-remote-code \
        > $LOG_DIR/vllm_gpu1_debugger.log 2>&1 &

    PID_DBG=$!
    echo "   PID: $PID_DBG → log: $LOG_DIR/vllm_gpu1_debugger.log"

    # ── Wait for servers ──
    echo ""
    echo "⏳ Waiting for servers to start (model loading ~30-60s)..."
    
    for PORT in $PORT_GEN $PORT_DBG; do
        LABEL="Generator"
        [[ $PORT == $PORT_DBG ]] && LABEL="Debugger"
        
        for i in $(seq 1 120); do
            if curl -s "http://localhost:$PORT/health" > /dev/null 2>&1; then
                echo "   ✅ $LABEL (:$PORT) ready! (${i}s)"
                break
            fi
            if [[ $i -eq 120 ]]; then
                echo "   ⚠️  $LABEL (:$PORT) not ready after 120s — check logs"
            fi
            sleep 1
        done
    done

    echo ""
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║  ✅ Both servers running!                               ║"
    echo "║                                                         ║"
    echo "║  Generator: http://localhost:$PORT_GEN/v1               ║"
    echo "║  Debugger:  http://localhost:$PORT_DBG/v1               ║"
    echo "║                                                         ║"
    echo "║  Stop:    ./launch_dual_gpu.sh --stop                   ║"
    echo "║  Status:  ./launch_dual_gpu.sh --status                 ║"
    echo "║  Logs:    tail -f $LOG_DIR/vllm_gpu*.log          ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo ""

    # ── Quick smoke test ──
    echo "🧪 Quick smoke test..."
    
    # Test Generator
    RESP=$(curl -s "http://localhost:$PORT_GEN/v1/models" 2>/dev/null || echo "FAIL")
    if echo "$RESP" | grep -q "qwen-base"; then
        echo "   ✅ GPU 0 Generator: qwen-base ready"
    else
        echo "   ❌ GPU 0 Generator: FAILED"
    fi

    # Test Debugger
    RESP=$(curl -s "http://localhost:$PORT_DBG/v1/models" 2>/dev/null || echo "FAIL")
    if echo "$RESP" | grep -q "debugger"; then
        echo "   ✅ GPU 1 Debugger: debugger (LoRA) ready"
    else
        echo "   ❌ GPU 1 Debugger: FAILED"
    fi

    echo ""
    echo "🎯 VRAM Usage (expected):"
    echo "   GPU 0: ~14GB model + ~30GB KV cache = ~44GB / 48GB"
    echo "   GPU 1: ~14GB model + ~0.1GB LoRA + ~30GB KV cache = ~44GB / 48GB"
    echo ""
    nvidia-smi --query-gpu=index,memory.used,memory.free,utilization.gpu --format=csv,noheader 2>/dev/null || true
}

# ── Main ──
case $ACTION in
    start)
        check_gpu
        start_dual
        ;;
    stop)
        stop_servers
        ;;
    status)
        check_status
        echo ""
        nvidia-smi --query-gpu=index,name,memory.used,memory.free,utilization.gpu --format=csv,noheader 2>/dev/null || true
        ;;
    restart)
        stop_servers
        sleep 3
        check_gpu
        start_dual
        ;;
esac
