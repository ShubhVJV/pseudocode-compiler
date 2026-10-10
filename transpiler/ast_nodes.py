class ASTNode:
    pass

class Program(ASTNode):
    def __init__(self, statements):
        self.statements = statements

class Declare(ASTNode):
    def __init__(self, name, value=None):
        self.name = name
        self.value = value

class ImportStmt(ASTNode):
    def __init__(self, module_name):
        self.module_name = module_name

class Assign(ASTNode):
    def __init__(self, name, value, index=None):
        self.name = name
        self.value = value
        self.index = index

class Print(ASTNode):
    def __init__(self, expressions):
        self.expressions = expressions

class Read(ASTNode):
    def __init__(self, name):
        self.name = name

class IfStmt(ASTNode):
    def __init__(self, condition, then_branch, else_ifs=None, else_branch=None):
        self.condition = condition
        self.then_branch = then_branch
        self.else_ifs = else_ifs or [] # list of (condition, branch)
        self.else_branch = else_branch

class WhileStmt(ASTNode):
    def __init__(self, condition, body):
        self.condition = condition
        self.body = body

class ForStmt(ASTNode):
    def __init__(self, var, start, end, body):
        self.var = var
        self.start = start
        self.end = end
        self.body = body

class FunctionDecl(ASTNode):
    def __init__(self, name, params, body):
        self.name = name
        self.params = params
        self.body = body

class FunctionCall(ASTNode):
    def __init__(self, name, args):
        self.name = name
        self.args = args

class ReturnStmt(ASTNode):
    def __init__(self, value):
        self.value = value

class BinaryOp(ASTNode):
    def __init__(self, left, op, right):
        self.left = left
        self.op = op
        self.right = right

class UnaryOp(ASTNode):
    def __init__(self, op, right):
        self.op = op
        self.right = right

class Literal(ASTNode):
    def __init__(self, value):
        self.value = value

class Identifier(ASTNode):
    def __init__(self, name):
        self.name = name

class ArrayAccess(ASTNode):
    def __init__(self, name, index):
        self.name = name
        self.index = index
