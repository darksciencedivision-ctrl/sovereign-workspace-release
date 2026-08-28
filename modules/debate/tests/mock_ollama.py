"""Deterministic Ollama-compatible stub used only by the offline smoke tests."""

import asyncio
import json
import os

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse


app = FastAPI()
MODELS = ["mock-alpha:latest", "mock-beta:latest"]
FAIL_TAGS = False
STREAM_MODE = "normal"
STREAM_CALLS = 0
CHAT_FAILURES = 0
ECHO_PAYLOAD = ""

VALID_MODES = {
    "normal",
    "reasoning",
    "slow_reasoning",
    "empty_once",
    "empty_always",
    "http_500",
    "malformed_ndjson",
    "partial_frame",
    "no_done",
    "stall_pause",
    "echo_control",
    "short_echo",
    "model_404",
}


@app.get("/api/tags")
async def tags():
    if FAIL_TAGS:
        return JSONResponse({"error": "simulated tags failure"}, status_code=503)
    return {"models": [{"name": name, "model": name, "size": 1_000_000} for name in MODELS]}


@app.post("/control/tags_failure/{enabled}")
async def tags_failure(enabled: int):
    global FAIL_TAGS
    FAIL_TAGS = bool(enabled)
    return {"ok": True, "enabled": FAIL_TAGS}


@app.post("/control/stream_mode/{mode}")
async def stream_mode(mode: str):
    global STREAM_MODE, STREAM_CALLS
    if mode not in VALID_MODES:
        return JSONResponse({"error": "invalid mode"}, status_code=400)
    STREAM_MODE = mode
    STREAM_CALLS = 0
    return {"ok": True, "mode": mode}


@app.post("/control/chat_failure/{count}")
async def chat_failure(count: int):
    global CHAT_FAILURES
    CHAT_FAILURES = max(0, count)
    return {"ok": True, "chat_failures": CHAT_FAILURES}


@app.post("/control/echo_payload")
async def echo_payload(request: Request):
    global ECHO_PAYLOAD
    body = await request.json()
    ECHO_PAYLOAD = str(body.get("text", ""))
    return {"ok": True}


@app.get("/control/metrics")
async def metrics():
    return {"stream_mode": STREAM_MODE, "stream_calls": STREAM_CALLS}


@app.get("/api/version")
async def version():
    return {"version": "mock-1.0"}


@app.post("/api/chat")
async def chat(request: Request):
    global STREAM_CALLS
    body = await request.json()
    if not body.get("stream"):
        await asyncio.sleep(0.5)
        return JSONResponse({
            "model": body.get("model"),
            "message": {"role": "assistant", "content": "Can deterministic tests expose orchestration races?"},
            "done": True,
        })

    global CHAT_FAILURES
    if CHAT_FAILURES > 0:
        CHAT_FAILURES -= 1
        return JSONResponse({"error": "simulated chat failure"}, status_code=500)
    if STREAM_MODE == "http_500":
        return JSONResponse({"error": "simulated 500"}, status_code=500)
    if STREAM_MODE == "model_404":
        return JSONResponse({"error": "model not found"}, status_code=404)

    STREAM_CALLS += 1
    call_number = STREAM_CALLS

    async def generate():
        if STREAM_MODE == "empty_always" or (
            STREAM_MODE == "empty_once" and call_number == 1
        ):
            yield json.dumps({"message": {"role": "assistant", "content": "<think>private only</think>"}, "done": False}) + "\n"
            yield json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}) + "\n"
            return
        if STREAM_MODE == "reasoning":
            fragments = (
                {"thinking": "separate private reasoning", "content": "<thi"},
                {"thinking": "must not leak", "content": "nk>private chain"},
                {"thinking": "must not leak", "content": "</th"},
                {"thinking": "must not leak", "content": "ink>Public answer after hidden reasoning."},
            )
            for fragment in fragments:
                await asyncio.sleep(0.005)
                yield json.dumps({"message": {"role": "assistant", **fragment}, "done": False}) + "\n"
            yield json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}) + "\n"
            return
        if STREAM_MODE == "echo_control":
            note = ""
            try:
                last_user = body.get("messages", [])[-1]["content"]
                for line in last_user.splitlines():
                    if line.startswith("OPERATOR NOTE:"):
                        note = line[len("OPERATOR NOTE:") :].strip()
                        break
            except Exception:
                note = ""
            if note:
                yield json.dumps({"message": {"role": "assistant", "content": note + "\n"}, "done": False}) + "\n"
            yield json.dumps({"message": {"role": "assistant", "content": "YOUR MOVE: challenge\n"}, "done": False}) + "\n"
            for index in range(3):
                yield json.dumps({"message": {"role": "assistant", "content": f"clean-token-{index:02d} "}, "done": False}) + "\n"
            yield json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}) + "\n"
            return
        if STREAM_MODE == "short_echo":
            yield json.dumps({"message": {"role": "assistant", "content": "I think the premise is incorrect."}, "done": False}) + "\n"
            yield json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}) + "\n"
            return
        if STREAM_MODE == "stall_pause":
            yield json.dumps({"message": {"role": "assistant", "content": "First words before the stall."}, "done": False}) + "\n"
            await asyncio.sleep(30)
            yield json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}) + "\n"
            return
        if STREAM_MODE == "no_done":
            yield json.dumps({"message": {"role": "assistant", "content": "Complete looking text without terminator."}, "done": False}) + "\n"
            return
        if STREAM_MODE == "malformed_ndjson":
            yield json.dumps({"message": {"role": "assistant", "content": "ok so far"}, "done": False}) + "\n"
            yield "NOT_JSON_LINE\n"
            yield json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}) + "\n"
            return
        if STREAM_MODE == "partial_frame":
            yield json.dumps({"message": {"role": "assistant", "content": "good start"}, "done": False}) + "\n"
            yield '{"message": {"content": "trunc'
            return
        if STREAM_MODE == "slow_reasoning":
            yield json.dumps({"message": {"role": "assistant", "thinking": "private", "content": "<think>private"}, "done": False}) + "\n"
            await asyncio.sleep(15)
            yield json.dumps({"message": {"role": "assistant", "content": "</think>Public after model load."}, "done": False}) + "\n"
            yield json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}) + "\n"
            return
        for index in range(40):
            await asyncio.sleep(0.005)
            token = f"substantive-token-{index:02d} "
            yield json.dumps({"message": {"role": "assistant", "content": token}, "done": False}) + "\n"
        yield json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("MOCK_OLLAMA_PORT", "11435")), log_level="warning")
