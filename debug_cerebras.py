from cerebras.cloud.sdk import Cerebras
from dotenv import load_dotenv
import os
load_dotenv('e:/yes/cty/chatbot/companion-demo/.env')
client = Cerebras(api_key=os.environ.get('CEREBRAS_API_KEY'))
stream = client.chat.completions.create(
    model='llama-3.3-70b',
    messages=[{'role':'user','content':'say hi'}],
    stream=True,
    max_completion_tokens=20,
)
for chunk in stream:
    print(type(chunk))
    print(repr(chunk))
    break
