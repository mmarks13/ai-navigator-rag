# Chainlit + AWS Bedrock Knowledge Bases Chatbot

Lightweight chat UI that queries an AWS Bedrock Knowledge Base via RetrieveAndGenerate. No local ingestion or vector DB.

## Setup

1) Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

2) Configure env (or edit `config/config.yaml`)

```bash
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1

BEDROCK_KB_ID=kb-xxxxxxxx
BEDROCK_MODEL_ARN=arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20240620-v1:0

# Optional
BEDROCK_MAX_TOKENS=800
BEDROCK_TEMPERATURE=0.2
BEDROCK_TOP_P=0.9
WELCOME_MESSAGE="Ready. Ask me about your knowledge base."
```

3) Run locally

```bash
chainlit run app/main.py -w --host 0.0.0.0 --port 8001
```

Open http://localhost:8001

## Deploy on AWS

Use App Runner, ECS/Fargate, EC2, or EKS:

- Build and push the Docker image to ECR
- Create the service from ECR
- Set env vars: `AWS_DEFAULT_REGION`, `BEDROCK_KB_ID`, `BEDROCK_MODEL_ARN`
- Attach an IAM role with Bedrock KB permissions

Example IAM policy:

```json
{
	"Version": "2012-10-17",
	"Statement": [
		{"Effect": "Allow", "Action": ["bedrock:RetrieveAndGenerate"], "Resource": "*"},
		{"Effect": "Allow", "Action": ["bedrock:Retrieve"], "Resource": "*"}
	]
}
```

## Config

`config/config.yaml` (overridable via env vars):

- aws.region (AWS_DEFAULT_REGION)
- aws.knowledge_base_id (BEDROCK_KB_ID)
- aws.model_arn (BEDROCK_MODEL_ARN)
- aws.max_tokens (BEDROCK_MAX_TOKENS)
- aws.temperature (BEDROCK_TEMPERATURE)
- aws.top_p (BEDROCK_TOP_P)
- ui.welcome_message (WELCOME_MESSAGE)

## Files

```
├── app/
│   ├── main.py           # Chainlit chat UI calling Bedrock KB
│   ├── rag.py            # Bedrock KB client + citation formatting
│   └── config_utils.py   # Config loader with env overlays
├── config/
│   └── config.yaml       # App config
├── prompts/
│   └── system_prompt.md  # Optional prompt used as KB generation prompt
├── Dockerfile
├── start.sh
└── requirements.txt
```
```
