import boto3
from typing import List, Tuple, Optional


class BedrockKBClient:
    """Thin wrapper around Agents for Bedrock Runtime retrieve_and_generate."""

    def __init__(self, region: str, kb_id: str, model_arn: Optional[str] = None, inference_profile_arn: Optional[str] = None, max_tokens: int = 800, temperature: float = 0.2, top_p: float = 0.9):
        self.client = boto3.client("bedrock-agent-runtime", region_name=region)
        self.kb_id = kb_id
        self.model_arn = model_arn
        self.inference_profile_arn = inference_profile_arn
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p

    def ask(self, text: str, system_prompt: str | None = None) -> Tuple[str, List[dict]]:
        gen_cfg = {
            "inferenceConfig": {
                "textInferenceConfig": {
                    "maxTokens": int(self.max_tokens),
                    "temperature": float(self.temperature),
                    "topP": float(self.top_p),
                }
            }
        }
        if system_prompt:
            # For KB generationConfiguration, prompt must include $search_results$
            prompt_text = system_prompt
            if "$search_results$" not in prompt_text:
                prompt_text = f"{prompt_text}\n\n$search_results$"
            gen_cfg["promptTemplate"] = {"textPromptTemplate": prompt_text}

        kb_cfg = {
            "knowledgeBaseId": self.kb_id,
            "generationConfiguration": gen_cfg,
        }
        if self.inference_profile_arn:
            kb_cfg["inferenceProfileArn"] = self.inference_profile_arn
        elif self.model_arn:
            kb_cfg["modelArn"] = self.model_arn
        else:
            raise ValueError("Either model_arn or inference_profile_arn must be provided")

        resp = self.client.retrieve_and_generate(
            input={"text": text},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": kb_cfg,
            },
        )

        answer = resp.get("output", {}).get("text", "")
        citations = resp.get("citations", []) or []
        return answer, citations
