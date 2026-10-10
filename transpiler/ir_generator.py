class TACGenerator:
    def __init__(self):
        self.instructions = []
        self.temp_count = 0
        self.label_count = 0
    def new_temp(self):
        self.temp_count += 1
        return f't{self.temp_count}'
    def new_label(self):
        self.label_count += 1
        return f'L{self.label_count}'
    def generate(self, ast):
        self.instructions = []
        if hasattr(ast, 'statements'):
            self.visit_list(ast.statements)
        return self.instructions
    def visit_list(self, nodes):
        for node in nodes:
            self.visit(node)
    def visit(self, node):
        if node is None: return None
        if isinstance(node, (int, float, str, bool)):
            return str(node)
        t = type(node).__name__
        if t == 'Assign':
            val = self.visit(node.value)
            self.instructions.append(f'{node.name} = {val}')
        elif t == 'Declare':
            if node.value:
                val = self.visit(node.value)
                self.instructions.append(f'{node.name} = {val}')
        elif t == 'BinaryOp':
            left = self.visit(node.left)
            right = self.visit(node.right)
            temp = self.new_temp()
            self.instructions.append(f'{temp} = {left} {node.op} {right}')
            return temp
        elif t == 'Identifier':
            return node.name
        elif t == 'Literal':
            return str(node.value)
        elif t == 'Print':
            for expr in node.expressions:
                val = self.visit(expr)
                self.instructions.append(f'PRINT {val}')
        elif t == 'Read':
            self.instructions.append(f'READ {node.name}')
        elif t == 'IfStmt':
            cond = self.visit(node.condition)
            l_true = self.new_label()
            l_false = self.new_label()
            l_end = self.new_label()
            self.instructions.append(f'IF {cond} GOTO {l_true}')
            self.instructions.append(f'GOTO {l_false}')
            self.instructions.append(f'{l_true}:')
            self.visit_list(node.then_branch)
            self.instructions.append(f'GOTO {l_end}')
            self.instructions.append(f'{l_false}:')
            if getattr(node, 'else_branch', None):
                self.visit_list(node.else_branch)
            self.instructions.append(f'{l_end}:')
        elif t == 'WhileStmt':
            l_start = self.new_label()
            l_true = self.new_label()
            l_end = self.new_label()
            self.instructions.append(f'{l_start}:')
            cond = self.visit(node.condition)
            self.instructions.append(f'IF {cond} GOTO {l_true}')
            self.instructions.append(f'GOTO {l_end}')
            self.instructions.append(f'{l_true}:')
            self.visit_list(node.body)
            self.instructions.append(f'GOTO {l_start}')
            self.instructions.append(f'{l_end}:')
        return None

class IROptimizer:
    def optimize(self, instructions):
        opt = []
        import re
        
        op_map = {
            'PLUS': '+', 'MINUS': '-', 'MULT': '*', 'DIV': '/',
            '+': '+', '-': '-', '*': '*', '/': '/'
        }
        
        for inst in instructions:
            match = re.match(r'^(\w+)\s*=\s*(\d+)\s*([A-Z]+|[\+\-\*/])\s*(\d+)$', inst)
            if match:
                var, v1, op_str, v2 = match.groups()
                if op_str in op_map:
                    try:
                        res = eval(f'{v1} {op_map[op_str]} {v2}')
                        if isinstance(res, float) and res.is_integer():
                            res = int(res)
                        opt.append(f'{var} = {res}')
                        continue
                    except:
                        pass
            opt.append(inst)
        return opt
