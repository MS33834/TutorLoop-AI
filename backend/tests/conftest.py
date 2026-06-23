import os

# The app validates these settings at import time; provide safe defaults for tests.
os.environ.setdefault("SECRET_KEY", "a" * 32)
os.environ.setdefault("LLM_API_KEYS", "sk-test-key")
os.environ.setdefault("LLM_BASE_URLS", "http://localhost:8000/v1")
os.environ.setdefault("LLM_MODELS", "test-model")
