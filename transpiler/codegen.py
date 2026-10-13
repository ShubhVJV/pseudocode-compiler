from transpiler.ast_nodes import *
from transpiler.semantic import BUILTIN_FUNCTIONS

class CodeGenerator:
    def __init__(self):
        self.code = []
        self.indent_level = 0
        self.imports = []
        self.defined_functions = set()

    def add_line(self, line):
        self.code.append("    " * self.indent_level + line)

    def generate(self, node):
        if hasattr(node, 'statements'):
            for stmt in node.statements:
                if isinstance(stmt, FunctionDecl):
                    self.defined_functions.add(stmt.name)
        self.visit(node)
        final_code = ""
        for imp in self.imports:
            final_code += f"import {imp}\n"
        if self.imports:
            final_code += "\n"
        final_code += "\n".join(self.code)
        return final_code

    def visit(self, node):
        if node is None:
            return "None"
        method_name = f'visit_{type(node).__name__}'
        visitor = getattr(self, method_name, self.generic_visit)
        return visitor(node)

    def visit_stmt(self, stmt):
        res = self.visit(stmt)
        if isinstance(stmt, (FunctionCall, MethodCall)) and isinstance(res, str):
            self.add_line(res)

    def generic_visit(self, node):
        return ""

    def visit_Program(self, node):
        for stmt in node.statements:
            self.visit_stmt(stmt)

    def visit_ImportStmt(self, node):
        if node.module_name not in self.imports:
            self.imports.append(node.module_name)

    def visit_Declare(self, node):
        if node.value is not None:
            val_str = self.visit(node.value)
            self.add_line(f"{node.name} = {val_str}")
        else:
            self.add_line(f"{node.name} = None")

    def visit_Assign(self, node):
        val_str = self.visit(node.value)
        op = getattr(node, 'op', '=')
        target = getattr(node, 'target', None)
        if target is not None and isinstance(target, (ArrayAccess, SliceAccess, AttributeAccess)):
            lhs_str = self.visit(target)
            self.add_line(f"{lhs_str} {op} {val_str}")
        elif node.index is not None:
            idx_str = self.visit(node.index)
            self.add_line(f"{node.name}[{idx_str}] {op} {val_str}")
        else:
            self.add_line(f"{node.name} {op} {val_str}")

    def visit_TupleUnpackAssign(self, node):
        targets_str = ", ".join(node.targets)
        val_str = self.visit(node.value)
        self.add_line(f"{targets_str} = {val_str}")

    def visit_Print(self, node):
        exprs = [self.visit(expr) for expr in node.expressions]
        self.add_line(f"print({', '.join(exprs)})")

    def visit_Read(self, node):
        if getattr(node, 'prompt', None) is not None:
            p_str = self.visit(node.prompt)
            self.add_line(f"{node.name} = input({p_str})")
        else:
            self.add_line(f"{node.name} = input()")

    def visit_IfStmt(self, node):
        cond_str = self.visit(node.condition)
        self.add_line(f"if {cond_str}:")
        self.indent_level += 1
        for stmt in node.then_branch:
            self.visit_stmt(stmt)
        if not node.then_branch:
            self.add_line("pass")
        self.indent_level -= 1

        for cond, body in node.else_ifs:
            cond_str = self.visit(cond)
            self.add_line(f"elif {cond_str}:")
            self.indent_level += 1
            for stmt in body:
                self.visit_stmt(stmt)
            if not body:
                self.add_line("pass")
            self.indent_level -= 1

        if node.else_branch:
            self.add_line("else:")
            self.indent_level += 1
            for stmt in node.else_branch:
                self.visit_stmt(stmt)
            if not node.else_branch:
                self.add_line("pass")
            self.indent_level -= 1

    def visit_WhileStmt(self, node):
        cond_str = self.visit(node.condition)
        self.add_line(f"while {cond_str}:")
        self.indent_level += 1
        for stmt in node.body:
            self.visit_stmt(stmt)
        if not node.body:
            self.add_line("pass")
        self.indent_level -= 1

    def _extract_static_number(self, expr):
        if isinstance(expr, Literal) and isinstance(expr.value, (int, float)) and not isinstance(expr.value, bool):
            return expr.value
        if isinstance(expr, UnaryOp) and expr.op == 'MINUS':
            sub = self._extract_static_number(expr.right)
            if sub is not None:
                return -sub
        if isinstance(expr, UnaryOp) and expr.op == 'PLUS':
            return self._extract_static_number(expr.right)
        return None

    def visit_ForStmt(self, node):
        start_str = self.visit(node.start)
        inclusive = getattr(node, 'inclusive', False)
        descending = getattr(node, 'descending', False)
        step_node = getattr(node, 'step', None)

        step_str = None
        is_neg = descending

        if descending:
            if step_node is None:
                step_str = "-1"
            else:
                num = self._extract_static_number(step_node)
                if num is not None:
                    step_str = str(-abs(num))
                else:
                    step_str = f"-abs({self.visit(step_node)})"
        else:
            if step_node is not None:
                num = self._extract_static_number(step_node)
                if num is not None:
                    step_str = str(num)
                    is_neg = num < 0
                else:
                    step_str = self.visit(step_node)
                    is_neg = step_str.startswith('(-') or step_str.startswith('-')

        end_num = self._extract_static_number(node.end)
        if not inclusive:
            stop_str = self.visit(node.end)
        else:
            if not is_neg:
                if isinstance(end_num, int):
                    stop_str = str(end_num + 1)
                else:
                    stop_str = f"{self.visit(node.end)} + 1"
            else:
                if isinstance(end_num, int):
                    stop_str = str(end_num - 1)
                else:
                    stop_str = f"{self.visit(node.end)} - 1"

        if step_str is None:
            self.add_line(f"for {node.var} in range({start_str}, {stop_str}):")
        else:
            self.add_line(f"for {node.var} in range({start_str}, {stop_str}, {step_str}):")

        self.indent_level += 1
        for stmt in node.body:
            self.visit_stmt(stmt)
        if not node.body:
            self.add_line("pass")
        self.indent_level -= 1

    def visit_ForEachStmt(self, node):
        target_str = ", ".join(node.unpack_vars) if getattr(node, 'unpack_vars', None) else node.var
        iter_str = self.visit(node.iterable)
        self.add_line(f"for {target_str} in {iter_str}:")
        self.indent_level += 1
        for stmt in node.body:
            self.visit_stmt(stmt)
        if not node.body:
            self.add_line("pass")
        self.indent_level -= 1

    def visit_FunctionDecl(self, node):
        self.defined_functions.add(node.name)
        defaults = getattr(node, 'defaults', None) or {}
        param_strs = []
        for p in node.params:
            if p in defaults:
                param_strs.append(f"{p}={self.visit(defaults[p])}")
            else:
                param_strs.append(p)
        params_str = ", ".join(param_strs)
        self.add_line(f"def {node.name}({params_str}):")
        self.indent_level += 1
        for stmt in node.body:
            self.visit_stmt(stmt)
        if not node.body:
            self.add_line("pass")
        self.indent_level -= 1

    def visit_ReturnStmt(self, node):
        if node.value is None:
            self.add_line("return")
        else:
            val_str = self.visit(node.value)
            self.add_line(f"return {val_str}")

    def visit_BreakStmt(self, node):
        self.add_line("break")

    def visit_ContinueStmt(self, node):
        self.add_line("continue")

    def visit_BinaryOp(self, node):
        left = self.visit(node.left)
        right = self.visit(node.right)
        op_map = {
            'PLUS': '+', 'MINUS': '-', 'MUL': '*', 'DIV': '/',
            'FLOORDIV': '//', 'MOD': '%', 'POW': '**',
            'GT': '>', 'LT': '<', 'GTE': '>=', 'LTE': '<=',
            'EQ': '==', 'NEQ': '!=',
            'AND': 'and', 'OR': 'or',
            'IN': 'in', 'NOT_IN': 'not in',
        }
        return f"({left} {op_map.get(node.op, node.op)} {right})"

    def visit_UnaryOp(self, node):
        right = self.visit(node.right)
        if node.op == 'NOT':
            return f"(not {right})"
        elif node.op == 'MINUS':
            if isinstance(node.right, Literal) and isinstance(node.right.value, (int, float)):
                return f"-{right}"
            return f"(-{right})"
        elif node.op == 'PLUS':
            return f"(+{right})"
        return right

    def visit_Literal(self, node):
        if node.value is None:
            return "None"
        if isinstance(node.value, bool):
            return "True" if node.value else "False"
        if isinstance(node.value, str):
            if '"' not in node.value and '\n' not in node.value and '\r' not in node.value and '\\' not in node.value:
                return f'"{node.value}"'
            return repr(node.value)
        return str(node.value)

    def visit_ListLiteral(self, node):
        elems = ", ".join(self.visit(e) for e in node.elements)
        return f"[{elems}]"

    def visit_TupleLiteral(self, node):
        if len(node.elements) == 0:
            return "()"
        if len(node.elements) == 1:
            return f"({self.visit(node.elements[0])},)"
        elems = ", ".join(self.visit(e) for e in node.elements)
        return f"({elems})"

    def visit_Identifier(self, node):
        return node.name

    def visit_ArrayAccess(self, node):
        target = getattr(node, 'target', None)
        target_str = self.visit(target) if target is not None else node.name
        idx = self.visit(node.index)
        return f"{target_str}[{idx}]"

    def visit_SliceAccess(self, node):
        target_str = self.visit(node.target)
        start_str = self.visit(node.start) if node.start is not None else ""
        stop_str = self.visit(node.stop) if node.stop is not None else ""
        if node.step is not None:
            step_str = self.visit(node.step)
            return f"{target_str}[{start_str}:{stop_str}:{step_str}]"
        return f"{target_str}[{start_str}:{stop_str}]"

    def visit_FunctionCall(self, node):
        args_str = ", ".join([self.visit(a) for a in node.args])
        callee_name = node.name
        if callee_name not in self.defined_functions and callee_name.lower() in BUILTIN_FUNCTIONS:
            callee_name = callee_name.lower()
        return f"{callee_name}({args_str})"

    def visit_MethodCall(self, node):
        obj_str = self.visit(node.obj)
        args_str = ", ".join([self.visit(a) for a in node.args])
        return f"{obj_str}.{node.method.lower() if node.method.upper() in ('APPEND', 'REMOVE') else node.method}({args_str})"

    def visit_AttributeAccess(self, node):
        obj_str = self.visit(node.obj)
        return f"{obj_str}.{node.attr}"
