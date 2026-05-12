import os
import json
import time
import uuid
import secrets
from typing import Any, Dict, List

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()


def load_env_file(env_path: str) -> None:
    """
    轻量读取 .env 文件，不依赖 python-dotenv。
    已存在的环境变量不会被覆盖。
    """
    if not env_path or not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if line.startswith("export "):
                line = line[len("export "):].strip()

            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            if not key:
                continue

            if (
                len(value) >= 2
                and (
                    (value[0] == value[-1] == '"')
                    or (value[0] == value[-1] == "'")
                )
            ):
                value = value[1:-1]

            os.environ.setdefault(key, value)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")


# 主动读取 mcp-openai-bridge 的 .env
MCP_OPENAI_BRIDGE_ENV = os.getenv(
    "MCP_OPENAI_BRIDGE_ENV",
    "/home/segzix/Projects/codex-responses-bridge/.env",
)

load_env_file(MCP_OPENAI_BRIDGE_ENV)


# 默认 GPT / Codex 上游。
# 注意：不要从 CODEX_BASE_URL 读取，因为 mcp-openai-bridge 里的 CODEX_BASE_URL 通常是 http://127.0.0.1:9010/v1，
# 如果这里读取 CODEX_BASE_URL，会导致 bridge 自己转发给自己，形成循环。
UPSTREAM_BASE_URL = os.getenv(
    "UPSTREAM_BASE_URL",
    "https://49.232.172.202/v1",
).rstrip("/")

# GPT / Codex 第三方平台真实 key。
# 这个 key 只用于 bridge 访问第三方平台，不用于本地客户端访问 bridge。
UPSTREAM_API_KEY = os.getenv("CODEX_API_KEY")

VERIFY_SSL = env_bool("VERIFY_SSL", False)


# Claude 上游。
# 注意：不要从 CLAUDE_BASE_URL 读取，因为 mcp-openai-bridge 里的 CLAUDE_BASE_URL 通常是 http://127.0.0.1:9010/v1，
# 如果这里读取 CLAUDE_BASE_URL，会导致 bridge 自己转发给自己，形成循环。
UPSTREAM_CLAUDE_BASE_URL = os.getenv(
    "UPSTREAM_CLAUDE_BASE_URL",
    "https://49.232.172.202/v1",
).rstrip("/")

# Claude 第三方平台真实 key。
# 这个 key 只用于 bridge 访问第三方平台，不用于本地客户端访问 bridge。
UPSTREAM_CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

UPSTREAM_CLAUDE_VERIFY_SSL = env_bool("UPSTREAM_CLAUDE_VERIFY_SSL", False)


# 本地客户端访问 bridge 的 key。
# OpenCode / Codex / curl 访问 http://127.0.0.1:9010/v1 时使用这个 key。
# 这个 key 不会转发给第三方平台。
LOCAL_BRIDGE_API_KEY = os.getenv("LOCAL_BRIDGE_API_KEY")


def verify_local_bridge_key(request: Request) -> None:
    """
    校验访问本地 uvicorn bridge 的客户端 key。

    客户端访问本地 bridge：
        Authorization: Bearer LOCAL_BRIDGE_API_KEY

    bridge 访问第三方平台：
        Authorization: Bearer CODEX_API_KEY 或 CLAUDE_API_KEY

    两类 key 必须分开。
    """
    if not LOCAL_BRIDGE_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="LOCAL_BRIDGE_API_KEY is not configured",
        )

    auth = request.headers.get("authorization") or ""

    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing local bridge bearer token",
        )

    token = auth[len("Bearer "):].strip()

    if not secrets.compare_digest(token, LOCAL_BRIDGE_API_KEY):
        raise HTTPException(
            status_code=401,
            detail="Invalid local bridge bearer token",
        )


GPT_MODELS = {
    "gpt-5.5",
    "gpt-5.4-mini",
}


CLAUDE_MODELS = {
    "claude-haiku-4-5-20251001",
    "claude-opus-4-6",
    "claude-opus-4-7",
    "claude-sonnet-4-6",
}


SUPPORTED_MODELS = GPT_MODELS | CLAUDE_MODELS


def is_gpt_model(model: str) -> bool:
    return bool(model) and model in GPT_MODELS


def is_claude_model(model: str) -> bool:
    return bool(model) and model in CLAUDE_MODELS


