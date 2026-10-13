from transpiler.ast_nodes import *
from transpiler.symbol_table import SymbolTable

BUILTIN_FUNCTIONS = {
    'len': (1, 1, 'NUMBER'),
    'range': (1, 3, 'LIST'),
    'int': (0, 2, 'NUMBER'),
    'float': (0, 1, 'NUMBER'),
    'str': (0, 1, 'STRING'),
    'bool': (0, 1, 'BOOLEAN'),
    'list': (0, 1, 'LIST'),
    'tuple': (0, 1, 'TUPLE'),
    'set': (0, 1, 'ANY'),
    'dict': (0, 1, 'ANY'),
    'abs': (1, 1, 'NUMBER'),
    'min': (1, None, 'ANY'),
    'max': (1, None, 'ANY'),
    'sum': (1, 2, 'NUMBER'),
    'round': (1, 2, 'NUMBER'),
    'sorted': (1, 3, 'LIST'),
    'reversed': (1, 1, 'LIST'),
    'enumerate': (1, 2, 'LIST'),
    'zip': (1, None, 'LIST'),
    'type': (1, 1, 'STRING'),
    'ord': (1, 1, 'NUMBER'),
    'chr': (1, 1, 'STRING'),
    'input': (0, 1, 'STRING'),
    'print': (0, None, 'NONE'),
}

