#!/usr/bin/env python3
"""
Debug script to replicate citation mismatch between retrieve() and retrieve_and_generate()
"""

import os
import json
import boto3
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Configuration
REGION = os.getenv("AWS_DEFAULT_REGION")
KB_ID = os.getenv("BEDROCK_KB_ID")
MODEL_ARN = os.getenv("BEDROCK_MODEL_ARN")
PROFILE_ARN = os.getenv("BEDROCK_INFERENCE_PROFILE_ARN")
QUERY = "what is odi doing with GenAI?"

print(f"Region: {REGION}")
print(f"KB_ID: {KB_ID}")
print(f"Model ARN: {MODEL_ARN[:20] + '...' if MODEL_ARN else None}")
print(f"Profile ARN: {PROFILE_ARN[:20] + '...' if PROFILE_ARN else None}")
print(f"Query: {QUERY}")
print("=" * 80)

if not all([REGION, KB_ID]):
    print("ERROR: Missing required env vars AWS_DEFAULT_REGION or BEDROCK_KB_ID")
    exit(1)

if not (MODEL_ARN or PROFILE_ARN):
    print("ERROR: Missing MODEL_ARN or PROFILE_ARN")
    exit(1)

# Initialize client
client = boto3.client("bedrock-agent-runtime", region_name=REGION)

print("\n1. TESTING RETRIEVE (works):")
print("-" * 40)

try:
    retrieve_resp = client.retrieve(
        knowledgeBaseId=KB_ID,
        retrievalQuery={"text": QUERY},
        retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 5}},
    )
    results = retrieve_resp.get("retrievalResults", [])
    print(f"Retrieved {len(results)} results")

    if results:
        first = results[0]
        print(f"First result URI: {first.get('metadata', {}).get('_source_uri')}")
        print(f"First result title: {first.get('metadata', {}).get('x-amz-kendra-document-title')}")
        print(f"First result snippet: {str(first.get('content', {}).get('text', ''))[:100]}...")
    else:
        print("No results found")

except Exception as e:
    print(f"RETRIEVE ERROR: {e}")

print("\n2. TESTING RETRIEVE_AND_GENERATE (broken citations):")
print("-" * 50)

# Test different prompt variations
prompt_variations = [
    "You are a helpful assistant. Use the provided search results to answer.\n\n$search_results$",
    "Answer the question using only the provided search results. If the search results don't contain enough information, say 'I don't have enough information.'\n\n$search_results$",
    "Based on the search results below, provide a comprehensive answer.\n\n$search_results$",
    "Please answer based strictly on the search results provided:\n\n$search_results$"
]

for i, prompt in enumerate(prompt_variations, 1):
    print(f"\n2.{i}. Testing prompt variation {i}:")
    print(f"Prompt: {prompt[:50]}...")

    try:
        gen_cfg = {
            "inferenceConfig": {
                "textInferenceConfig": {
                    "maxTokens": 800,
                    "temperature": 0.2,
                    "topP": 0.9,
                }
            },
            "promptTemplate": {"textPromptTemplate": prompt}
        }

        kb_cfg = {
            "knowledgeBaseId": KB_ID,
            "generationConfiguration": gen_cfg,
        }

        # Add model/profile ARN
        if PROFILE_ARN:
            kb_cfg["inferenceProfileArn"] = PROFILE_ARN
        elif MODEL_ARN:
            kb_cfg["modelArn"] = MODEL_ARN

        rag_resp = client.retrieve_and_generate(
            input={"text": QUERY},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": kb_cfg,
            },
        )

        # Analyze response
        answer = rag_resp.get("output", {}).get("text", "")
        citations = rag_resp.get("citations", [])

        print(f"Answer length: {len(answer)} chars")
        print(f"Answer preview: {answer[:100]}...")
        print(f"Citations count: {len(citations)}")

        # Analyze each citation
        for ci, citation in enumerate(citations):
            gen_part = citation.get("generatedResponsePart", {}).get("textResponsePart", {})
            span = gen_part.get("span", {})
            span_text = gen_part.get("text", "")
            refs = citation.get("retrievedReferences", [])

            print(f"  Citation {ci+1}:")
            print(f"    Span: {span}")
            print(f"    Span text: '{span_text}'")
            print(f"    Retrieved refs: {len(refs)}")

            # Check if span text matches answer substring
            if span.get("start") is not None and span.get("end") is not None:
                start, end = span["start"], span["end"]
                actual_span_text = answer[start:end] if start < len(answer) and end <= len(answer) else "OUT_OF_BOUNDS"
                print(f"    Actual span from answer: '{actual_span_text}'")

            if refs:
                ref = refs[0]
                uri = (ref.get("metadata", {}).get("_source_uri") or
                       ref.get("metadata", {}).get("x-amz-kendra-document-id"))
                print(f"    First ref URI: {uri}")
            else:
                print(f"    NO REFERENCES - this is the problem!")

    except Exception as e:
        print(f"RAG ERROR for prompt {i}: {e}")

print("\n3. DIAGNOSIS:")
print("-" * 20)
print("If retrieve() works but retrieve_and_generate() has citations with empty retrievedReferences,")
print("the issue is likely:")
print("1. The model is not grounding its response to the KB search results")
print("2. The model is using its own knowledge instead of $search_results$")
print("3. The prompt template isn't forcing grounding effectively")
print("4. The model/inference profile doesn't support proper citation grounding")
