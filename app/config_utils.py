import os, yaml
from dotenv import load_dotenv


def load_config(path: str):
    load_dotenv(override=True)
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    def env(name, default=None):
        return os.getenv(name, default if default is None else str(default))

    def env_num(name, default, cast=float):
        val = os.getenv(name)
        if val is None:
            return default
        try:
            return cast(val)
        except Exception:
            return default

    aws = cfg.get("aws", {})
    aws["region"] = env("AWS_DEFAULT_REGION", aws.get("region", "us-east-1"))
    aws["knowledge_base_id"] = env("BEDROCK_KB_ID", aws.get("knowledge_base_id", ""))
    aws["model_arn"] = env("BEDROCK_MODEL_ARN", aws.get("model_arn", ""))
    aws["inference_profile_arn"] = env("BEDROCK_INFERENCE_PROFILE_ARN", aws.get("inference_profile_arn", ""))
    aws["max_tokens"] = env_num("BEDROCK_MAX_TOKENS", int(aws.get("max_tokens", 800)), int)
    aws["temperature"] = env_num("BEDROCK_TEMPERATURE", float(aws.get("temperature", 0.2)), float)
    aws["top_p"] = env_num("BEDROCK_TOP_P", float(aws.get("top_p", 0.9)), float)
    cfg["aws"] = aws

    ui = cfg.get("ui", {})
    ui["welcome_message"] = env("WELCOME_MESSAGE", ui.get("welcome_message", "Ready. Ask me about your knowledge base."))
    cfg["ui"] = ui

    return cfg
