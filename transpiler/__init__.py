import re
from transpiler.lexer import Lexer, TAMIL_TANGLISH_KEYWORDS
from transpiler.parser import Parser
from transpiler.semantic import SemanticAnalyzer
from transpiler.codegen import CodeGenerator
from transpiler.ai_module import AIModule
from transpiler.execution import ExecutionModule

def ast_to_dict(node):
    if node is None:
        return None
    if isinstance(node, list):
        return [ast_to_dict(n) for n in node]
    if isinstance(node, (int, float, str, bool)):
        return node
    if hasattr(node, '__dict__'):
        d = {'_type': type(node).__name__}
        for k, v in vars(node).items():
            d[k] = ast_to_dict(v)
        return d
    return str(node)

STRUCTURED_LINE_STARTERS = {
    'START', 'STOP', 'SET', 'IF', 'ELSE', 'ELIF', 'ELSEIF', 'ENDIF', 'END',
    'WHILE', 'ENDWHILE', 'FOR', 'ENDFOR', 'FUNCTION', 'DEF', 'DEFINE',
    'PROCEDURE', 'PROC', 'ENDFUNCTION', 'ENDDEF', 'RETURN', 'BREAK', 'CONTINUE',
    'LET', 'ASSIGN', 'DECLARE', 'IMPORT', 'PRINT', 'OUTPUT', 'READ', 'INPUT',
    *TAMIL_TANGLISH_KEYWORDS.keys()
}

class TranspilerPipeline:
    def __init__(self):
        self.ai = AIModule()

    def _is_nlp_input(self, code):
        """Return True only if the input looks like natural language prose rather than structured pseudocode."""
        cleaned = re.sub(r'"[^"]*"|\'[^\']*\'', '', code).strip()
        if not cleaned:
            return False

        # Structured operators or bracket syntax indicate code rather than plain English NLP
        if re.search(r'[=<>!+\-*/%\[\]]', cleaned):
            return False

        lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip() and not ln.strip().startswith('#')]
        if not lines:
            return False

        for ln in lines:
            words = ln.split()
            first_word = words[0].upper().rstrip(':')
            if first_word in STRUCTURED_LINE_STARTERS:
                return False
            # Function call syntax like foo(bar) at start of line
            if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*\s*\(', ln):
                return False

        return True

    def compile(self, code):
        result = {
            "tokens": [],
            "lex_errors": [],
            "parse_errors": [],
            "semantic_errors": [],
            "python_code": "",
            "ai_used": False,
            "ai_reason": "",
            "ai_structured": None,
            "ast_tree": None,
            "cfg_mermaid": "",
            "tac": [],
            "optimized_ir": [],
            "symbol_table": [],
            "success": False
        }
        
        # 1. Lexical Analysis (never use AI to bypass lexical errors)
        lexer = Lexer(code)
        tokens, lex_errors = lexer.tokenize()
        result["tokens"] = [{"type": t.type, "value": t.value, "line": t.line, "col": t.column} for t in tokens]
        result["lex_errors"] = lex_errors
        
        if lex_errors:
            return result
            
        # 2. Parsing
        parser = Parser(tokens)
        ast, parse_errors = parser.parse()
        result["parse_errors"] = parse_errors
        
        # Only use AI if the input is natural language (NLP), NEVER for fixing structured code errors
        if parse_errors and self._is_nlp_input(code):
            ai_ast = self.ai.interpret_natural_language(code)
            if ai_ast:
                if hasattr(ai_ast, 'statements'):
                    ast = ai_ast
                else:
                    ast.statements = [ai_ast]
                result["parse_errors"] = []
                result["ai_used"] = self.ai.ai_used
                result["ai_reason"] = self.ai.ai_reason
                result["ai_structured"] = self.ai.structured_intent

        if result["parse_errors"]:
            return result
            
        # 3. Semantic Analysis (never use AI to bypass semantic errors)
        analyzer = SemanticAnalyzer()
        semantic_errors = analyzer.analyze(ast)
        result["semantic_errors"] = semantic_errors
        
        if semantic_errors:
            return result

        # 4. Code Generation
        codegen = CodeGenerator()
        python_code = codegen.generate(ast)
        result["python_code"] = python_code
        result["success"] = True
            
        # Populate AST, CFG, and IR
        if 'ast' in locals() and ast:
            result["ast_tree"] = ast_to_dict(ast)
            from transpiler.cfg_generator import generate_cfg
            result["cfg_mermaid"] = generate_cfg(ast)
            
            from transpiler.ir_generator import TACGenerator, IROptimizer
            tac_gen = TACGenerator()
            raw_tac = tac_gen.generate(ast)
            result["tac"] = raw_tac
            
            optimizer = IROptimizer()
            result["optimized_ir"] = optimizer.optimize(raw_tac)
            
        if 'analyzer' in locals() and analyzer:
            result["symbol_table"] = analyzer.all_symbols
            
        return result