def select_chat_upstream(model: str) -> Dict[str, Any]:
    """
    根据 model 选择上游。
    只有 GPT_MODELS 或 CLAUDE_MODELS 中显式声明的模型才允许路由；
    未声明模型直接报错，避免误把 DeepSeek/Qwen/随机模型转发到默认上游。
    """
    if is_claude_model(model):
        return {
            "provider": "claude",
            "base_url": UPSTREAM_CLAUDE_BASE_URL,
            "api_key": UPSTREAM_CLAUDE_API_KEY,
            "verify_ssl": UPSTREAM_CLAUDE_VERIFY_SSL,
        }

    if is_gpt_model(model):
        return {
            "provider": "default",
            "base_url": UPSTREAM_BASE_URL,
            "api_key": UPSTREAM_API_KEY,
            "verify_ssl": VERIFY_SSL,
        }

    raise HTTPException(
        status_code=400,
        detail=(
            f"Unsupported model for local bridge: {model}. "
            f"Allowed models: {', '.join(sorted(SUPPORTED_MODELS))}"
        ),
    )


def content_to_text(content: Any) -> str:
    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if "text" in item:
                    parts.append(str(item["text"]))
                elif "content" in item:
                    parts.append(str(item["content"]))
        return "\n".join(parts)

    return str(content)


def responses_input_to_messages(input_data: Any) -> List[Dict[str, str]]:
    if isinstance(input_data, str):
        return [{"role": "user", "content": input_data}]

    messages = []

    if isinstance(input_data, list):
        for item in input_data:
            if not isinstance(item, dict):
                messages.append({"role": "user", "content": str(item)})
                continue

            role = item.get("role", "user")
            if role == "developer":
                role = "system"
            if role not in ("system", "user", "assistant"):
                role = "user"

            text = content_to_text(item.get("content", ""))
            if text.strip():
                messages.append({"role": role, "content": text})

    if not messages:
        messages = [{"role": "user", "content": json.dumps(input_data, ensure_ascii=False)}]

    return messages


def response_object(
    response_id: str,
    model: str,
    text: str,
    usage: Dict[str, Any] | None = None,
):
    return {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": model,
        "output": [
            {
                "id": "msg_" + uuid.uuid4().hex,
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": text,
                        "annotations": [],
                    }
                ],
            }
        ],
        "output_text": text,
        "usage": usage or {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        },
    }


def sse(event_type: str, data: Dict[str, Any]) -> str:
    data.setdefault("type", event_type)
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/")
async def root():
    return {
        "ok": True,
        "service": "codex-responses-bridge",
        "env_file": MCP_OPENAI_BRIDGE_ENV,
        "local_auth_enabled": bool(LOCAL_BRIDGE_API_KEY),
    }


@app.get("/v1/models")
async def models(request: Request):
    verify_local_bridge_key(request)

    result = {
        "object": "list",
        "data": [],
    }

    existing_ids = set()

    if UPSTREAM_API_KEY:
        headers = {"Authorization": f"Bearer {UPSTREAM_API_KEY}"}

        try:
            async with httpx.AsyncClient(
                verify=VERIFY_SSL,
                timeout=60.0,
                trust_env=False,
            ) as client:
                r = await client.get(f"{UPSTREAM_BASE_URL}/models", headers=headers)

            if r.status_code < 400:
                upstream = r.json()
                for item in upstream.get("data", []):
                    model_id = item.get("id")
                    if model_id in GPT_MODELS and model_id not in existing_ids:
                        result["data"].append(item)
                        existing_ids.add(model_id)
        except Exception as e:
            print("[models upstream error]", repr(e), flush=True)

    # 只对外暴露本地 bridge 明确允许路由的模型，避免客户端选到未白名单模型。
    for model_id in sorted(SUPPORTED_MODELS):
        if model_id not in existing_ids:
            result["data"].append({
                "id": model_id,
                "object": "model",
                "type": "model",
                "display_name": model_id,
                "created_at": "2024-01-01T00:00:00Z",
            })
            existing_ids.add(model_id)

    return JSONResponse(content=result)


