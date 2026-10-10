from transpiler.ast_nodes import *
from transpiler.symbol_table import SymbolTable

class SemanticAnalyzer:
    def __init__(self):
        self.global_scope = SymbolTable()
        self.current_scope = self.global_scope
        self.errors = []
        self.all_symbols = []

    def analyze(self, node):
        self.visit(node)
        return self.errors

    def visit(self, node):
        method_name = f'visit_{type(node).__name__}'
        visitor = getattr(self, method_name, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node):
        pass

    def visit_Program(self, node):
        for stmt in node.statements:
            self.visit(stmt)

    def visit_ImportStmt(self, node):
        allowed = ["math", "random", "time", "datetime"]
        if node.module_name not in allowed:
            self.errors.append(f"Import '{node.module_name}' is not approved/allowed.")

    def visit_Declare(self, node):
        # We can infer type from value if present
        var_type = 'ANY'
        if node.value:
            var_type = self.visit(node.value)
        success, err = self.current_scope.define(node.name, var_type)
        if not success:
            self.errors.append(err)
        else:
            self.all_symbols.append({"name": node.name, "type": var_type, "scope": "Local/Global", "kind": "Variable"})

    def visit_Assign(self, node):
        val_type = self.visit(node.value)
        var_type = self.current_scope.resolve(node.name)
        
        if var_type is None:
            # Implicit declaration
            inferred_type = val_type or 'ANY'
            self.current_scope.define(node.name, inferred_type)
            var_type = inferred_type
            self.all_symbols.append({"name": node.name, "type": var_type, "scope": "Local/Global", "kind": "Variable (Implicit)"})
            
        if node.index:
            self.visit(node.index) # index should be INT, maybe check that
            
        if var_type == 'ANY' and val_type:
            self.current_scope.update(node.name, val_type)
            
    def visit_Print(self, node):
        for expr in node.expressions:
            self.visit(expr)

    def visit_Read(self, node):
        var_type = self.current_scope.resolve(node.name)
        if var_type is None:
            self.current_scope.define(node.name, 'STRING')
            self.all_symbols.append({"name": node.name, "type": "STRING", "scope": "Local/Global", "kind": "Variable (Implicit)"})

    def visit_IfStmt(self, node):
        cond_type = self.visit(node.condition)
        # Push scope
        prev_scope = self.current_scope
        self.current_scope = SymbolTable(parent=prev_scope)
        for stmt in node.then_branch:
            self.visit(stmt)
        self.current_scope = prev_scope
        
        for cond, body in node.else_ifs:
            self.visit(cond)
            self.current_scope = SymbolTable(parent=prev_scope)
            for stmt in body:
                self.visit(stmt)
            self.current_scope = prev_scope
            
        if node.else_branch:
            self.current_scope = SymbolTable(parent=prev_scope)
            for stmt in node.else_branch:
                self.visit(stmt)
            self.current_scope = prev_scope

    def visit_WhileStmt(self, node):
        self.visit(node.condition)
        prev_scope = self.current_scope
        self.current_scope = SymbolTable(parent=prev_scope)
        for stmt in node.body:
            self.visit(stmt)
        self.current_scope = prev_scope

    def visit_ForStmt(self, node):
        self.current_scope.define(node.var, 'NUMBER')
        self.visit(node.start)
        self.visit(node.end)
        prev_scope = self.current_scope
        self.current_scope = SymbolTable(parent=prev_scope)
        for stmt in node.body:
            self.visit(stmt)
        self.current_scope = prev_scope

    def visit_FunctionDecl(self, node):
        self.current_scope.define(node.name, 'FUNCTION')
        self.all_symbols.append({"name": node.name, "type": "FUNCTION", "scope": "Global", "kind": "Function"})
        prev_scope = self.current_scope
        self.current_scope = SymbolTable(parent=prev_scope)
        for param in node.params:
            self.current_scope.define(param, 'ANY')
            self.all_symbols.append({"name": param, "type": "ANY", "scope": f"Function '{node.name}'", "kind": "Parameter"})
        for stmt in node.body:
            self.visit(stmt)
        self.current_scope = prev_scope

    def visit_ReturnStmt(self, node):
        self.visit(node.value)
        return 'ANY'

    def visit_BinaryOp(self, node):
        left_type = self.visit(node.left)
        right_type = self.visit(node.right)
        if node.op in ('PLUS', 'MINUS', 'MUL', 'DIV', 'MOD'):
            return 'NUMBER'
        elif node.op in ('GT', 'LT', 'GTE', 'LTE', 'EQ', 'NEQ', 'AND', 'OR'):
            return 'BOOLEAN'
        return 'ANY'

    def visit_UnaryOp(self, node):
        return self.visit(node.right)

    def visit_Literal(self, node):
        if isinstance(node.value, (int, float)):
            return 'NUMBER'
        if isinstance(node.value, str):
            return 'STRING'
        return 'ANY'

    def visit_Identifier(self, node):
        var_type = self.current_scope.resolve(node.name)
        if var_type is None:
            self.errors.append(f"Undeclared variable '{node.name}'")
            return 'ANY'
        return var_type
        
    def visit_ArrayAccess(self, node):
        var_type = self.current_scope.resolve(node.name)
        if var_type is None:
            self.errors.append(f"Undeclared array '{node.name}'")
        self.visit(node.index)
        return 'ANY'

    def visit_FunctionCall(self, node):
        for arg in node.args:
            self.visit(arg)
        return 'ANY'
