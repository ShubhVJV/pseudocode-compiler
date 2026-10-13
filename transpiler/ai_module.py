import re
import os
import json
import requests
from transpiler.ast_nodes import *


def _load_env_file():
    """Load key-value pairs from .env in the project root without requiring external dependencies."""
    env_vars = {}
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(root_dir, ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    # Strip surrounding quotes if present
                    if len(val) >= 2 and ((val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'")):
                        val = val[1:-1].strip()
                    if key and val:
                        env_vars[key] = val
                        if not os.environ.get(key):
                            os.environ[key] = val
        except Exception:
            pass
    return env_vars


class AIModule:
    def __init__(self):
        env_file_vars = _load_env_file()
        self.groq_key = env_file_vars.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY") or ""
        self.gemini_key = env_file_vars.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY") or ""
        self.openai_key = env_file_vars.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
        generic_key = env_file_vars.get("AI_API_KEY") or os.environ.get("AI_API_KEY") or ""

        if generic_key and not (self.groq_key or self.gemini_key or self.openai_key):
            if generic_key.startswith("gsk_"):
                self.groq_key = generic_key
            elif generic_key.startswith("AIza"):
                self.gemini_key = generic_key
            elif generic_key.startswith("sk-"):
                self.openai_key = generic_key
            else:
                self.groq_key = generic_key

        self.api_key = self.groq_key or self.gemini_key or self.openai_key or None
        self.ai_used = False
        self.ai_reason = ""
        self.structured_intent = None

    def _is_external_ai_enabled(self):
        if not self.api_key:
            return False
        # Avoid live network calls during unit tests unless explicitly enabled
        if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("FORCE_AI_IN_TESTS"):
            return False
        return True

    def interpret_natural_language(self, text):
        # 1. Rule-based recognition
        intent = self.rule_based_fallback(text)
        if intent:
            return intent

        # 2. AI Fallback
        if not self._is_external_ai_enabled():
            self.structured_intent = {"error": "AI API key missing in .env, cannot parse"}
            return None

        self.ai_used = True
        self.ai_reason = "Natural language instruction translated using AI."
        return self.call_ai_api(text)

    def _make_operand(self, val):
        val = val.strip()
        if re.match(r'^-?\d+$', val):
            return Literal(int(val))
        if re.match(r'^-?\d+\.\d+$', val):
            return Literal(float(val))
        return Identifier(val)

    def rule_based_fallback(self, text):
        text_lower = text.lower().strip()

        # Addition: "add 5 and 6", "calculate sum of a and b"
        match = re.match(r'^(?:add|calculate sum of|sum|find sum of)\s+([a-z0-9_]+)\s*(?:and|,)\s*([a-z0-9_]+)$', text_lower)
        if match:
            var1, var2 = match.group(1), match.group(2)
            return Declare("sum", BinaryOp(self._make_operand(var1), 'PLUS', self._make_operand(var2)))

        match = re.match(r'^add (\d+) (?:no|numbers) ([a-z0-9_]+),([a-z0-9_]+)$', text_lower)
        if match:
            var1, var2 = match.group(2), match.group(3)
            return Declare("sum", BinaryOp(self._make_operand(var1), 'PLUS', self._make_operand(var2)))

        # Subtraction: "subtract b from a"
        match = re.match(r'^subtract\s+([a-z0-9_]+)\s+from\s+([a-z0-9_]+)$', text_lower)
        if match:
            var1, var2 = match.group(1), match.group(2)
            return Declare("result", BinaryOp(self._make_operand(var2), 'MINUS', self._make_operand(var1)))

        # Multiplication: "multiply a and b"
        match = re.match(r'^(?:multiply|product of)\s+([a-z0-9_]+)\s*(?:and|by|,)\s*([a-z0-9_]+)$', text_lower)
        if match:
            var1, var2 = match.group(1), match.group(2)
            return Declare("product", BinaryOp(self._make_operand(var1), 'MUL', self._make_operand(var2)))

        return None

    def _request_llm_json(self, system_prompt, user_prompt):
        """Send prompt to configured provider (Groq, Gemini, or OpenAI) and parse JSON response."""
        content = None

        # 1. Groq API (or gsk_ key)
        if self.groq_key or (self.api_key and str(self.api_key).startswith("gsk_")):
            key = self.groq_key or self.api_key
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            }
            groq_models = (
                "openai/gpt-oss-120b",
                "openai/gpt-oss-20b",
                "qwen/qwen3.8-27b",
                "llama-3.3-70b-versatile",
                "llama-3.1-8b-instant",
            )
            for model_name in groq_models:
                data = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.1
                }
                resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=10
                )
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"]
                    break

        # 2. Google Gemini API
        elif self.gemini_key or (self.api_key and str(self.api_key).startswith("AIza")):
            key = self.gemini_key or self.api_key
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
            data = {
                "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
                "generationConfig": {"temperature": 0.1}
            }
            resp = requests.post(url, json=data, timeout=10)
            if resp.status_code == 200:
                candidates = resp.json().get("candidates", [])
                if candidates:
                    content = candidates[0]["content"]["parts"][0]["text"]

        # 3. OpenAI API
        elif self.openai_key or self.api_key:
            key = self.openai_key or self.api_key
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.1
            }
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=10
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]

        if not content:
            return None

        # Strip optional <think>...</think> blocks
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        content = content.strip()
        start_brace = content.find("{")
        end_brace = content.rfind("}")
        if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
            content = content[start_brace:end_brace + 1]

        return json.loads(content)

    def _pseudocode_to_ast(self, pseudocode_str):
        from transpiler.lexer import Lexer
        from transpiler.parser import Parser
        lexer = Lexer(pseudocode_str)
        tokens, lex_errs = lexer.tokenize()
        if lex_errs:
            return None
        parser = Parser(tokens)
        ast, parse_errs = parser.parse()
        if parse_errs:
            return None
        return ast

    def call_ai_api(self, text):
        system_prompt = (
            "You are a compiler assistant that translates natural-language instructions or informal pseudocode "
            "into valid structured pseudocode. Respond ONLY with valid JSON."
        )
        user_prompt = f"""
Convert the following natural language or informal instruction into structured pseudocode.
Rules for valid pseudocode:
- Use direct assignment: x = 10 (NEVER use the SET keyword).
- Use PRINT expr to output values.
- Use INPUT var or READ var for input.
- Conditionals: IF cond THEN ... ELSE ... END IF
- Loops: WHILE cond DO ... END WHILE, FOR EACH x IN list ... END FOR, or FOR i FROM 0 TO 10 ... END FOR
- Functions: FUNCTION name(params) ... RETURN val ... END FUNCTION

Respond ONLY with JSON in this exact format:
{{
  "intent": "Short description of what the instruction does",
  "pseudocode": "x = 5\\ny = 10\\nresult = x + y\\nPRINT result"
}}

Instruction:
{text}
"""
        try:
            parsed_json = self._request_llm_json(system_prompt, user_prompt)
            if not parsed_json:
                return None
            self.structured_intent = parsed_json
            if isinstance(parsed_json, dict) and "pseudocode" in parsed_json:
                ast_prog = self._pseudocode_to_ast(parsed_json["pseudocode"])
                if ast_prog and ast_prog.statements:
                    if len(ast_prog.statements) == 1:
                        return ast_prog.statements[0]
                    return ast_prog
            return self.json_to_ast(parsed_json)
        except Exception as e:
            self.structured_intent = {"error": str(e)}
        return None

    def json_to_ast(self, data):
        if not isinstance(data, dict):
            return Literal(data)

        if "pseudocode" in data:
            ast_prog = self._pseudocode_to_ast(data["pseudocode"])
            if ast_prog:
                return ast_prog

        node_type = data.get("type")
        if node_type == "PROGRAM":
            stmts = [self.json_to_ast(s) for s in data.get("statements", [])]
            return Program([s for s in stmts if s is not None])
        elif node_type == "ASSIGN":
            return Assign(data["name"], self.json_to_ast(data["value"]))
        elif node_type == "DECLARE":
            return Declare(data["name"], self.json_to_ast(data.get("value")))
        elif node_type == "BINARY_OP":
            return BinaryOp(self.json_to_ast(data["left"]), data["op"], self.json_to_ast(data["right"]))
        elif node_type == "IDENTIFIER":
            return Identifier(data["name"])
        elif node_type == "LITERAL":
            return Literal(data["value"])
        elif node_type == "PRINT":
            return Print([self.json_to_ast(data["expr"])])

        if isinstance(data, str):
            if data.isnumeric():
                return Literal(int(data))
            return Identifier(data)

        return None

    def fix_code_errors(self, code, errors):
        if not self._is_external_ai_enabled():
            self.structured_intent = {"error": "AI API key missing in .env, cannot parse"}
            return None

        self.ai_used = True
        self.ai_reason = "Resolved natural language or simple syntax error using AI."

        system_prompt = (
            "You are a compiler error-recovery and NLP assistant for a Pseudocode-to-Python transpiler. "
            "Respond ONLY with valid JSON."
        )
        user_prompt = f"""
The following user input (natural language or pseudocode with minor typos/errors) produced these compiler diagnostics:
Errors: {errors}

Input Code:
{code}

Convert or repair the input into valid canonical pseudocode while preserving all user variable names, function names, and logic.
Rules for valid canonical pseudocode:
- Use direct assignment: x = 10 (NEVER use SET).
- Close every IF with END IF, every WHILE with END WHILE, every FOR with END FOR, every FUNCTION with END FUNCTION.
- Use PRINT for output and INPUT / READ for input.
- Do NOT invent unapproved imports (only math, random, time, datetime are allowed).

Respond ONLY with JSON in this exact format:
{{
  "intent": "Explanation of the NLP translation or syntax fix applied",
  "pseudocode": "Corrected canonical pseudocode here"
}}
"""
        try:
            parsed_json = self._request_llm_json(system_prompt, user_prompt)
            if not parsed_json:
                return None
            self.structured_intent = parsed_json
            return self.json_to_ast(parsed_json)
        except Exception as e:
            self.structured_intent = {"error": str(e)}

        return None
