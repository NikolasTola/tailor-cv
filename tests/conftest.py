import sys
from pathlib import Path

# permite "from llm_falsa import LLMFalsa" nos testes
sys.path.insert(0, str(Path(__file__).parent))
