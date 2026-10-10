import re
import os
import json
import requests
from transpiler.ast_nodes import *

class AIModule:
    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY")
        self.ai_used = False
        self.ai_reason = ""
        self.structured_intent = None

    def interpret_natural_language(self, text):
        # 1. Rule-based recognition
        intent = self.rule_based_fallback(text)
        if intent:
            return intent
            
        # 2. AI Fallback
        self.ai_used = True
        self.ai_reason = "Rule-based recognition failed to match the intent."
        if not self.api_key:
            # Mock fallback if no API key
            self.structured_intent = {"error": "AI API key missing, cannot parse"}
            return None
            
        return self.call_ai_api(text)

    def _make_operand(self, val):
        if val.isdigit():
            return Literal(int(val))
        return Identifier(val)

    def rule_based_fallback(self, text):
        text_lower = text.lower().strip()
        
        # Addition
        match = re.match(r'(add|calculate sum of|sum|find sum of)\s+([a-z0-9_]+)\s*(?:and|,|)\s*([a-z0-9_]+)', text_lower)
        if match:
            var1, var2 = match.group(2), match.group(3)
            # DECLARE sum = var1 + var2
            return Declare("sum", BinaryOp(self._make_operand(var1), 'PLUS', self._make_operand(var2)))

        match = re.match(r'add (\d+) (?:no|numbers) ([a-z0-9_]+),([a-z0-9_]+)', text_lower)
        if match:
            var1, var2 = match.group(2), match.group(3)
            return Declare("sum", BinaryOp(self._make_operand(var1), 'PLUS', self._make_operand(var2)))
            
        # Swap
        match = re.match(r'swap(?:\s+2\s+(?:no|numbers))?\s+([a-z0-9_]+)\s*(?:and|,)\s*([a-z0-9_]+)', text_lower)
        if match:
            var1, var2 = match.group(1), match.group(2)
            # _temp = var1, var1 = var2, var2 = _temp
            # For simplicity, returning a print or we could return a block of statements
            return None # Requires handling blocks of AST nodes, let's keep it simple or implement a Block node

        return None

    def call_ai_api(self, text):
        # Using Groq API as an example for free Llama-family model
        prompt = f"""
        Convert the following natural language or Tanglish instruction into a structured JSON representation of an AST.
        Only respond with JSON.
        Operations supported: ASSIGN, PRINT, READ, DECLARE
        Example for 'add a and b':
        {{"type": "ASSIGN", "name": "result", "value": {{"type": "BINARY_OP", "left": "a", "op": "PLUS", "right": "b"}}}}
        
        Instruction: {text}
        """
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "llama3-8b-8192",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }
        
        try:
            response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data, timeout=5)
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                # extract json block if there are markdown ticks
                if '```json' in content:
                    content = content.split('```json')[1].split('```')[0]
                elif '```' in content:
                    content = content.split('```')[1].split('```')[0]
                
                parsed_json = json.loads(content.strip())
                self.structured_intent = parsed_json
                return self.json_to_ast(parsed_json)
        except Exception as e:
            self.structured_intent = {"error": str(e)}
        
        return None

    def json_to_ast(self, data):
        if not isinstance(data, dict):
            return Literal(data)
            
        node_type = data.get("type")
        if node_type == "PROGRAM":
            stmts = [self.json_to_ast(s) for s in data.get("statements", [])]
            return Program(stmts)
        elif node_type == "ASSIGN":
            return Assign(data["name"], self.json_to_ast(data["value"]))
        elif node_type == "BINARY_OP":
            return BinaryOp(self.json_to_ast(data["left"]), data["op"], self.json_to_ast(data["right"]))
        elif node_type == "IDENTIFIER":
            return Identifier(data["name"])
        elif node_type == "LITERAL":
            return Literal(data["value"])
        elif node_type == "PRINT":
            return Print([self.json_to_ast(data["expr"])])
        
        # Fallback for simple string references
        if isinstance(data, str):
            if data.isnumeric():
                return Literal(int(data))
            return Identifier(data)
            
        return None

    def fix_code_errors(self, code, errors):
        self.ai_used = True
        self.ai_reason = "cant compile manually using ai to resolve the issues"
        
        if not self.api_key:
            self.structured_intent = {"error": "AI API key missing, cannot parse"}
            return None
            
        prompt = f"""
        The following pseudocode failed to compile with these errors: {errors}
        Code:
        {code}
        
        Fix the logic and convert it into a structured JSON representation of an AST representing a PROGRAM.
        Only respond with JSON. Do not include markdown ticks.
        Format:
        {{
            "type": "PROGRAM",
            "statements": [
                {{"type": "ASSIGN", "name": "a", "value": {{"type": "LITERAL", "value": 5}}}},
                {{"type": "PRINT", "expr": {{"type": "IDENTIFIER", "name": "a"}}}}
            ]
        }}
        """
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "llama3-8b-8192",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }
        
        try:
            response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data, timeout=5)
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                if '```json' in content:
                    content = content.split('```json')[1].split('```')[0]
                elif '```' in content:
                    content = content.split('```')[1].split('```')[0]
                
                parsed_json = json.loads(content.strip())
                self.structured_intent = parsed_json
                return self.json_to_ast(parsed_json)
        except Exception as e:
            self.structured_intent = {"error": str(e)}
            
        return None
