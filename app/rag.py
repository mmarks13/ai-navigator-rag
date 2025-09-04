import boto3
import re
from typing import List, Tuple, Optional, Dict, Any


URL_LIKE_KEYS = {
    "_source_uri",
    "x-amz-kendra-document-id",
    "x-amz-bedrock-source-uri",
    "source_uri",
    "source-url",
    "document_uri",
    "url",
    "uri",
    "link",
    "href",
}


def _first_url_from_metadata(md: dict) -> str | None:
    """Extract URL from metadata using common keys or heuristic scanning."""
    # Direct lookups by common keys
    for k in URL_LIKE_KEYS:
        v = md.get(k)
        if isinstance(v, str) and v.startswith(("http://", "https://")):
            return v
    # Heuristic: scan any string value for an http(s) URL
    for v in md.values():
        if isinstance(v, str):
            m = re.search(r"https?://\S+", v)
            if m:
                return m.group(0)
    return None


def _ref_url(ref: dict) -> str:
    """Extract URL from a reference using all known location shapes."""
    loc = ref.get("location") or {}
    # Try all known location shapes first
    return (
        ((loc.get("webLocation") or {}).get("url")) or
        ((loc.get("sharePointLocation") or {}).get("url")) or
        ((loc.get("confluenceLocation") or {}).get("url")) or
        ((loc.get("salesforceLocation") or {}).get("url")) or
        ((loc.get("kendraDocumentLocation") or {}).get("uri")) or
        ((loc.get("s3Location") or {}).get("uri")) or
        # Fallback: pull from metadata (where Kendra usually puts the original URL)
        _first_url_from_metadata(ref.get("metadata") or {}) or
        ""
    )