@app.get("/debug/env")
async def debug_env(request: Request):
    """
    调试用：只显示 key 是否存在，不返回真实 key。
    """
    verify_local_bridge_key(request)

    return {
        "MCP_OPENAI_BRIDGE_ENV": MCP_OPENAI_BRIDGE_ENV,
        "UPSTREAM_BASE_URL": UPSTREAM_BASE_URL,
        "UPSTREAM_API_KEY": bool(UPSTREAM_API_KEY),
        "VERIFY_SSL": VERIFY_SSL,
        "UPSTREAM_CLAUDE_BASE_URL": UPSTREAM_CLAUDE_BASE_URL,
        "UPSTREAM_CLAUDE_API_KEY": bool(UPSTREAM_CLAUDE_API_KEY),
        "UPSTREAM_CLAUDE_VERIFY_SSL": UPSTREAM_CLAUDE_VERIFY_SSL,
        "LOCAL_BRIDGE_API_KEY": bool(LOCAL_BRIDGE_API_KEY),
    }


@app.post("/v1/responses")
async def responses(request: Request):
    verify_local_bridge_key(request)

    body = await request.json()

    model = body.get("model", "gpt-5.5")
    stream = bool(body.get("stream", False))

    chat_payload = {
        "model": model,
        "messages": responses_input_to_messages(body.get("input", "")),
        "stream": stream,
    }

    if "temperature" in body:
        chat_payload["temperature"] = body["temperature"]
    if "top_p" in body:
        chat_payload["top_p"] = body["top_p"]
    if "max_output_tokens" in body:
        chat_payload["max_tokens"] = body["max_output_tokens"]
    if "max_tokens" in body:
        chat_payload["max_tokens"] = body["max_tokens"]

    upstream_route = select_chat_upstream(model)

    if not upstream_route["api_key"]:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": f"Missing upstream API key for provider: {upstream_route['provider']}",
                    "type": "bridge_config_error",
                }
            },
        )

    headers = {
        "Authorization": f"Bearer {upstream_route['api_key']}",
        "Content-Type": "application/json",
    }

    upstream_chat_url = f"{upstream_route['base_url']}/chat/completions"
    response_id = "resp_" + uuid.uuid4().hex

    if not stream:
        async with httpx.AsyncClient(
            verify=upstream_route["verify_ssl"],
            timeout=None,
            trust_env=False,
        ) as client:
            r = await client.post(
                upstream_chat_url,
                headers=headers,
                json=chat_payload,
            )

        print(
            "[responses upstream]",
            "provider=", upstream_route["provider"],
            "model=", model,
            "url=", upstream_chat_url,
            "status=", r.status_code,
            "body=", r.text[:300],
            flush=True,
        )

        try:
            upstream_response = r.json()
        except Exception:
            return JSONResponse(
                status_code=502,
                content={
                    "error": {
                        "message": "Upstream returned non-JSON",
                        "type": "upstream_non_json",
                        "raw": r.text,
                    }
                },
            )

        if r.status_code >= 400:
            return JSONResponse(status_code=r.status_code, content=upstream_response)

        text = upstream_response.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = upstream_response.get("usage")

        return JSONResponse(content=response_object(response_id, model, text, usage))

    async def event_generator():
        output_item_id = "msg_" + uuid.uuid4().hex
        full_text = ""

        yield sse("response.created", {
            "response": {
                "id": response_id,
                "object": "response",
                "created_at": int(time.time()),
                "status": "in_progress",
                "model": model,
                "output": [],
            }
        })

        yield sse("response.output_item.added", {
            "response_id": response_id,
            "output_index": 0,
            "item": {
                "id": output_item_id,
                "type": "message",
                "status": "in_progress",
                "role": "assistant",
                "content": [],
            },
        })

        yield sse("response.content_part.added", {
            "response_id": response_id,
            "item_id": output_item_id,
            "output_index": 0,
            "content_index": 0,
            "part": {
                "type": "output_text",
                "text": "",
                "annotations": [],
            },
        })

        try:
            async with httpx.AsyncClient(
                verify=upstream_route["verify_ssl"],
                timeout=None,
                trust_env=False,
            ) as client:
                async with client.stream(
                    "POST",
                    upstream_chat_url,
                    headers=headers,
                    json=chat_payload,
                ) as r:
                    print(
                        "[responses stream upstream]",
                        "provider=", upstream_route["provider"],
                        "model=", model,
                        "url=", upstream_chat_url,
                        "status=", r.status_code,
                        flush=True,
                    )

                    if r.status_code >= 400:
                        err = await r.aread()
                        yield sse("error", {
                            "error": {
                                "message": err.decode("utf-8", errors="ignore"),
                                "type": "upstream_error",
                            }
                        })
                        return

                    async for line in r.aiter_lines():
                        if not line:
                            continue

                        raw = line.strip()
                        if raw.startswith("data:"):
                            raw = raw[len("data:"):].strip()

                        if raw == "[DONE]":
                            break

                        try:
                            chunk = json.loads(raw)
                        except Exception:
                            continue

                        delta = ""

                        try:
                            delta = chunk["choices"][0].get("delta", {}).get("content") or ""
                        except Exception:
                            pass

                        if not delta:
                            try:
                                delta = chunk["choices"][0].get("message", {}).get("content") or ""
                            except Exception:
                                pass

                        if delta:
                            full_text += delta
                            yield sse("response.output_text.delta", {
                                "response_id": response_id,
                                "item_id": output_item_id,
                                "output_index": 0,
                                "content_index": 0,
                                "delta": delta,
                            })

        except Exception as e:
            yield sse("error", {
                "error": {
                    "message": str(e),
                    "type": "bridge_error",
                }
            })
            return

        yield sse("response.output_text.done", {
            "response_id": response_id,
            "item_id": output_item_id,
            "output_index": 0,
            "content_index": 0,
            "text": full_text,
        })

        yield sse("response.output_item.done", {
            "response_id": response_id,
            "output_index": 0,
            "item": {
                "id": output_item_id,
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": full_text,
                        "annotations": [],
                    }
                ],
            },
        })

        yield sse("response.completed", {
            "response": response_object(response_id, model, full_text)
        })

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    verify_local_bridge_key(request)

    body: Dict[str, Any] = await request.json()

    model = body.get("model")
    if not model:
        raise HTTPException(status_code=400, detail="Missing model")

    upstream_route = select_chat_upstream(model)

    if not upstream_route["api_key"]:
        raise HTTPException(
            status_code=500,
            detail=f"Missing upstream API key for provider: {upstream_route['provider']}",
        )

    url = f"{upstream_route['base_url']}/chat/completions"

    headers = {
        "Authorization": f"Bearer {upstream_route['api_key']}",
        "Content-Type": "application/json",
    }

    stream = bool(body.get("stream", False))

    if not stream:
        async with httpx.AsyncClient(
            verify=upstream_route["verify_ssl"],
            timeout=None,
            trust_env=False,
        ) as client:
            try:
                r = await client.post(url, headers=headers, json=body)
            except httpx.ConnectError as e:
                raise HTTPException(
                    status_code=502,
                    detail=f"Upstream connect error: {str(e)}",
                )
            except httpx.ReadTimeout:
                raise HTTPException(
                    status_code=504,
                    detail="Upstream read timeout",
                )
            except httpx.HTTPError as e:
                raise HTTPException(
                    status_code=502,
                    detail=f"Upstream HTTP error: {str(e)}",
                )

        print(
            "[chat upstream]",
            "provider=", upstream_route["provider"],
            "model=", model,
            "url=", url,
            "status=", r.status_code,
            "body=", r.text[:300],
            flush=True,
        )

        try:
            data = r.json()
        except Exception:
            return JSONResponse(
                status_code=502,
                content={
                    "error": {
                        "message": "Upstream returned non-JSON",
                        "type": "upstream_non_json",
                        "raw": r.text,
                    }
                },
            )

        return JSONResponse(status_code=r.status_code, content=data)

    async def stream_generator():
        async with httpx.AsyncClient(
            verify=upstream_route["verify_ssl"],
            timeout=None,
            trust_env=False,
        ) as client:
            try:
                async with client.stream(
                    "POST",
                    url,
                    headers=headers,
                    json=body,
                ) as r:
                    print(
                        "[chat stream upstream]",
                        "provider=", upstream_route["provider"],
                        "model=", model,
                        "url=", url,
                        "status=", r.status_code,
                        flush=True,
                    )

                    if r.status_code >= 400:
                        err = await r.aread()
                        yield json.dumps({
                            "error": {
                                "message": err.decode("utf-8", errors="ignore"),
                                "type": "upstream_error",
                            }
                        }, ensure_ascii=False)
                        return

                    async for chunk in r.aiter_bytes():
                        if chunk:
                            yield chunk

            except Exception as e:
                yield json.dumps({
                    "error": {
                        "message": str(e),
                        "type": "bridge_error",
                    }
                }, ensure_ascii=False)

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
    )