class SemanticAnalyzer:
    def __init__(self):
        self.global_scope = SymbolTable()
        self.current_scope = self.global_scope
        self.errors = []
        self.all_symbols = []
        self.functions = {}  # name -> (min_args, max_args, params)
        self.function_depth = 0
        self.loop_depth = 0
        self.collection_info = {}  # (id(scope), name) -> (type_str, static_len_or_None)

    def _set_collection_info(self, scope, name, col_type, length):
        self.collection_info[(id(scope), name)] = (col_type, length)

    def _get_collection_info(self, name):
        scope = self.current_scope
        while scope is not None:
            key = (id(scope), name)
            if key in self.collection_info:
                return self.collection_info[key]
            scope = scope.parent
        return None

    def _invalidate_collection_length(self, name):
        scope = self.current_scope
        while scope is not None:
            key = (id(scope), name)
            if key in self.collection_info:
                col_type, _ = self.collection_info[key]
                self.collection_info[key] = (col_type, None)
                return
            scope = scope.parent

    def analyze(self, node):
        self.visit(node)
        return self.errors

    def visit(self, node):
        if node is None:
            return 'NONE'
        method_name = f'visit_{type(node).__name__}'
        visitor = getattr(self, method_name, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node):
        return 'ANY'

    def visit_Program(self, node):
        # Pass 1: Pre-register top-level function declarations to support recursion and forward calls
        for stmt in node.statements:
            if isinstance(stmt, FunctionDecl):
                self._register_function_signature(stmt)

        # Pass 2: Analyze all statements
        for stmt in node.statements:
            self.visit(stmt)

    def _register_function_signature(self, node):
        if not isinstance(node.name, str) or not node.name.isidentifier():
            self.errors.append(f"Line {node.line}: Invalid function identifier '{node.name}'.")
            return

        if node.name in self.functions:
            self.errors.append(f"Line {node.line}: Duplicate function definition '{node.name}'.")
            return

        seen_params = set()
        for p in node.params:
            if not isinstance(p, str) or not p.isidentifier():
                self.errors.append(f"Line {node.line}: Invalid parameter identifier '{p}' in function '{node.name}'.")
            elif p in seen_params:
                self.errors.append(f"Line {node.line}: Duplicate parameter '{p}' in function '{node.name}'.")
            seen_params.add(p)

        defaults = getattr(node, 'defaults', None) or {}
        max_args = len(node.params)
        min_args = max_args - len(defaults)
        self.functions[node.name] = (min_args, max_args, list(node.params))
        self.global_scope.define(node.name, 'FUNCTION', line=node.line)
        self.all_symbols.append({
            "name": node.name,
            "type": "FUNCTION",
            "scope": "Global",
            "kind": "Function"
        })

    def visit_ImportStmt(self, node):
        allowed = ["math", "random", "time", "datetime"]
        root_mod = node.module_name.split('.')[0]
        if root_mod not in allowed:
            self.errors.append(f"Import '{node.module_name}' is not approved/allowed.")
        else:
            self.current_scope.define(root_mod, 'MODULE', line=node.line)
            self.all_symbols.append({
                "name": node.module_name,
                "type": "MODULE",
                "scope": "Global",
                "kind": "Import"
            })

    def visit_Declare(self, node):
        var_type = 'ANY'
        if node.value is not None:
            var_type = self.visit(node.value)
        success, err = self.current_scope.define(node.name, var_type, line=node.line)
        if not success:
            self.errors.append(err)
        else:
            scope_label = "Local" if self.function_depth > 0 else "Global"
            self.all_symbols.append({
                "name": node.name,
                "type": var_type,
                "scope": scope_label,
                "kind": "Variable"
            })
            if isinstance(node.value, TupleLiteral):
                self._set_collection_info(self.current_scope, node.name, 'TUPLE', len(node.value.elements))
            elif isinstance(node.value, ListLiteral):
                self._set_collection_info(self.current_scope, node.name, 'LIST', len(node.value.elements))

    def visit_Assign(self, node):
        val_type = self.visit(node.value)
        op = getattr(node, 'op', '=')
        target = getattr(node, 'target', None)

        # Indexed or sliced assignment: e.g. numbers[1] = 50 or nested[0][1] = 50
        if node.index is not None or isinstance(target, (ArrayAccess, SliceAccess)):
            var_type = self.current_scope.resolve(node.name)
            if var_type is None:
                self.errors.append(f"Line {node.line}: Undeclared variable '{node.name}'.")
            elif var_type == 'TUPLE':
                self.errors.append(f"Line {node.line}: Cannot modify tuple '{node.name}'; tuples are immutable.")
            elif var_type in ('NUMBER', 'BOOLEAN', 'NONE'):
                self.errors.append(f"Line {node.line}: Cannot index-assign into non-collection variable '{node.name}' of type {var_type}.")

            if target is not None:
                self.visit(target)
            elif node.index is not None:
                idx_type = self.visit(node.index)
                if isinstance(node.index, Literal) and not isinstance(node.index.value, int):
                    self.errors.append(f"Line {node.line}: Index must be an integer.")
            return

        # Compound assignment (+=, -=, *=, /=) requires variable to already exist
        if op != '=':
            existing_type = self.current_scope.resolve(node.name)
            if existing_type is None:
                self.errors.append(
                    f"Line {node.line}: Undeclared variable '{node.name}' used in compound assignment '{op}'."
                )
            return

        # Regular assignment: Python-like function-local scope rules
        if self.function_depth > 0:
            # Inside a function, assignment binds in local scope unless already local
            if node.name in self.current_scope.symbols:
                self.current_scope.symbols[node.name] = val_type or 'ANY'
            else:
                inferred = val_type or 'ANY'
                self.current_scope.define(node.name, inferred, line=node.line)
                self.all_symbols.append({
                    "name": node.name,
                    "type": inferred,
                    "scope": "Local",
                    "kind": "Variable (Local)"
                })
        else:
            var_type = self.current_scope.resolve(node.name)
            if var_type is None:
                inferred = val_type or 'ANY'
                self.current_scope.define(node.name, inferred, line=node.line)
                self.all_symbols.append({
                    "name": node.name,
                    "type": inferred,
                    "scope": "Global",
                    "kind": "Variable (Implicit)"
                })
            else:
                if val_type:
                    self.current_scope.update(node.name, val_type)

        if isinstance(node.value, TupleLiteral):
            self._set_collection_info(self.current_scope, node.name, 'TUPLE', len(node.value.elements))
        elif isinstance(node.value, ListLiteral):
            self._set_collection_info(self.current_scope, node.name, 'LIST', len(node.value.elements))
        else:
            self._invalidate_collection_length(node.name)

    def visit_TupleUnpackAssign(self, node):
        rhs_type = self.visit(node.value)
        expected_count = len(node.targets)

        rhs_len = None
        if isinstance(node.value, (TupleLiteral, ListLiteral)):
            rhs_len = len(node.value.elements)
        elif isinstance(node.value, Identifier):
            info = self._get_collection_info(node.value.name)
            if info is not None:
                rhs_len = info[1]

        if rhs_type in ('NUMBER', 'BOOLEAN', 'NONE'):
            self.errors.append(
                f"Line {node.line}: Cannot unpack non-iterable value of type {rhs_type}."
            )
        elif rhs_len is not None and rhs_len != expected_count:
            self.errors.append(
                f"Line {node.line}: Tuple unpacking mismatch: expected {expected_count} values to unpack, but got {rhs_len}."
            )

        scope_label = "Local" if self.function_depth > 0 else "Global"
        for target_name in node.targets:
            if not target_name.isidentifier():
                self.errors.append(f"Line {node.line}: Invalid identifier '{target_name}' in tuple unpacking.")
                continue
            if self.function_depth > 0:
                if target_name not in self.current_scope.symbols:
                    self.current_scope.define(target_name, 'ANY', line=node.line)
                    self.all_symbols.append({
                        "name": target_name,
                        "type": "ANY",
                        "scope": scope_label,
                        "kind": "Variable (Unpacked)"
                    })
            else:
                if self.current_scope.resolve(target_name) is None:
                    self.current_scope.define(target_name, 'ANY', line=node.line)
                    self.all_symbols.append({
                        "name": target_name,
                        "type": "ANY",
                        "scope": scope_label,
                        "kind": "Variable (Unpacked)"
                    })

    def visit_Print(self, node):
        for expr in node.expressions:
            self.visit(expr)

    def visit_Read(self, node):
        var_type = self.current_scope.resolve(node.name)
        if var_type is None:
            self.current_scope.define(node.name, 'STRING', line=node.line)
            scope_label = "Local" if self.function_depth > 0 else "Global"
            self.all_symbols.append({
                "name": node.name,
                "type": "STRING",
                "scope": scope_label,
                "kind": "Variable (Implicit)"
            })

    def visit_IfStmt(self, node):
        self.visit(node.condition)
        for stmt in node.then_branch:
            self.visit(stmt)
        for cond, body in node.else_ifs:
            self.visit(cond)
            for stmt in body:
                self.visit(stmt)
        if node.else_branch:
            for stmt in node.else_branch:
                self.visit(stmt)

    def visit_WhileStmt(self, node):
        self.visit(node.condition)
        self.loop_depth += 1
        for stmt in node.body:
            self.visit(stmt)
        self.loop_depth -= 1

    def _is_statically_zero(self, expr):
        if expr is None:
            return False
        if isinstance(expr, Literal) and isinstance(expr.value, (int, float)) and not isinstance(expr.value, bool):
            return expr.value == 0
        if isinstance(expr, UnaryOp) and expr.op in ('MINUS', 'PLUS'):
            return self._is_statically_zero(expr.right)
        return False

    def visit_ForStmt(self, node):
        self.visit(node.start)
        self.visit(node.end)
        if getattr(node, 'step', None) is not None:
            self.visit(node.step)
            if self._is_statically_zero(node.step):
                self.errors.append(f"Line {node.line}: Numeric range step cannot be zero.")

        if node.var not in self.current_scope.symbols:
            self.current_scope.define(node.var, 'NUMBER', line=node.line)
            self.all_symbols.append({
                "name": node.var,
                "type": "NUMBER",
                "scope": "Local" if self.function_depth > 0 else "Global",
                "kind": "Loop Variable"
            })
        else:
            self.current_scope.update(node.var, 'NUMBER')

        self.loop_depth += 1
        for stmt in node.body:
            self.visit(stmt)
        self.loop_depth -= 1

    def visit_ForEachStmt(self, node):
        iter_type = self.visit(node.iterable)
        if iter_type in ('NUMBER', 'BOOLEAN', 'NONE'):
            self.errors.append(
                f"Line {node.line}: Cannot iterate over non-iterable value of type {iter_type}."
            )

        loop_vars = node.unpack_vars if getattr(node, 'unpack_vars', None) else [node.var]
        for v in loop_vars:
            if v not in self.current_scope.symbols:
                self.current_scope.define(v, 'ANY', line=node.line)
                self.all_symbols.append({
                    "name": v,
                    "type": "ANY",
                    "scope": "Local" if self.function_depth > 0 else "Global",
                    "kind": "Loop Variable"
                })

        self.loop_depth += 1
        for stmt in node.body:
            self.visit(stmt)
        self.loop_depth -= 1

    def visit_FunctionDecl(self, node):
        # If nested function or not yet registered, register signature
        if node.name not in self.functions and self.function_depth > 0:
            self._register_function_signature(node)

        defaults = getattr(node, 'defaults', None) or {}
        for def_expr in defaults.values():
            self.visit(def_expr)

        prev_scope = self.current_scope
        self.current_scope = SymbolTable(parent=prev_scope)
        for param in node.params:
            if param not in self.current_scope.symbols:
                self.current_scope.define(param, 'ANY', line=node.line)
                self.all_symbols.append({
                    "name": param,
                    "type": "ANY",
                    "scope": f"Function '{node.name}'",
                    "kind": "Parameter"
                })

        self.function_depth += 1
        for stmt in node.body:
            self.visit(stmt)
        self.function_depth -= 1
        self.current_scope = prev_scope

    def visit_ReturnStmt(self, node):
        if self.function_depth == 0:
            self.errors.append(f"Line {node.line}: RETURN used outside a function.")
        if node.value is not None:
            return self.visit(node.value)
        return 'NONE'

    def visit_BreakStmt(self, node):
        if self.loop_depth == 0:
            self.errors.append(f"Line {node.line}: BREAK used outside a loop.")

    def visit_ContinueStmt(self, node):
        if self.loop_depth == 0:
            self.errors.append(f"Line {node.line}: CONTINUE used outside a loop.")

    def visit_BinaryOp(self, node):
        left_type = self.visit(node.left)
        right_type = self.visit(node.right)
        if node.op in ('PLUS', 'MINUS', 'MUL', 'DIV', 'FLOORDIV', 'MOD', 'POW'):
            if node.op == 'PLUS' and (left_type == 'STRING' or right_type == 'STRING'):
                return 'STRING'
            if node.op == 'PLUS' and (left_type == 'LIST' and right_type == 'LIST'):
                return 'LIST'
            if node.op == 'PLUS' and (left_type == 'TUPLE' and right_type == 'TUPLE'):
                return 'TUPLE'
            return 'NUMBER'
        elif node.op in ('GT', 'LT', 'GTE', 'LTE', 'EQ', 'NEQ', 'AND', 'OR', 'IN', 'NOT_IN'):
            return 'BOOLEAN'
        return 'ANY'

    def visit_UnaryOp(self, node):
        right_type = self.visit(node.right)
        if node.op == 'NOT':
            return 'BOOLEAN'
        return right_type

    def visit_Literal(self, node):
        if node.value is None:
            return 'NONE'
        if isinstance(node.value, bool):
            return 'BOOLEAN'
        if isinstance(node.value, (int, float)):
            return 'NUMBER'
        if isinstance(node.value, str):
            return 'STRING'
        return 'ANY'

    def visit_ListLiteral(self, node):
        for el in node.elements:
            self.visit(el)
        return 'LIST'

    def visit_TupleLiteral(self, node):
        for el in node.elements:
            self.visit(el)
        return 'TUPLE'

    def visit_Identifier(self, node):
        var_type = self.current_scope.resolve(node.name)
        if var_type is None:
            if node.name.lower() in BUILTIN_FUNCTIONS:
                return 'FUNCTION'
            self.errors.append(f"Undeclared variable '{node.name}'")
            return 'ANY'
        return var_type

    def visit_ArrayAccess(self, node):
        target = getattr(node, 'target', None)
        if target is not None and not isinstance(target, Identifier):
            var_type = self.visit(target)
        else:
            var_type = self.current_scope.resolve(node.name)
            if var_type is None:
                self.errors.append(f"Undeclared array '{node.name}'")
                var_type = 'ANY'

        if var_type in ('NUMBER', 'BOOLEAN', 'NONE'):
            self.errors.append(
                f"Line {node.line}: Cannot index into non-indexable value of type {var_type}."
            )

        idx_type = self.visit(node.index)
        if isinstance(node.index, Literal) and (isinstance(node.index.value, (float, str, bool)) or node.index.value is None):
            self.errors.append(
                f"Line {node.line}: Collection index must be an integer, got {type(node.index.value).__name__}."
            )
        return 'ANY'

    def visit_SliceAccess(self, node):
        target_type = self.visit(node.target)
        if target_type in ('NUMBER', 'BOOLEAN', 'NONE'):
            self.errors.append(
                f"Line {node.line}: Cannot slice non-sequence value of type {target_type}."
            )
        if node.start is not None:
            self.visit(node.start)
        if node.stop is not None:
            self.visit(node.stop)
        if node.step is not None:
            self.visit(node.step)
            if self._is_statically_zero(node.step):
                self.errors.append(f"Line {node.line}: Slice step cannot be zero.")
        return target_type if target_type in ('LIST', 'TUPLE', 'STRING') else 'ANY'

    def visit_FunctionCall(self, node):
        for arg in node.args:
            self.visit(arg)

        if node.name in self.functions:
            min_args, max_args, _ = self.functions[node.name]
            actual = len(node.args)
            if actual < min_args or actual > max_args:
                if min_args == max_args:
                    self.errors.append(
                        f"Line {node.line}: Function '{node.name}' expects {min_args} arguments but received {actual}."
                    )
                else:
                    self.errors.append(
                        f"Line {node.line}: Function '{node.name}' expects {min_args} to {max_args} arguments but received {actual}."
                    )
            return 'ANY'

        lower_name = node.name.lower()
        if lower_name in BUILTIN_FUNCTIONS:
            min_a, max_a, ret_type = BUILTIN_FUNCTIONS[lower_name]
            actual = len(node.args)
            if actual < min_a or (max_a is not None and actual > max_a):
                self.errors.append(
                    f"Line {node.line}: Built-in function '{node.name}' expects {min_a}{'' if max_a == min_a else f' to {max_a}'} argument(s) but received {actual}."
                )
            return ret_type

        resolved = self.current_scope.resolve(node.name)
        if resolved is None:
            self.errors.append(f"Line {node.line}: Undefined function '{node.name}'.")
        elif resolved in ('NUMBER', 'STRING', 'BOOLEAN', 'LIST', 'TUPLE', 'NONE'):
            self.errors.append(f"Line {node.line}: Variable '{node.name}' of type {resolved} is not callable.")
        return 'ANY'

    def visit_MethodCall(self, node):
        obj_type = self.visit(node.obj)
        for arg in node.args:
            self.visit(arg)

        mutating_list_methods = {'append', 'remove', 'pop', 'insert', 'extend', 'clear', 'sort', 'reverse'}
        if node.method in mutating_list_methods:
            if obj_type == 'TUPLE':
                self.errors.append(
                    f"Line {node.line}: Cannot call '{node.method}' on tuple; tuples are immutable."
                )
            elif obj_type in ('NUMBER', 'BOOLEAN', 'NONE', 'STRING'):
                self.errors.append(
                    f"Line {node.line}: Type {obj_type} does not support list method '{node.method}'."
                )
            if isinstance(node.obj, Identifier):
                self._invalidate_collection_length(node.obj.name)

        return 'ANY'

    def visit_AttributeAccess(self, node):
        self.visit(node.obj)
        return 'ANY'
