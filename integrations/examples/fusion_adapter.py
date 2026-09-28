"""Wrap any agent for Fusion:  fusion run start --prompt agent.txt --target "cmd:python fusion_adapter.py"

Fusion writes one JSON request to stdin and reads the reply from stdout:

  stdin   {"system": "...", "messages": [{"role": "user", "content": "..."}], "max_tokens": 512,
           "temperature": 0.0, "role": "target"}
  stdout  {"text": "..."}  (or plain text)

Replace reply() with a call into the agent you actually run. Examples:

  Hugging Face transformers (pip install transformers torch):
      from transformers import pipeline
      chat = pipeline("text-generation", model="Qwen/Qwen2.5-0.5B-Instruct")
      out = chat([{"role": "system", "content": system}, *messages], max_new_tokens=512)
      return out[0]["generated_text"][-1]["content"]

  Your own agent over HTTP:
      import urllib.request
      body = json.dumps({"system": system, "messages": messages}).encode()
      req = urllib.request.Request("http://127.0.0.1:8080/chat", body, {"Content-Type": "application/json"})
      return json.load(urllib.request.urlopen(req))["reply"]

  A framework (LangChain, LlamaIndex, CrewAI...): build the chain once, invoke it with the messages.

Tool calls: return them in the reply the way the agent writes them (e.g. an `ACTION: {"tool": ...}`
line); Fusion's checks read tool calls from the reply text.
"""

import json
import sys


def reply(system: str, messages: list[dict]) -> str:
    return "Replace reply() in fusion_adapter.py with a call to your agent."


if __name__ == "__main__":
    request = json.load(sys.stdin)
    print(json.dumps({"text": reply(request.get("system", ""), request.get("messages", []))}))
