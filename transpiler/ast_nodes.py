class ASTNode:
    line = 0
    column = 0

class Program(ASTNode):
    def __init__(self, statements):
        self.statements = statements

class Declare(ASTNode):
    def __init__(self, name, value=None, line=0):
        self.name = name
        self.value = value
        self.line = line

class ImportStmt(ASTNode):
    def __init__(self, module_name, line=0):
        self.module_name = module_name
        self.line = line

class Assign(ASTNode):
    def __init__(self, name, value, index=None, op='=', target=None, line=0):
        self.name = name
        self.value = value
        self.index = index
        self.op = op
        self.target = target
        self.line = line

class TupleUnpackAssign(ASTNode):
    def __init__(self, targets, value, line=0):
        self.targets = targets
        self.name = ", ".join(targets)
        self.value = value
        self.line = line

class Print(ASTNode):
    def __init__(self, expressions, line=0):
        self.expressions = expressions
        self.line = line

class Read(ASTNode):
    def __init__(self, name, prompt=None, line=0):
        self.name = name
        self.prompt = prompt
        self.line = line

class IfStmt(ASTNode):
    def __init__(self, condition, then_branch, else_ifs=None, else_branch=None, line=0):
        self.condition = condition
        self.then_branch = then_branch
        self.else_ifs = else_ifs or []  # list of (condition, branch)
        self.else_branch = else_branch
        self.line = line

class WhileStmt(ASTNode):
    def __init__(self, condition, body, line=0):
        self.condition = condition
        self.body = body
        self.line = line

class ForStmt(ASTNode):
    def __init__(self, var, start, end, body, step=None, inclusive=False, descending=False, line=0):
        self.var = var
        self.start = start
        self.end = end
        self.body = body
        self.step = step
        self.inclusive = inclusive
        self.descending = descending
        self.line = line

class ForEachStmt(ASTNode):
    def __init__(self, var, iterable, body, unpack_vars=None, line=0):
        self.var = var
        self.unpack_vars = unpack_vars  # Optional list of var names if tuple unpacking in loop
        self.iterable = iterable
        self.body = body
        self.line = line

class FunctionDecl(ASTNode):
    def __init__(self, name, params, body, defaults=None, line=0):
        self.name = name
        self.params = params
        self.body = body
        self.defaults = defaults or {}  # dict mapping param_name -> default AST expr
        self.line = line

class FunctionCall(ASTNode):
    def __init__(self, name, args, line=0):
        self.name = name
        self.args = args
        self.line = line

class MethodCall(ASTNode):
    def __init__(self, obj, method, args, line=0):
        self.obj = obj
        self.method = method
        self.args = args
        self.name = f"{getattr(obj, 'name', 'expr')}.{method}"
        self.line = line

class AttributeAccess(ASTNode):
    def __init__(self, obj, attr, line=0):
        self.obj = obj
        self.attr = attr
        self.line = line

class ReturnStmt(ASTNode):
    def __init__(self, value=None, line=0):
        self.value = value
        self.line = line

class BreakStmt(ASTNode):
    def __init__(self, line=0):
        self.line = line

class ContinueStmt(ASTNode):
    def __init__(self, line=0):
        self.line = line

class BinaryOp(ASTNode):
    def __init__(self, left, op, right, line=0):
        self.left = left
        self.op = op
        self.right = right
        self.line = line

class UnaryOp(ASTNode):
    def __init__(self, op, right, line=0):
        self.op = op
        self.right = right
        self.line = line

class Literal(ASTNode):
    def __init__(self, value, raw_type=None, line=0):
        self.value = value
        self.raw_type = raw_type
        self.line = line

class ListLiteral(ASTNode):
    def __init__(self, elements, line=0):
        self.elements = elements
        self.line = line

class TupleLiteral(ASTNode):
    def __init__(self, elements, line=0):
        self.elements = elements
        self.line = line

class Identifier(ASTNode):
    def __init__(self, name, line=0):
        self.name = name
        self.line = line

class ArrayAccess(ASTNode):
    def __init__(self, name, index, target=None, line=0):
        self.name = name
        self.index = index
        self.target = target  # ASTNode when indexing arbitrary expression or chained indexing
        self.line = line

class SliceAccess(ASTNode):
    def __init__(self, target, start=None, stop=None, step=None, line=0):
        self.target = target
        self.name = getattr(target, 'name', 'seq')
        self.start = start
        self.stop = stop
        self.step = step
        self.line = line
