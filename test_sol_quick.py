"""Quick test: 3 turns with Sol to evaluate model quality before full run."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

from characters import get_all_characters
from prompt_builder import build_messages_full
from cerebras_client import chat_complete, MODEL
from conversation import ConversationManager
from memory.scene_tracker import SceneTracker
from affection_state import AffectionState

print(f"Model: {MODEL}\n")

conv = ConversationManager(max_turns=10)
scene = SceneTracker()
aff = AffectionState()
char = get_all_characters()["sol"]

test_msgs = [
    "*looks up from the box* Hey, need help with those plants?",
    "Sol, nice name. I'm still unloading honestly, got like ten more boxes. You live alone?",
    "*brushes a strand of hair from her face, letting his fingers linger on her cheek* You know, I'm not really thinking about podcasts right now. I keep getting distracted by how pretty you are up close.",
]

for i, msg in enumerate(test_msgs, 1):
    print(f"{'='*50}")
    print(f"TURN {i} — USER: {msg[:60]}...")
    conv.add_user(msg)
    scene.update(msg)
    
    messages = build_messages_full(
        character_key="sol",
        conversation_window=conv.get_window(),
        user_name="User",
        total_turns=conv.total_turns,
        scene_context=scene.get_context_block() + aff.to_prompt_block(),
    )
    
    response = chat_complete(messages=messages, temperature=0.85, max_tokens=1024)
    conv.add_assistant(response)
    
    words = len(response.split())
    print(f"\nSOL ({words} words):\n{response}\n")
