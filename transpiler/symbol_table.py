class SymbolTable:
    def __init__(self, parent=None):
        self.symbols = {}
        self.parent = parent

    def define(self, name, type_info, line=0):
        if name in self.symbols:
            return False, f"Duplicate declaration of '{name}' at line {line}"
        self.symbols[name] = type_info
        return True, ""

    def resolve(self, name):
        if name in self.symbols:
            return self.symbols[name]
        if self.parent:
            return self.parent.resolve(name)
        return None

    def update(self, name, type_info):
        if name in self.symbols:
            self.symbols[name] = type_info
            return True
        if self.parent:
            return self.parent.update(name, type_info)
        return False