class BedrockKBClient:
    """Bedrock Knowledge Base client with proper citation handling."""

    def __init__(self, region: str, kb_id: str, model_arn: Optional[str] = None, inference_profile_arn: Optional[str] = None, max_tokens: int = 800, temperature: float = 0.2, top_p: float = 0.9):
        self.region = region
        self.client = boto3.client("bedrock-agent-runtime", region_name=region)
        self.kb_id = kb_id
        self.model_arn = model_arn
        self.inference_profile_arn = inference_profile_arn
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p

    def ask(self, query: str, system_prompt: str = None, number_of_results: int = 10) -> Tuple[str, List[Dict[str, Any]]]:
        """Ask the knowledge base using the working approach: retrieve then generate."""

        print(f"\n{'='*50}")
        print(f"RAG.PY DEBUG: ask() method called with WORKING APPROACH")
        print(f"Query: {repr(query)}")
        print(f"System prompt provided: {system_prompt is not None}")
        print(f"Number of results: {number_of_results}")
        print(f"{'='*50}")

        # Step 1: Retrieve relevant documents using the working retrieve method
        print(f"RAG DEBUG: Step 1 - Calling retrieve() method...")
        retrieval_results = self.retrieve(query, top_k=number_of_results)

        print(f"RAG DEBUG: Retrieved {len(retrieval_results) if retrieval_results else 0} results")
        if not retrieval_results:
            return "I don't have any relevant information to answer this question.", []

        # Step 2: Extract information and build sources
        print(f"RAG DEBUG: Step 2 - Processing retrieval results...")
        sources = []
        seen = set()
        search_results_text = []

        for i, result in enumerate(retrieval_results, start=1):
            print(f"  Processing result {i}: {result}")

            # Extract URL using our comprehensive approach
            url = _ref_url(result)
            print(f"    Extracted URL: {repr(url)}")

            # Extract snippet
            snippet = ""
            content = result.get("content", {})
            if isinstance(content, dict) and content.get("text"):
                snippet = str(content["text"])[:300] + ("…" if len(str(content["text"])) > 300 else "")
                print(f"    Extracted snippet from dict: {len(snippet)} chars")
            elif isinstance(content, list) and content:
                for seg in content:
                    if isinstance(seg, dict) and seg.get("text"):
                        snippet = str(seg["text"])[:300] + ("…" if len(str(seg["text"])) > 300 else "")
                        print(f"    Extracted snippet from list: {len(snippet)} chars")
                        break

            # Extract title from metadata
            title = ""
            metadata = result.get("metadata", {})
            for k in ["title", "document_title", "x-amz-kendra-document-title"]:
                if k in metadata and metadata[k]:
                    title = str(metadata[k])
                    print(f"    Extracted title: {repr(title)}")
                    break

            # Avoid duplicate sources
            source_key = (url, snippet[:100])  # Use URL + snippet prefix as key
            if source_key not in seen:
                seen.add(source_key)
                source_obj = {
                    "url": url,
                    "snippet": snippet,
                    "title": title
                }
                sources.append(source_obj)
                print(f"    Added source {len(sources)}: {source_obj}")

                # Build search results text for prompt
                search_results_text.append(f"[{len(sources)}] {title or 'Source'}\n{snippet}\nURL: {url}\n")
            else:
                print(f"    Skipped duplicate source")

        print(f"RAG DEBUG: Built {len(sources)} unique sources")
        print(f"RAG DEBUG: Search results text length: {len(''.join(search_results_text))}")

        # Step 3: Generate answer using the model directly
        print(f"RAG DEBUG: Step 3 - Generating answer...")

        if system_prompt:
            formatted_results = "\n".join(search_results_text)
            prompt = system_prompt.replace("$search_results$", formatted_results).replace("$query$", query)
            print(f"RAG DEBUG: Using system prompt, search results length: {len(formatted_results)}")
            print(f"RAG DEBUG: Search results preview: {repr(formatted_results[:300])}")
            print(f"RAG DEBUG: Replaced $query$ with: {repr(query)}")
        else:
            prompt = f"""You are an expert assistant. Answer the user's question using ONLY the search results provided below. Include citations like [1], [2], etc. when referencing specific sources.

User Question: {query}

Search Results:
{chr(10).join(search_results_text)}

Instructions:
- Answer the question directly using the search results
- Include citations [1], [2], etc. for each fact you mention
- Be specific and factual
- If the search results don't contain enough information, say so

Answer:"""

        print(f"RAG DEBUG: Final prompt length: {len(prompt)}")
        print(f"RAG DEBUG: Prompt preview: {repr(prompt[:300])}...")

        # Step 4: Call the model directly for generation
        try:
            import boto3
            import json

            if self.model_arn:
                model_id = self.model_arn
            else:
                model_id = self.inference_profile_arn

            print(f"RAG DEBUG: Using model: {model_id}")

            # Detect model type for proper formatting
            if "anthropic.claude" in model_id or "anthropic" in model_id.lower():
                print(f"RAG DEBUG: Using Claude format")
                # Use bedrock-runtime for direct model invocation
                bedrock_runtime = boto3.client('bedrock-runtime', region_name=self.region)

                # Claude-3 style prompt
                body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": int(self.max_tokens),
                    "temperature": float(self.temperature),
                    "top_p": float(self.top_p),
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                }
            else:
                print(f"RAG DEBUG: Using generic format")
                bedrock_runtime = boto3.client('bedrock-runtime', region_name=self.region)
                body = {
                    "max_tokens": int(self.max_tokens),
                    "temperature": float(self.temperature),
                    "top_p": float(self.top_p),
                    "prompt": prompt
                }

            print(f"RAG DEBUG: Calling bedrock-runtime directly...")
            response = bedrock_runtime.invoke_model(
                body=json.dumps(body),
                modelId=model_id,
                accept="application/json",
                contentType="application/json"
            )

            response_body = json.loads(response.get('body').read())
            print(f"RAG DEBUG: Raw response body: {response_body}")

            if "anthropic.claude" in model_id or "anthropic" in model_id.lower():
                answer = response_body.get('content', [{}])[0].get('text', '')
            else:
                answer = response_body.get('completion', '') or response_body.get('generated_text', '')

            print(f"RAG DEBUG: Generated answer length: {len(answer)}")
            print(f"RAG DEBUG: Generated answer preview: {repr(answer[:200])}")
            print(f"RAG DEBUG: Returning {len(sources)} sources")

            return answer, sources

        except Exception as e:
            print(f"RAG DEBUG: Error during generation: {e}")
            # Fallback to a basic response
            return f"I found {len(sources)} relevant sources but couldn't generate an answer. Error: {str(e)}", sources

    def retrieve(self, text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Retrieve from the knowledge base without generation."""
        req: Dict[str, Any] = {
            "knowledgeBaseId": self.kb_id,
            "retrievalQuery": {"text": text},
            "retrievalConfiguration": {
                "vectorSearchConfiguration": {"numberOfResults": int(top_k)}
            },
        }
        resp = self.client.retrieve(**req)
        return resp.get("retrievalResults", []) or []
