"""Quick test: send request directly to LM Studio with correct model."""
from openai import OpenAI

client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")
MODEL = "qwen3.5-4b-uncensored-hauhaucs-aggressive"

print(f"Using model: {MODEL}")
print("=== Sending Sol test request ===\n")

response = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "system", "content": """You are Sol, a friendly 25-year-old FEMALE neighbor. She is a freelance graphic designer who lives alone next door. She has a cat named Bartholomew. She knits blankets and grows plants.

Write in third person narration with *italics for actions* and "quotes for dialogue". 
Keep response 150-250 words. Include sensory details (sight, sound, touch, smell).
Sol's body language should contradict her words sometimes."""},
        {"role": "user", "content": "*looks up from the box* Hey, need help with those plants?"},
    ],
    temperature=0.85,
    max_tokens=1024,
)

print(f"Response ({len(response.choices[0].message.content)} chars):")
print(response.choices[0].message.content)
print(f"\nFinish reason: {response.choices[0].finish_reason}")
print(f"Tokens: prompt={response.usage.prompt_tokens}, completion={response.usage.completion_tokens}")
