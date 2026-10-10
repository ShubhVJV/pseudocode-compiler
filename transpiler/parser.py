from transpiler.ast_nodes import *

class ParseError(Exception):
    pass

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.errors = []

    def current_token(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return self.tokens[-1]

    def consume(self, expected_type=None):
        tok = self.current_token()
        if expected_type and tok.type != expected_type:
            self.errors.append(f"Syntax Error at line {tok.line}: Expected {expected_type}, got {tok.type}")
            # Try to recover by just advancing, though not ideal
            self.pos += 1
            return tok
        self.pos += 1
        return tok

    def match(self, *expected_types):
        tok = self.current_token()
        if tok.type in expected_types:
            self.pos += 1
            return True
        return False

    def parse(self):
        statements = []
        # Optional START token
        if self.current_token().type == 'START':
            self.consume('START')
            
        while self.current_token().type not in ('EOF', 'STOP'):
            stmt = self.parse_statement()
            if stmt:
                statements.append(stmt)
            else:
                # If we couldn't parse a statement, advance to avoid infinite loop
                self.pos += 1
                
        if self.current_token().type == 'STOP':
            self.consume('STOP')
            
        return Program(statements), self.errors

    def parse_statement(self):
        tok = self.current_token()
        
        if tok.type == 'IMPORT':
            return self.parse_import()
        elif tok.type == 'DECLARE':
            return self.parse_declare()
        elif tok.type == 'SET':
            return self.parse_set()
        elif tok.type == 'PRINT':
            return self.parse_print()
        elif tok.type == 'READ':
            return self.parse_read()
        elif tok.type == 'IF':
            return self.parse_if()
        elif tok.type == 'WHILE':
            return self.parse_while()
        elif tok.type == 'FOR':
            return self.parse_for()
        elif tok.type == 'FUNCTION':
            return self.parse_function()
        elif tok.type == 'RETURN':
            return self.parse_return()
        elif tok.type == 'IDENTIFIER':
            # Could be assignment or function call
            next_tok = self.tokens[self.pos+1] if self.pos+1 < len(self.tokens) else None
            if next_tok and next_tok.type in ('ASSIGN', 'LBRACKET'):
                return self.parse_set_implicit()
            elif next_tok and next_tok.type == 'LPAREN':
                return self.parse_function_call_stmt()
                
        # If we reach here, it's something we don't recognize as a statement
        self.errors.append(f"Syntax Error at line {tok.line}: Unrecognized statement starting with {tok.type}")
        return None

    def parse_import(self):
        self.consume('IMPORT')
        name_tok = self.consume('IDENTIFIER')
        return ImportStmt(name_tok.value)

    def parse_declare(self):
        self.consume('DECLARE')
        name_tok = self.consume('IDENTIFIER')
        value = None
        if self.match('ASSIGN'):
            value = self.parse_expression()
        return Declare(name_tok.value, value)

    def parse_set(self):
        self.consume('SET')
        return self.parse_set_implicit()

    def parse_set_implicit(self):
        name_tok = self.consume('IDENTIFIER')
        index = None
        if self.match('LBRACKET'):
            index = self.parse_expression()
            self.consume('RBRACKET')
        self.consume('ASSIGN')
        value = self.parse_expression()
        return Assign(name_tok.value, value, index)

    def parse_print(self):
        self.consume('PRINT')
        exprs = []
        exprs.append(self.parse_expression())
        while self.match('COMMA'):
            exprs.append(self.parse_expression())
        return Print(exprs)

    def parse_read(self):
        self.consume('READ')
        name_tok = self.consume('IDENTIFIER')
        return Read(name_tok.value)

    def parse_if(self):
        self.consume('IF')
        condition = self.parse_expression()
        self.consume('THEN') if self.current_token().type == 'THEN' else None
        
        then_branch = []
        while self.current_token().type not in ('EOF', 'ELSE', 'ELSE_IF', 'ENDIF', 'STOP'):
            # Allow "ELSE IF" as two tokens
            if self.current_token().type == 'ELSE' and self.tokens[self.pos+1].type == 'IF':
                break
            stmt = self.parse_statement()
            if stmt: then_branch.append(stmt)
            else: self.pos += 1
            
        else_ifs = []
        while True:
            if self.match('ELSE_IF'):
                cond = self.parse_expression()
                self.consume('THEN') if self.current_token().type == 'THEN' else None
                body = []
                while self.current_token().type not in ('EOF', 'ELSE', 'ELSE_IF', 'ENDIF', 'STOP'):
                    if self.current_token().type == 'ELSE' and self.tokens[self.pos+1].type == 'IF':
                        break
                    stmt = self.parse_statement()
                    if stmt: body.append(stmt)
                    else: self.pos += 1
                else_ifs.append((cond, body))
            elif self.current_token().type == 'ELSE' and self.tokens[self.pos+1].type == 'IF':
                self.consume('ELSE')
                self.consume('IF')
                cond = self.parse_expression()
                self.consume('THEN') if self.current_token().type == 'THEN' else None
                body = []
                while self.current_token().type not in ('EOF', 'ELSE', 'ELSE_IF', 'ENDIF', 'STOP'):
                    if self.current_token().type == 'ELSE' and self.tokens[self.pos+1].type == 'IF':
                        break
                    stmt = self.parse_statement()
                    if stmt: body.append(stmt)
                    else: self.pos += 1
                else_ifs.append((cond, body))
            else:
                break
                
        else_branch = None
        if self.match('ELSE'):
            else_branch = []
            while self.current_token().type not in ('EOF', 'ENDIF', 'STOP'):
                stmt = self.parse_statement()
                if stmt: else_branch.append(stmt)
                else: self.pos += 1
                
        if self.match('ENDIF'):
            pass # Optional ENDIF
            
        return IfStmt(condition, then_branch, else_ifs, else_branch)

    def parse_while(self):
        self.consume('WHILE')
        condition = self.parse_expression()
        self.consume('DO') if self.current_token().type == 'DO' else None
        body = []
        while self.current_token().type not in ('EOF', 'ENDWHILE', 'STOP'):
            stmt = self.parse_statement()
            if stmt: body.append(stmt)
            else: self.pos += 1
        if self.match('ENDWHILE'):
            pass
        return WhileStmt(condition, body)

    def parse_for(self):
        self.consume('FOR')
        var_tok = self.consume('IDENTIFIER')
        self.consume('ASSIGN') if self.current_token().type == 'ASSIGN' else None
        start = self.parse_expression()
        self.consume('TO') if self.current_token().type == 'TO' else None
        end = self.parse_expression()
        body = []
        while self.current_token().type not in ('EOF', 'ENDFOR', 'STOP'):
            stmt = self.parse_statement()
            if stmt: body.append(stmt)
            else: self.pos += 1
        if self.match('ENDFOR'):
            pass
        return ForStmt(var_tok.value, start, end, body)

    def parse_function(self):
        self.consume('FUNCTION')
        name_tok = self.consume('IDENTIFIER')
        self.consume('LPAREN')
        params = []
        if self.current_token().type != 'RPAREN':
            params.append(self.consume('IDENTIFIER').value)
            while self.match('COMMA'):
                params.append(self.consume('IDENTIFIER').value)
        self.consume('RPAREN')
        body = []
        while self.current_token().type not in ('EOF', 'ENDFUNCTION', 'STOP'):
            stmt = self.parse_statement()
            if stmt: body.append(stmt)
            else: self.pos += 1
        if self.match('ENDFUNCTION'):
            pass
        return FunctionDecl(name_tok.value, params, body)

    def parse_return(self):
        self.consume('RETURN')
        value = self.parse_expression()
        return ReturnStmt(value)

    def parse_function_call_stmt(self):
        name = self.consume('IDENTIFIER').value
        self.consume('LPAREN')
        args = []
        if self.current_token().type != 'RPAREN':
            args.append(self.parse_expression())
            while self.match('COMMA'):
                args.append(self.parse_expression())
        self.consume('RPAREN')
        return FunctionCall(name, args)

    # Expressions
    def parse_expression(self):
        return self.parse_logical_or()

    def parse_logical_or(self):
        node = self.parse_logical_and()
        while self.current_token().type == 'OR':
            op = self.consume('OR').type
            right = self.parse_logical_and()
            node = BinaryOp(node, op, right)
        return node

    def parse_logical_and(self):
        node = self.parse_equality()
        while self.current_token().type == 'AND':
            op = self.consume('AND').type
            right = self.parse_equality()
            node = BinaryOp(node, op, right)
        return node

    def parse_equality(self):
        node = self.parse_relational()
        while self.current_token().type in ('EQ', 'NEQ'):
            op = self.consume(self.current_token().type).type
            right = self.parse_relational()
            node = BinaryOp(node, op, right)
        return node

    def parse_relational(self):
        node = self.parse_additive()
        while self.current_token().type in ('LT', 'GT', 'LTE', 'GTE'):
            op = self.consume(self.current_token().type).type
            right = self.parse_additive()
            node = BinaryOp(node, op, right)
        return node

    def parse_additive(self):
        node = self.parse_multiplicative()
        while self.current_token().type in ('PLUS', 'MINUS'):
            op = self.consume(self.current_token().type).type
            right = self.parse_multiplicative()
            node = BinaryOp(node, op, right)
        return node

    def parse_multiplicative(self):
        node = self.parse_unary()
        while self.current_token().type in ('MUL', 'DIV', 'MOD'):
            op = self.consume(self.current_token().type).type
            right = self.parse_unary()
            node = BinaryOp(node, op, right)
        return node

    def parse_unary(self):
        if self.current_token().type in ('MINUS', 'NOT'):
            op = self.consume(self.current_token().type).type
            return UnaryOp(op, self.parse_unary())
        return self.parse_primary()

    def parse_primary(self):
        tok = self.current_token()
        if tok.type in ('NUMBER', 'STRING'):
            self.consume(tok.type)
            return Literal(tok.value)
        elif tok.type == 'IDENTIFIER':
            next_tok = self.tokens[self.pos+1] if self.pos+1 < len(self.tokens) else None
            if next_tok and next_tok.type == 'LPAREN':
                return self.parse_function_call_stmt()
            elif next_tok and next_tok.type == 'LBRACKET':
                name = self.consume('IDENTIFIER').value
                self.consume('LBRACKET')
                index = self.parse_expression()
                self.consume('RBRACKET')
                return ArrayAccess(name, index)
            else:
                self.consume('IDENTIFIER')
                return Identifier(tok.value)
        elif tok.type == 'LPAREN':
            self.consume('LPAREN')
            expr = self.parse_expression()
            self.consume('RPAREN')
            return expr
        else:
            self.errors.append(f"Syntax Error at line {tok.line}: Unexpected token {tok.type} in expression")
            self.consume() # Avoid infinite loop
            return Literal(None)
