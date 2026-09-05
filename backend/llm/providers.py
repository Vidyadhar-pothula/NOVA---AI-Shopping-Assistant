"""
LLM Provider Abstraction for NOVA Commerce Agent.
Supports Ollama local LLM execution with automatic model fallback and diagnostic reporting.
"""
import json
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple, Optional

class LLMProvider(ABC):
    @abstractmethod
    def generate_response(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        """
        Send chat messages and tool schemas to the model.
        Returns:
            Tuple[content, tool_calls]
        """
        pass

class OllamaProvider(LLMProvider):
    # Candidate models in order of preference if primary is missing or fails
    FALLBACK_MODELS = ["llama3.1:8b", "llama3.2:latest", "llama3:latest", "qwen2.5:14b", "tinyllama:latest"]

    def __init__(self, model_name: str = "llama3.1:8b", api_url: str = "http://localhost:11434/api/chat"):
        self.model_name = model_name
        self.api_url = api_url

    def _call_ollama_api(self, model: str, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "top_p": 0.9,
                "num_predict": 300
            }
        }
        if tools:
            payload["tools"] = tools

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.api_url, 
            data=data, 
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def generate_response(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        # Try requested primary model first
        models_to_try = [self.model_name] + [m for m in self.FALLBACK_MODELS if m != self.model_name]

        last_error = None
        for model in models_to_try:
            try:
                print(f"🤖 [OllamaProvider] Invoking model '{model}' at {self.api_url}...")
                resp_data = self._call_ollama_api(model, messages, tools)
                
                message = resp_data.get("message", {})
                content = message.get("content")
                
                raw_tool_calls = message.get("tool_calls", [])
                tool_calls = []
                for tc in raw_tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name")
                    args = fn.get("arguments", {})
                    if name:
                        tool_calls.append({
                            "name": name,
                            "arguments": args
                        })
                        
                print(f"✅ [OllamaProvider] Model '{model}' successfully responded.")
                return content, tool_calls

            except urllib.error.HTTPError as e:
                error_text = e.read().decode("utf-8", errors="ignore")
                print(f"⚠️ [OllamaProvider] Model '{model}' HTTP Error {e.code}: {error_text}")
                # Ollama returns 400 when model emits empty output with tools enabled.
                # Retry without tools so the model can give a plain conversational answer.
                if e.code == 400 and tools and "empty" in error_text.lower():
                    try:
                        print(f"🔄 [OllamaProvider] Retrying '{model}' without tools (empty output workaround)...")
                        resp_data = self._call_ollama_api(model, messages, [])  # no tools
                        message = resp_data.get("message", {})
                        content = message.get("content")
                        if content:
                            print(f"✅ [OllamaProvider] Retry succeeded (no-tools mode).")
                            return content, []  # no tool calls in no-tools mode
                    except Exception as retry_err:
                        print(f"⚠️ [OllamaProvider] Retry without tools also failed: {retry_err}")
                last_error = e
            except urllib.error.URLError as e:
                print(f"❌ [OllamaProvider] Connection error to Ollama at {self.api_url}: {e.reason}")
                raise RuntimeError(f"Could not connect to Ollama at http://localhost:11434. Is Ollama running?") from e
            except Exception as e:
                print(f"⚠️ [OllamaProvider] Error calling model '{model}': {e}")
                last_error = e

        raise RuntimeError(f"Ollama failed to generate response across all models: {last_error}")

