from transpiler.lexer import Lexer
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

class TranspilerPipeline:
    def __init__(self):
        self.ai = AIModule()
        
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
        
        # 1. Lexical Analysis
        lexer = Lexer(code)
        tokens, lex_errors = lexer.tokenize()
        result["tokens"] = [{"type": t.type, "value": t.value, "line": t.line, "col": t.column} for t in tokens]
        result["lex_errors"] = lex_errors
        
        if lex_errors:
            self._attempt_ai_fix(code, result, lex_errors)
            if not result["success"]:
                return result
            
        if not result["success"]:
            # 2. Parsing
            parser = Parser(tokens)
            ast, parse_errors = parser.parse()
            result["parse_errors"] = parse_errors
            
            # If parsing fails on the first token, it might be a single natural language instruction
            if parse_errors and len(code.split('\n')) == 1:
                ai_ast = self.ai.interpret_natural_language(code)
                if ai_ast:
                    ast.statements = [ai_ast]
                    result["parse_errors"] = [] # Cleared because AI handled it
                    result["ai_used"] = self.ai.ai_used
                    result["ai_reason"] = self.ai.ai_reason
                    result["ai_structured"] = self.ai.structured_intent

            if result["parse_errors"]:
                self._attempt_ai_fix(code, result, result["parse_errors"])
                if not result["success"]:
                    return result
                
        if not result["success"]:
            # 3. Semantic Analysis
            analyzer = SemanticAnalyzer()
            semantic_errors = analyzer.analyze(ast)
            result["semantic_errors"] = semantic_errors
            
            if semantic_errors:
                self._attempt_ai_fix(code, result, semantic_errors)
                if not result["success"]:
                    return result

        if not result["success"]:
            # 4. Code Generation
            codegen = CodeGenerator()
            python_code = codegen.generate(ast)
            result["python_code"] = python_code
            result["success"] = True
            
        # Ensure we always populate AST if it exists
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
            
        # Ensure we always populate symbols if analyzer ran
        if 'analyzer' in locals() and analyzer:
            result["symbol_table"] = analyzer.all_symbols
            
        return result

    def _attempt_ai_fix(self, code, result, errors):
        ai_ast = self.ai.fix_code_errors(code, errors)
        if ai_ast:
            codegen = CodeGenerator()
            python_code = codegen.generate(ai_ast)
            result["python_code"] = python_code
            result["ast_tree"] = ast_to_dict(ai_ast)
            
            from transpiler.cfg_generator import generate_cfg
            result["cfg_mermaid"] = generate_cfg(ai_ast)
            
            from transpiler.ir_generator import TACGenerator, IROptimizer
            tac_gen = TACGenerator()
            raw_tac = tac_gen.generate(ai_ast)
            result["tac"] = raw_tac
            
            optimizer = IROptimizer()
            result["optimized_ir"] = optimizer.optimize(raw_tac)
            
            analyzer = SemanticAnalyzer()
            analyzer.analyze(ai_ast)
            result["symbol_table"] = analyzer.all_symbols
            
            result["ai_used"] = True
            result["ai_reason"] = "cant compile manually using ai to resolve the issues"
            result["ai_structured"] = self.ai.structured_intent
            result["success"] = True
            # Clear manual errors so UI doesn't say it failed
            result["lex_errors"] = []
            result["parse_errors"] = []
            result["semantic_errors"] = []
