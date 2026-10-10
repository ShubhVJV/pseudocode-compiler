class CFGBuilder:
    def __init__(self):
        self.lines = ['flowchart TD', '  START([Start])']
        self.counter = 0
        
    def get_id(self):
        self.counter += 1
        return f'N{self.counter}'

    def build(self, node, current_heads):
        if isinstance(node, list):
            for stmt in node:
                current_heads = self.build(stmt, current_heads)
            return current_heads
            
        if not hasattr(node, '__dict__'):
            return current_heads
            
        t = type(node).__name__
        node_id = self.get_id()
        
        if t in ['Assign', 'Declare']:
            self.lines.append(f'  {node_id}["{t}: {node.name}"]')
            for h in current_heads:
                self.lines.append(f'  {h} --> {node_id}')
            return [node_id]
            
        elif t == 'Print':
            self.lines.append(f'  {node_id}["Print"]')
            for h in current_heads:
                self.lines.append(f'  {h} --> {node_id}')
            return [node_id]
            
        elif t == 'Read':
            self.lines.append(f'  {node_id}["Read: {node.name}"]')
            for h in current_heads:
                self.lines.append(f'  {h} --> {node_id}')
            return [node_id]
            
        elif t == 'IfStmt':
            self.lines.append(f'  {node_id}{{"If Condition"}}')
            for h in current_heads:
                self.lines.append(f'  {h} --> {node_id}')
            
            # True branch
            true_heads = self.build(node.then_branch, [node_id])
            for h in true_heads:
                if h != node_id:
                    self.lines[-1] = self.lines[-1].replace(f'--> {true_heads[0]}', f'-- True --> {true_heads[0]}')
            
            # False branch
            if node.else_branch:
                false_heads = self.build(node.else_branch, [node_id])
                for h in false_heads:
                    if h != node_id:
                        self.lines[-1] = self.lines[-1].replace(f'--> {false_heads[0]}', f'-- False --> {false_heads[0]}')
            else:
                false_heads = [node_id] # Pass-through
                
            return true_heads + false_heads
            
        elif t == 'WhileStmt':
            self.lines.append(f'  {node_id}{{"While Loop"}}')
            for h in current_heads:
                self.lines.append(f'  {h} --> {node_id}')
                
            body_heads = self.build(node.body, [node_id])
            for h in body_heads:
                self.lines.append(f'  {h} --> {node_id}') # loop back
                
            return [node_id] # Exit path
            
        elif t == 'ForStmt':
            self.lines.append(f'  {node_id}{{"For Loop: {node.var}"}}')
            for h in current_heads:
                self.lines.append(f'  {h} --> {node_id}')
                
            body_heads = self.build(node.body, [node_id])
            for h in body_heads:
                self.lines.append(f'  {h} --> {node_id}') # loop back
                
            return [node_id] # Exit path
            
        elif t == 'FunctionDecl':
            self.lines.append(f'  {node_id}(["Function: {node.name}"])')
            self.build(node.body, [node_id])
            return current_heads
            
        elif t == 'ReturnStmt':
            self.lines.append(f'  {node_id}(["Return"])')
            for h in current_heads:
                self.lines.append(f'  {h} --> {node_id}')
            return []
            
        elif t == 'FunctionCall':
            self.lines.append(f'  {node_id}["Call: {node.name}"]')
            for h in current_heads:
                self.lines.append(f'  {h} --> {node_id}')
            return [node_id]
            
        else:
            self.lines.append(f'  {node_id}["{t}"]')
            for h in current_heads:
                self.lines.append(f'  {h} --> {node_id}')
            return [node_id]

    def generate(self, ast_prog):
        heads = self.build(ast_prog.statements, ['START'])
        self.lines.append('  END([End])')
        for h in heads:
            self.lines.append(f'  {h} --> END')
        return '\n'.join(self.lines)

def generate_cfg(ast):
    if not ast:
        return ""
    builder = CFGBuilder()
    return builder.generate(ast)
