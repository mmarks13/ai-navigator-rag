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
_DEBUG_CIT = os.getenv("CITATION_DEBUG", "0") in ("1", "true", "True")

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
        # Command: /retrieve <query> — retrieval-only debug view
        if message.content.strip().lower().startswith("/retrieve"):
            q = message.content.split(" ", 1)[1].strip() if " " in message.content else ""
            if not q:
                await cl.Message(content="Usage: /retrieve <query>").send()
                return
            results = kb.retrieve(q, top_k=5)
            if not results:
                await cl.Message(content="No retrieval results.").send()
                return
            lines = ["Top retrievals (no generation):"]
            for i, r in enumerate(results, start=1):
                # Extract snippet directly from the result structure
                snippet = ""
                content = r.get("content")
                if isinstance(content, dict) and content.get("text"):
                    snippet = str(content["text"])[:150] + ("…" if len(str(content["text"])) > 150 else "")
                elif isinstance(content, list) and content:
                    for seg in content:
                        if isinstance(seg, dict) and seg.get("text"):
                            snippet = str(seg["text"])[:150] + ("…" if len(str(seg["text"])) > 150 else "")
                            break

                # Extract URI from metadata and location
                uri = ""
                title = ""
                metadata = r.get("metadata", {})

                # Try metadata first
                for k, v in metadata.items():
                    if k in ["_source_uri", "source_uri", "uri", "url"] and isinstance(v, str):
                        uri = v
                        break
                    if k in ["title", "document_title"] and isinstance(v, str):
                        title = v

                # Fallback to location-based discovery
                if not uri:
                    loc = r.get("location") or {}
                    web = loc.get("webLocation") or {}
                    if web.get("url"):
                        uri = str(web["url"])
                    s3 = loc.get("s3Location") or {}
                    if not uri and s3.get("bucket") and s3.get("key"):
                        uri = f"s3://{s3['bucket']}/{s3['key']}"

                head = f"{i}. {title} — {snippet}" if title else f"{i}. {snippet or '(no snippet)'}"
                lines.append(head)
                lines.append(f"   {uri or '(no URI)'}")
            await cl.Message(content="\n".join(lines)).send()
            return

        answer, sources = kb.ask(message.content, system_prompt=system_prompt)

        # EXTENSIVE DEBUG: Show what we got from the API
        print(f"\n{'='*60}")
        print(f"DEBUG: API Response Analysis")
        print(f"{'='*60}")
        print(f"Answer type: {type(answer)}")
        print(f"Answer length: {len(answer) if answer else 0}")
        print(f"Answer preview (first 200 chars): {repr(answer[:200]) if answer else 'None'}")
        print(f"Sources type: {type(sources)}")
        print(f"Sources length: {len(sources) if sources else 0}")
        print(f"Sources raw: {sources}")
        print(f"{'='*60}")

        if sources:
            print(f"SOURCES DETAILS:")
            for i, source in enumerate(sources):
                print(f"  Source {i+1}:")
                print(f"    Type: {type(source)}")
                print(f"    Keys: {list(source.keys()) if isinstance(source, dict) else 'Not a dict'}")
                if isinstance(source, dict):
                    print(f"    URL: {repr(source.get('url'))}")
                    print(f"    Title: {repr(source.get('title'))}")
                    print(f"    Snippet length: {len(source.get('snippet', '')) if source.get('snippet') else 0}")
                    print(f"    Snippet preview: {repr(source.get('snippet', '')[:100])}")
                print(f"    Full source: {source}")

        # Create bibliography and enriched answer with [n] citations
        if sources:
            print(f"\nDEBUG: Starting citation processing...")
            print(f"Original answer contains these [n] patterns:")
            import re
            citation_matches = re.findall(r'\[\d+\]', answer)
            print(f"  Found citation patterns: {citation_matches}")

            # Replace [n] patterns in the answer with clickable markdown links
            enriched = answer
            citations_found = False

            print(f"DEBUG: Processing {len(sources)} sources...")
            for i, s in enumerate(sources, start=1):
                tag = f"[{i}]"
                print(f"  Looking for tag '{tag}' in answer...")
                if tag in enriched:
                    citations_found = True
                    print(f"    FOUND {tag} - will replace with markdown link")
                    # Create hover tooltip with source info
                    title_parts = []
                    if s.get("title"):
                        title_parts.append(f"Title: {s['title']}")
                    if s.get("snippet"):
                        snippet_preview = s["snippet"][:150] + ("…" if len(s["snippet"]) > 150 else "")
                        title_parts.append(f"Content: {snippet_preview}")
                    if s.get("url"):
                        title_parts.append(f"URL: {s['url']}")

                    tooltip = (" | ".join(title_parts) or "Source").replace('"', "'").replace("\n", " ")
                    href = s.get("url") or "#"

                    # Create bracketed citation link with hover tooltip
                    md_link = f"[[{i}]]({href} \"{tooltip}\")"
                    enriched = enriched.replace(tag, md_link)
                    print(f"    Replaced '{tag}' with '{md_link[:50]}...'")

                    # Also handle spacing between consecutive citations (e.g., [[2]][[3]] → [[2]] [[3]])
                    # This fixes the issue where citations appear as "23" instead of "2, 3"
                    import re
                    enriched = re.sub(r'\]\]\[\[', ']] [[', enriched)
                else:
                    print(f"    NOT FOUND {tag} in answer")

            print(f"DEBUG: Citations found in text: {citations_found}")
            print(f"DEBUG: Answer before enrichment: {repr(answer[:100])}...")
            print(f"DEBUG: Answer after enrichment: {repr(enriched[:100])}...")

            # If no citations were found in the text, add a note
            if not citations_found and len(sources) > 0:
                enriched += f"\n\n*Note: This answer is based on {len(sources)} source(s).*"
                print(f"DEBUG: Added fallback note about {len(sources)} sources")

            print(f"DEBUG: Final enriched content length: {len(enriched)}")
            print(f"DEBUG: Skipping long Sources section to keep response concise")
            await cl.Message(content=enriched).send()
        else:
            print(f"DEBUG: No sources returned, sending plain answer")
            await cl.Message(content=answer).send()

        # Optional debug
        if _DEBUG_CIT:
            print(f"[debug] sources count={len(sources)}")
            if sources:
                first = sources[0]
                print(f"[debug] first source url={first.get('url')!r} title={first.get('title')!r}")
            await cl.Message(
                content=f"(debug) found {len(sources)} sources\n(debug) test tooltip: [T](# \"This should show on hover\")"
            ).send()
    except Exception as e:
        await cl.Message(content=f"Error: {e}").send()