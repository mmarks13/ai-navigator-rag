import os, sys
import chainlit as cl
from pathlib import Path
from dotenv import load_dotenv
from typing import Any

# Ensure repo root is importable when Chainlit runs this as a script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config_utils import load_config
from app.rag import BedrockKBClient

load_dotenv(override=True)

CFG_PATH = os.getenv("APP_CONFIG", "config/config.yaml")
_RESOURCE: dict = {}

# Expose a simple health endpoint for App Runner/containers.
# We register it on Chainlit's underlying FastAPI app so `/healthz` returns 200.
try:
    from chainlit.server import app as _fastapi_app
    from fastapi.routing import APIRoute

    async def _healthz() -> Any:
        return {"status": "ok"}

    # Insert at the top to take precedence over Chainlit's catch-all route.
    _fastapi_app.router.routes.insert(
        0,
        APIRoute(
            path="/healthz",
            endpoint=_healthz,
            methods=["GET", "HEAD"],
            name="healthz",
            include_in_schema=False,
        ),
    )
except Exception as e:  # pragma: no cover - best-effort registration
    print(f"[init] ⚠️ Could not register /healthz endpoint: {e}")


def _init_resources():
    print("[init] 🔧 Initializing Bedrock KB client...")
    cfg = load_config(CFG_PATH)
    aws = cfg["aws"]

    kb_id = aws.get("knowledge_base_id")
    model_arn = aws.get("model_arn")
    inference_profile_arn = aws.get("inference_profile_arn")
    region = aws.get("region")
    if not (kb_id and region and (model_arn or inference_profile_arn)):
        raise RuntimeError("Missing AWS config: BEDROCK_KB_ID, AWS_DEFAULT_REGION, and either BEDROCK_MODEL_ARN or BEDROCK_INFERENCE_PROFILE_ARN")

    system_prompt = Path("prompts/system_prompt.md").read_text(encoding="utf-8")

    kb = BedrockKBClient(
        region=region,
        kb_id=kb_id,
        model_arn=model_arn,
        inference_profile_arn=inference_profile_arn,
        max_tokens=int(aws.get("max_tokens", 800)),
        temperature=float(aws.get("temperature", 0.2)),
        top_p=float(aws.get("top_p", 0.9)),
    )

    print("[init] ✅ Bedrock KB client ready")
    return {
        "cfg": cfg,
        "kb": kb,
        "system_prompt": system_prompt,
    }


@cl.on_chat_start
async def start():
    if not _RESOURCE:
        _RESOURCE.update(_init_resources())

    cfg = _RESOURCE["cfg"]
    aws = cfg["aws"]
    await cl.Message(content=f"Loaded `{CFG_PATH}`\nUsing Bedrock KB `{aws['knowledge_base_id']}` in {aws['region']}").send()
    welcome = cfg.get("ui", {}).get("welcome_message") or "Ready. Ask me about your knowledge base."
    await cl.Message(content=welcome).send()


@cl.on_message
async def main(message: cl.Message):
    kb: BedrockKBClient = _RESOURCE.get("kb")
    system_prompt: str = _RESOURCE.get("system_prompt")
    if not kb:
        await cl.Message(content="App not initialized.").send()
        return

    try:
        answer, _ = kb.ask(message.content, system_prompt=system_prompt)
        await cl.Message(content=answer).send()
    except Exception as e:
        await cl.Message(content=f"Error: {e}").send()