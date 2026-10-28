from transpiler.ast_nodes import *

# Emitted once at the top of any generated program that uses READ.
_READ_HELPER = '''import sys as _sys

_input_buffer = []


def _read():
    while not _input_buffer:
        line = _sys.stdin.readline()
        if not line:
            raise EOFError("Program tried to read more input than was provided")
        _input_buffer.extend(line.split())
    tok = _input_buffer.pop(0)
    for cast in (int, float):
        try:
            return cast(tok)
        except ValueError:
            pass
    return tok
'''

class CodeGenerator:
    def __init__(self):
        self.uses_read = False
        self.code = []
        self.indent_level = 0
        self.imports = set()

    def add_line(self, line):
        self.code.append("    " * self.indent_level + line)

    def generate(self, node):
        self.visit(node)
        final_code = ""
        for imp in self.imports:
            final_code += f"import {imp}\n"
        if self.imports:
            final_code += "\n"
        if self.uses_read:
            final_code += _READ_HELPER + "\n\n"
        final_code += "\n".join(self.code)
        return final_code

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
        self.imports.add(node.module_name)

    def visit_Declare(self, node):
        if node.value:
            val_str = self.visit(node.value)
            self.add_line(f"{node.name} = {val_str}")
        else:
            self.add_line(f"{node.name} = None")

    def visit_Assign(self, node):
        val_str = self.visit(node.value)
        if node.index:
            idx_str = self.visit(node.index)
            self.add_line(f"{node.name}[{idx_str}] = {val_str}")
        else:
            self.add_line(f"{node.name} = {val_str}")

    def visit_Print(self, node):
        exprs = [self.visit(expr) for expr in node.expressions]
        self.add_line(f"print({', '.join(exprs)})")

    def visit_Read(self, node):
        self.uses_read = True
        self.add_line(f"{node.name} = _read()")

    def visit_IfStmt(self, node):
        cond_str = self.visit(node.condition)
        self.add_line(f"if {cond_str}:")
        self.indent_level += 1
        for stmt in node.then_branch:
            self.visit(stmt)
        if not node.then_branch:
            self.add_line("pass")
        self.indent_level -= 1
        
        for cond, body in node.else_ifs:
            cond_str = self.visit(cond)
            self.add_line(f"elif {cond_str}:")
            self.indent_level += 1
            for stmt in body:
                self.visit(stmt)
            if not body:
                self.add_line("pass")
            self.indent_level -= 1
            
        if node.else_branch:
            self.add_line("else:")
            self.indent_level += 1
            for stmt in node.else_branch:
                self.visit(stmt)
            if not node.else_branch:
                self.add_line("pass")
            self.indent_level -= 1

    def visit_WhileStmt(self, node):
        cond_str = self.visit(node.condition)
        self.add_line(f"while {cond_str}:")
        self.indent_level += 1
        for stmt in node.body:
            self.visit(stmt)
        if not node.body:
            self.add_line("pass")
        self.indent_level -= 1

    def visit_ForStmt(self, node):
        start_str = self.visit(node.start)
        end_str = self.visit(node.end)
        self.add_line(f"for {node.var} in range({start_str}, {end_str} + 1):")
        self.indent_level += 1
        for stmt in node.body:
            self.visit(stmt)
        if not node.body:
            self.add_line("pass")
        self.indent_level -= 1

    def visit_FunctionDecl(self, node):
        params_str = ", ".join(node.params)
        self.add_line(f"def {node.name}({params_str}):")
        self.indent_level += 1
        for stmt in node.body:
            self.visit(stmt)
        if not node.body:
            self.add_line("pass")
        self.indent_level -= 1

    def visit_ReturnStmt(self, node):
        val_str = self.visit(node.value)
        self.add_line(f"return {val_str}")

    def visit_BinaryOp(self, node):
        left = self.visit(node.left)
        right = self.visit(node.right)
        op_map = {
            'PLUS': '+', 'MINUS': '-', 'MUL': '*', 'DIV': '/', 'MOD': '%',
            'GT': '>', 'LT': '<', 'GTE': '>=', 'LTE': '<=', 'EQ': '==', 'NEQ': '!=',
            'AND': 'and', 'OR': 'or'
        }
        return f"({left} {op_map.get(node.op, node.op)} {right})"

    def visit_UnaryOp(self, node):
        right = self.visit(node.right)
        if node.op == 'NOT':
            return f"(not {right})"
        elif node.op == 'MINUS':
            return f"(-{right})"
        return right

    def visit_Literal(self, node):
        if isinstance(node.value, str):
            return f'"{node.value}"'
        return str(node.value)

    def visit_Identifier(self, node):
        return node.name
        
    def visit_ArrayAccess(self, node):
        idx = self.visit(node.index)
        return f"{node.name}[{idx}]"

    def visit_FunctionCall(self, node):
        args_str = ", ".join([self.visit(a) for a in node.args])
        return f"{node.name}({args_str})"
