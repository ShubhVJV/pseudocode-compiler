from transpiler.ast_nodes import *
from transpiler.lexer import TAMIL_TANGLISH_KEYWORDS

class ParseError(Exception):
    pass

BLOCK_BOUNDARY_TOKENS = {
    'EOF', 'STOP', 'ELSE', 'ELSE_IF',
    'ENDIF', 'ENDWHILE', 'ENDFOR', 'ENDFUNCTION', 'ENDDEF', 'END'
}

ASSIGN_OP_MAP = {
    'ASSIGN': '=',
    'PLUS_ASSIGN': '+=',
    'MINUS_ASSIGN': '-=',
    'MUL_ASSIGN': '*=',
    'DIV_ASSIGN': '/=',
    'FLOORDIV_ASSIGN': '//=',
    'MOD_ASSIGN': '%=',
    'POW_ASSIGN': '**=',
}

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.errors = []
        self.is_tamil = any(
            t.type == 'SET' or str(t.value).upper() in TAMIL_TANGLISH_KEYWORDS
            for t in tokens if t.type != 'STRING'
        )

    def current_token(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return self.tokens[-1]

    def peek_token(self, offset=1):
        idx = self.pos + offset
        if 0 <= idx < len(self.tokens):
            return self.tokens[idx]
        return self.tokens[-1]

    def consume(self, expected_type=None):
        tok = self.current_token()
        if expected_type and tok.type != expected_type:
            self.errors.append(
                f"Line {tok.line}, Column {tok.column}: Expected {expected_type}, got {tok.type} ('{tok.value}')."
            )
            if tok.type != 'EOF':
                self.pos += 1
            return tok
        if tok.type != 'EOF':
            self.pos += 1
        return tok

    def match(self, *expected_types):
        tok = self.current_token()
        if tok.type in expected_types:
            self.pos += 1
            return True
        return False

    def _skip_to_next_line(self, current_line):
        while self.current_token().type != 'EOF' and self.current_token().line == current_line:
            self.pos += 1

    def parse(self):
        statements = []
        has_start = False
        if self.current_token().type == 'START':
            self.consume('START')
            has_start = True

        while self.current_token().type not in ('EOF', 'STOP'):
            tok = self.current_token()
            # Allow bare END at the very end of a START ... END program
            if tok.type == 'END' and has_start and self.peek_token().type == 'EOF':
                self.consume('END')
                break

            if tok.type in ('ELSE', 'ELSE_IF', 'ENDIF', 'ENDWHILE', 'ENDFOR', 'ENDFUNCTION', 'ENDDEF', 'END'):
                self.errors.append(
                    f"Line {tok.line}, Column {tok.column}: Unexpected {tok.value or tok.type} without matching opening block."
                )
                self.pos += 1
                continue

            before_pos = self.pos
            stmt = self.parse_statement()
            if stmt is not None:
                statements.append(stmt)
            else:
                if self.pos == before_pos:
                    self.pos += 1

        if self.current_token().type == 'STOP':
            self.consume('STOP')

        return Program(statements), self.errors

    def parse_statement(self):
        tok = self.current_token()

        # Skip stray colons if any
        if tok.type == 'COLON':
            self.errors.append(f"Line {tok.line}, Column {tok.column}: Unexpected ':'.")
            self.pos += 1
            return None

        if tok.type == 'IMPORT':
            return self.parse_import()
        elif tok.type == 'DECLARE':
            return self.parse_declare()
        elif tok.type == 'SET':
            if self.is_tamil:
                return self.parse_set_tamil()
            self.errors.append(
                f"Line {tok.line}, Column {tok.column}: The 'SET' keyword is not supported for assignment. Use direct assignment 'variable = value' instead."
            )
            self._skip_to_next_line(tok.line)
            return None
        elif tok.type in ('LET', 'ASSIGN_KW'):
            return self.parse_let_or_assign()
        elif tok.type == 'PRINT':
            return self.parse_print()
        elif tok.type in ('READ', 'INPUT'):
            return self.parse_read_or_input()
        elif tok.type == 'IF':
            return self.parse_if()
        elif tok.type == 'WHILE':
            return self.parse_while()
        elif tok.type == 'FOR':
            return self.parse_for()
        elif tok.type in ('FUNCTION', 'DEF', 'DEFINE'):
            return self.parse_function()
        elif tok.type == 'RETURN':
            return self.parse_return()
        elif tok.type == 'BREAK':
            self.consume('BREAK')
            return BreakStmt(line=tok.line)
        elif tok.type == 'CONTINUE':
            self.consume('CONTINUE')
            return ContinueStmt(line=tok.line)
        elif tok.type == 'LPAREN':
            return self.parse_paren_unpack_or_expr_stmt()
        elif tok.type == 'IDENTIFIER':
            upper_val = str(tok.value).upper()
            nxt = self.peek_token()
            # Explicitly reject 'SET var = val' in pseudocode mode
            if not self.is_tamil and upper_val == 'SET':
                if nxt.line == tok.line and nxt.type == 'IDENTIFIER':
                    self.errors.append(
                        f"Line {tok.line}, Column {tok.column}: The 'SET' keyword is not supported for assignment. Use direct assignment '{nxt.value} = ...' instead."
                    )
                    self._skip_to_next_line(tok.line)
                    return None
            # Contextual collection statements when not followed by '=', '(', '[', '.', ','
            if nxt.line == tok.line and nxt.type not in ('LPAREN', 'LBRACKET', 'DOT', 'COMMA') and nxt.type not in ASSIGN_OP_MAP:
                if upper_val == 'CREATE' and nxt.type == 'IDENTIFIER' and str(nxt.value).upper() == 'LIST':
                    return self.parse_create_collection()
                elif upper_val in ('APPEND', 'ADD'):
                    return self.parse_append_stmt()
                elif upper_val == 'REMOVE':
                    return self.parse_remove_stmt()
            return self.parse_identifier_led_statement()

        self.errors.append(
            f"Line {tok.line}, Column {tok.column}: Unrecognized statement starting with '{tok.value or tok.type}'."
        )
        self._skip_to_next_line(tok.line)
        return None

    def parse_import(self):
        imp_tok = self.consume('IMPORT')
        if self.current_token().type != 'IDENTIFIER':
            tok = self.current_token()
            self.errors.append(f"Line {imp_tok.line}, Column {tok.column}: Expected module name after IMPORT.")
            return None
        parts = [self.consume('IDENTIFIER').value]
        while self.current_token().type == 'DOT' and self.current_token().line == imp_tok.line:
            self.consume('DOT')
            if self.current_token().type == 'IDENTIFIER':
                parts.append(self.consume('IDENTIFIER').value)
        return ImportStmt(".".join(parts), line=imp_tok.line)

    def parse_declare(self):
        dec_tok = self.consume('DECLARE')
        if self.current_token().type != 'IDENTIFIER':
            tok = self.current_token()
            self.errors.append(f"Line {dec_tok.line}, Column {tok.column}: Expected variable name after DECLARE.")
            self._skip_to_next_line(dec_tok.line)
            return None
        name_tok = self.consume('IDENTIFIER')
        value = None
        if self.match('ASSIGN'):
            value = self._parse_required_rhs(name_tok.line, '=')
        return Declare(name_tok.value, value, line=dec_tok.line)

    def parse_set_tamil(self):
        self.consume('SET')
        return self.parse_identifier_led_statement()

    def _match_assign_alias(self):
        if self.match('ASSIGN', 'TO', 'BE'):
            return True
        tok = self.current_token()
        if tok.type == 'IDENTIFIER' and str(tok.value).upper() in ('BE', 'TO'):
            self.consume()
            return True
        return False

    def parse_let_or_assign(self):
        kw_tok = self.consume()  # LET or ASSIGN_KW
        if self.current_token().type != 'IDENTIFIER':
            tok = self.current_token()
            self.errors.append(f"Line {kw_tok.line}, Column {tok.column}: Expected variable name after {kw_tok.value}.")
            self._skip_to_next_line(kw_tok.line)
            return None

        first_tok = self.consume('IDENTIFIER')
        # Check for tuple unpacking: LET a, b = ...
        if self.match('COMMA'):
            targets = [first_tok.value]
            while True:
                if self.current_token().type != 'IDENTIFIER':
                    t = self.current_token()
                    self.errors.append(f"Line {t.line}, Column {t.column}: Expected identifier in tuple unpacking.")
                    break
                targets.append(self.consume('IDENTIFIER').value)
                if not self.match('COMMA'):
                    break
            if not self._match_assign_alias():
                t = self.current_token()
                self.errors.append(f"Line {t.line}, Column {t.column}: Expected '=' after unpacking targets.")
                return None
            val = self._parse_rhs_maybe_tuple(kw_tok.line, '=')
            return TupleUnpackAssign(targets, val, line=kw_tok.line)

        # Check for indexing: LET arr[i] = ...
        lhs = Identifier(first_tok.value, line=first_tok.line)
        while self.current_token().type == 'LBRACKET' and self.current_token().line == first_tok.line:
            lhs = self._parse_index_or_slice(lhs)

        if self.current_token().type in ASSIGN_OP_MAP:
            op_tok = self.consume()
            op_str = ASSIGN_OP_MAP[op_tok.type]
        elif self._match_assign_alias():
            op_str = '='
        else:
            t = self.current_token()
            self.errors.append(
                f"Line {t.line}, Column {t.column}: Expected '=' (or BE/TO) in assignment to '{first_tok.value}'."
            )
            self._skip_to_next_line(kw_tok.line)
            return None

        val = self._parse_rhs_maybe_tuple(kw_tok.line, op_str)
        return self._build_assign_node(lhs, val, op_str, kw_tok.line)

    def parse_create_collection(self):
        cr_tok = self.consume('IDENTIFIER')  # CREATE
        self.consume('IDENTIFIER')  # LIST
        if self.current_token().type != 'IDENTIFIER':
            t = self.current_token()
            self.errors.append(f"Line {cr_tok.line}, Column {t.column}: Expected list variable name after CREATE LIST.")
            self._skip_to_next_line(cr_tok.line)
            return None
        name_tok = self.consume('IDENTIFIER')
        if self._match_assign_alias():
            val = self._parse_required_rhs(cr_tok.line, '=')
        else:
            val = ListLiteral([], line=cr_tok.line)
        return Assign(name_tok.value, val, line=cr_tok.line)

    def parse_append_stmt(self):
        op_tok = self.consume('IDENTIFIER')  # APPEND or ADD
        item_expr = self.parse_expression()
        if not self.match('TO'):
            t = self.current_token()
            self.errors.append(f"Line {op_tok.line}, Column {t.column}: Expected TO in '{op_tok.value} <item> TO <list>'.")
            self._skip_to_next_line(op_tok.line)
            return None
        target_expr = self.parse_postfix()
        return MethodCall(target_expr, 'append', [item_expr], line=op_tok.line)

    def parse_remove_stmt(self):
        op_tok = self.consume('IDENTIFIER')  # REMOVE
        item_expr = self.parse_expression()
        if not self.match('FROM'):
            t = self.current_token()
            self.errors.append(f"Line {op_tok.line}, Column {t.column}: Expected FROM in 'REMOVE <item> FROM <list>'.")
            self._skip_to_next_line(op_tok.line)
            return None
        target_expr = self.parse_postfix()
        return MethodCall(target_expr, 'remove', [item_expr], line=op_tok.line)

    def parse_paren_unpack_or_expr_stmt(self):
        # Support (a, b) = point
        lp_tok = self.consume('LPAREN')
        if self.current_token().type == 'IDENTIFIER' and self.peek_token().type == 'COMMA':
            targets = [self.consume('IDENTIFIER').value]
            while self.match('COMMA'):
                if self.current_token().type != 'IDENTIFIER':
                    t = self.current_token()
                    self.errors.append(f"Line {t.line}, Column {t.column}: Expected identifier in tuple unpacking.")
                    break
                targets.append(self.consume('IDENTIFIER').value)
            self.consume('RPAREN')
            if not self.match('ASSIGN'):
                t = self.current_token()
                self.errors.append(f"Line {t.line}, Column {t.column}: Expected '=' after tuple unpacking pattern.")
                self._skip_to_next_line(lp_tok.line)
                return None
            val = self._parse_rhs_maybe_tuple(lp_tok.line, '=')
            return TupleUnpackAssign(targets, val, line=lp_tok.line)
        else:
            self.errors.append(f"Line {lp_tok.line}, Column {lp_tok.column}: Unexpected '(' at start of statement.")
            self._skip_to_next_line(lp_tok.line)
            return None

    def parse_identifier_led_statement(self):
        start_tok = self.current_token()

        # Check for tuple unpacking: first, second = point
        if self.peek_token().type == 'COMMA' and self.peek_token().line == start_tok.line:
            targets = [self.consume('IDENTIFIER').value]
            while self.match('COMMA'):
                if self.current_token().type != 'IDENTIFIER':
                    t = self.current_token()
                    self.errors.append(f"Line {t.line}, Column {t.column}: Expected identifier in tuple unpacking.")
                    self._skip_to_next_line(start_tok.line)
                    return None
                targets.append(self.consume('IDENTIFIER').value)
            if not self.match('ASSIGN'):
                t = self.current_token()
                self.errors.append(f"Line {t.line}, Column {t.column}: Expected '=' after unpacking variables.")
                self._skip_to_next_line(start_tok.line)
                return None
            val = self._parse_rhs_maybe_tuple(start_tok.line, '=')
            return TupleUnpackAssign(targets, val, line=start_tok.line)

        lhs = self.parse_postfix()

        # Check for assignment or compound assignment
        tok = self.current_token()
        if tok.type in ASSIGN_OP_MAP:
            op_tok = self.consume()
            op_str = ASSIGN_OP_MAP[op_tok.type]
            if not isinstance(lhs, (Identifier, ArrayAccess, SliceAccess, AttributeAccess)):
                self.errors.append(
                    f"Line {start_tok.line}, Column {start_tok.column}: Invalid assignment target."
                )
                self._skip_to_next_line(start_tok.line)
                return None
            val = self._parse_rhs_maybe_tuple(op_tok.line, op_str)
            stmt = self._build_assign_node(lhs, val, op_str, start_tok.line)
            self._check_end_of_statement(op_tok.line)
            return stmt

        # Standalone function call or method call statement
        if isinstance(lhs, (FunctionCall, MethodCall)):
            self._check_end_of_statement(start_tok.line)
            return lhs

        # If we get here, it's an invalid standalone expression or malformed statement
        err_tok = self.current_token()
        if err_tok.line == start_tok.line and err_tok.type != 'EOF':
            self.errors.append(
                f"Line {err_tok.line}, Column {err_tok.column}: Expected '=' or '(' after '{start_tok.value}', got '{err_tok.value or err_tok.type}'."
            )
        else:
            self.errors.append(
                f"Line {start_tok.line}, Column {start_tok.column}: Incomplete statement '{start_tok.value}'; expected assignment or function call."
            )
        self._skip_to_next_line(start_tok.line)
        return None

    def _build_assign_node(self, lhs, val, op_str, line):
        if isinstance(lhs, Identifier):
            return Assign(lhs.name, val, index=None, op=op_str, target=None, line=line)
        elif isinstance(lhs, ArrayAccess) and isinstance(lhs.target, Identifier):
            return Assign(lhs.name, val, index=lhs.index, op=op_str, target=lhs, line=line)
        else:
            name = getattr(lhs, 'name', 'target')
            idx = getattr(lhs, 'index', None)
            return Assign(name, val, index=idx, op=op_str, target=lhs, line=line)

    def _parse_required_rhs(self, line, op_str='='):
        tok = self.current_token()
        if tok.type in BLOCK_BOUNDARY_TOKENS or tok.line > line:
            self.errors.append(f"Line {line}, Column {tok.column}: Expected an expression after '{op_str}'.")
            return Literal(None, line=line)
        return self.parse_expression()

    def _parse_rhs_maybe_tuple(self, line, op_str='='):
        first = self._parse_required_rhs(line, op_str)
        if self.current_token().type == 'COMMA' and self.current_token().line == line:
            elements = [first]
            while self.current_token().type == 'COMMA' and self.current_token().line == line:
                self.consume('COMMA')
                elements.append(self.parse_expression())
            return TupleLiteral(elements, line=line)
        return first

    def _check_end_of_statement(self, stmt_line):
        tok = self.current_token()
        if tok.type not in BLOCK_BOUNDARY_TOKENS and tok.line == stmt_line:
            self.errors.append(
                f"Line {tok.line}, Column {tok.column}: Unexpected token '{tok.value or tok.type}' after statement on the same line."
            )
            self._skip_to_next_line(stmt_line)

    def parse_print(self):
        p_tok = self.consume('PRINT')
        exprs = []
        tok = self.current_token()
        if tok.type in BLOCK_BOUNDARY_TOKENS or tok.line > p_tok.line:
            return Print(exprs, line=p_tok.line)
        exprs.append(self.parse_expression())
        while self.current_token().type == 'COMMA' and self.current_token().line == p_tok.line:
            self.consume('COMMA')
            exprs.append(self.parse_expression())
        self._check_end_of_statement(p_tok.line)
        return Print(exprs, line=p_tok.line)

    def parse_read_or_input(self):
        r_tok = self.consume()  # READ or INPUT
        if self.current_token().type == 'LPAREN' and self.current_token().line == r_tok.line:
            self.consume('LPAREN')
            args = []
            if self.current_token().type != 'RPAREN':
                args.append(self.parse_expression())
                while self.match('COMMA'):
                    args.append(self.parse_expression())
            self.consume('RPAREN')
            return FunctionCall('input', args, line=r_tok.line)

        if self.current_token().type != 'IDENTIFIER':
            t = self.current_token()
            self.errors.append(f"Line {r_tok.line}, Column {t.column}: Expected variable name after {r_tok.value}.")
            self._skip_to_next_line(r_tok.line)
            return None
        name_tok = self.consume('IDENTIFIER')
        return Read(name_tok.value, line=r_tok.line)

    def _consume_optional_header_delimiter(self, header_line, keyword_name):
        if self.match('THEN', 'DO', 'COLON'):
            return
        # If no explicit delimiter (like THEN/DO/:), ensure condition isn't jammed with body on same line
        tok = self.current_token()
        if tok.type not in BLOCK_BOUNDARY_TOKENS and tok.line == header_line:
            self.errors.append(
                f"Line {tok.line}, Column {tok.column}: Expected {'THEN' if keyword_name in ('IF', 'ELSE IF') else 'DO'} or ':' or newline after {keyword_name} header, got '{tok.value or tok.type}'."
            )
            self._skip_to_next_line(header_line)

    def parse_if(self):
        if_tok = self.consume('IF')
        if self.current_token().type in ('THEN', 'COLON') or self.current_token().type in BLOCK_BOUNDARY_TOKENS:
            self.errors.append(f"Line {if_tok.line}, Column {if_tok.column}: Missing condition in IF statement.")
            cond = Literal(False, line=if_tok.line)
        else:
            cond = self.parse_expression()
        self._consume_optional_header_delimiter(if_tok.line, 'IF')

        then_branch = []
        while self.current_token().type not in BLOCK_BOUNDARY_TOKENS:
            before = self.pos
            stmt = self.parse_statement()
            if stmt is not None:
                then_branch.append(stmt)
            elif self.pos == before:
                self.pos += 1

        else_ifs = []
        while self.current_token().type == 'ELSE_IF':
            elif_tok = self.consume('ELSE_IF')
            if self.current_token().type in ('THEN', 'COLON') or self.current_token().type in BLOCK_BOUNDARY_TOKENS:
                self.errors.append(f"Line {elif_tok.line}, Column {elif_tok.column}: Missing condition in ELSE IF statement.")
                elif_cond = Literal(False, line=elif_tok.line)
            else:
                elif_cond = self.parse_expression()
            self._consume_optional_header_delimiter(elif_tok.line, 'ELSE IF')

            body = []
            while self.current_token().type not in BLOCK_BOUNDARY_TOKENS:
                before = self.pos
                stmt = self.parse_statement()
                if stmt is not None:
                    body.append(stmt)
                elif self.pos == before:
                    self.pos += 1
            else_ifs.append((elif_cond, body))

        else_branch = None
        if self.match('ELSE'):
            self.match('COLON')
            else_branch = []
            while self.current_token().type not in BLOCK_BOUNDARY_TOKENS:
                before = self.pos
                stmt = self.parse_statement()
                if stmt is not None:
                    else_branch.append(stmt)
                elif self.pos == before:
                    self.pos += 1

            # Detect duplicate ELSE or ELSE IF after ELSE
            while self.current_token().type in ('ELSE', 'ELSE_IF'):
                bad = self.consume()
                self.errors.append(
                    f"Line {bad.line}, Column {bad.column}: Unexpected '{bad.value}' after ELSE branch in conditional block."
                )
                self.match('THEN', 'COLON')
                while self.current_token().type not in BLOCK_BOUNDARY_TOKENS:
                    before = self.pos
                    self.parse_statement()
                    if self.pos == before:
                        self.pos += 1

        # Verify terminator
        if self.match('ENDIF'):
            pass
        elif self.is_tamil and self.current_token().type in ('STOP', 'EOF'):
            pass
        elif self.current_token().type in ('ENDWHILE', 'ENDFOR', 'ENDFUNCTION', 'ENDDEF', 'END'):
            bad = self.consume()
            self.errors.append(
                f"Line {bad.line}, Column {bad.column}: Unexpected {bad.value or bad.type}; expected END IF (for IF at line {if_tok.line})."
            )
        else:
            tok = self.current_token()
            self.errors.append(
                f"Line {tok.line}: Missing END IF for the conditional block starting at line {if_tok.line}."
            )

        return IfStmt(cond, then_branch, else_ifs, else_branch, line=if_tok.line)

    def parse_while(self):
        w_tok = self.consume('WHILE')
        if self.current_token().type in ('DO', 'COLON') or self.current_token().type in BLOCK_BOUNDARY_TOKENS:
            self.errors.append(f"Line {w_tok.line}, Column {w_tok.column}: Missing condition in WHILE loop.")
            cond = Literal(False, line=w_tok.line)
        else:
            cond = self.parse_expression()
        self._consume_optional_header_delimiter(w_tok.line, 'WHILE')

        body = []
        while self.current_token().type not in BLOCK_BOUNDARY_TOKENS:
            before = self.pos
            stmt = self.parse_statement()
            if stmt is not None:
                body.append(stmt)
            elif self.pos == before:
                self.pos += 1

        if self.match('ENDWHILE'):
            pass
        elif self.is_tamil and self.current_token().type in ('STOP', 'EOF'):
            pass
        elif self.current_token().type in ('ENDIF', 'ENDFOR', 'ENDFUNCTION', 'ENDDEF', 'ELSE', 'ELSE_IF', 'END'):
            bad = self.consume()
            self.errors.append(
                f"Line {bad.line}, Column {bad.column}: Unexpected {bad.value or bad.type}; expected END WHILE (for WHILE at line {w_tok.line})."
            )
        else:
            tok = self.current_token()
            self.errors.append(
                f"Line {tok.line}: Missing END WHILE for the while loop starting at line {w_tok.line}."
            )

        return WhileStmt(cond, body, line=w_tok.line)

    def parse_for(self):
        f_tok = self.consume('FOR')
        has_each = self.match('EACH')

        if self.current_token().type != 'IDENTIFIER':
            t = self.current_token()
            self.errors.append(f"Line {f_tok.line}, Column {t.column}: Expected loop variable name after FOR.")
            self._skip_to_next_line(f_tok.line)
            return None

        var_tok = self.consume('IDENTIFIER')
        unpack_vars = None
        if self.match('COMMA'):
            unpack_vars = [var_tok.value]
            while True:
                if self.current_token().type != 'IDENTIFIER':
                    t = self.current_token()
                    self.errors.append(f"Line {t.line}, Column {t.column}: Expected identifier in FOR loop unpacking.")
                    break
                unpack_vars.append(self.consume('IDENTIFIER').value)
                if not self.match('COMMA'):
                    break

        # For-each loop: FOR [EACH] item IN items
        if has_each or self.current_token().type == 'IN':
            if not self.match('IN'):
                t = self.current_token()
                self.errors.append(f"Line {f_tok.line}, Column {t.column}: Expected IN in FOR EACH loop.")
            iterable = self.parse_expression()
            self.match('DO', 'COLON')

            body = []
            while self.current_token().type not in BLOCK_BOUNDARY_TOKENS:
                before = self.pos
                stmt = self.parse_statement()
                if stmt is not None:
                    body.append(stmt)
                elif self.pos == before:
                    self.pos += 1

            self._consume_for_terminator(f_tok)
            return ForEachStmt(var_tok.value, iterable, body, unpack_vars=unpack_vars, line=f_tok.line)

        # Numeric range loop: FOR i FROM/= start TO/THROUGH/DOWN TO end [STEP step]
        if not self.match('FROM', 'ASSIGN') and not self.is_tamil:
            t = self.current_token()
            self.errors.append(
                f"Line {f_tok.line}, Column {t.column}: Expected FROM, '=', or IN after loop variable '{var_tok.value}'."
            )

        start_expr = self.parse_expression()

        descending = False
        inclusive = False
        if self.match('DOWNTO'):
            descending = True
            inclusive = False
        elif self.match('DOWN'):
            descending = True
            if self.match('THROUGH'):
                inclusive = True
            else:
                self.consume('TO')
                inclusive = False
        elif self.match('THROUGH'):
            inclusive = True
        elif self.match('TO'):
            inclusive = True if self.is_tamil else False
        else:
            t = self.current_token()
            self.errors.append(
                f"Line {t.line}, Column {t.column}: Expected TO, THROUGH, or DOWN TO in numeric FOR loop."
            )

        end_expr = self.parse_expression()
        step_expr = None
        if self.match('STEP'):
            step_expr = self.parse_expression()

        self.match('DO', 'COLON')

        body = []
        while self.current_token().type not in BLOCK_BOUNDARY_TOKENS:
            before = self.pos
            stmt = self.parse_statement()
            if stmt is not None:
                body.append(stmt)
            elif self.pos == before:
                self.pos += 1

        self._consume_for_terminator(f_tok)
        return ForStmt(
            var_tok.value, start_expr, end_expr, body,
            step=step_expr, inclusive=inclusive, descending=descending, line=f_tok.line
        )

    def _consume_for_terminator(self, f_tok):
        if self.match('ENDFOR'):
            return
        if self.is_tamil and self.current_token().type in ('STOP', 'EOF'):
            return
        if self.current_token().type in ('ENDIF', 'ENDWHILE', 'ENDFUNCTION', 'ENDDEF', 'ELSE', 'ELSE_IF', 'END'):
            bad = self.consume()
            self.errors.append(
                f"Line {bad.line}, Column {bad.column}: Unexpected {bad.value or bad.type}; expected END FOR (for FOR at line {f_tok.line})."
            )
        else:
            tok = self.current_token()
            self.errors.append(
                f"Line {tok.line}: Missing END FOR for the for loop starting at line {f_tok.line}."
            )

    def parse_function(self):
        fn_tok = self.consume()  # FUNCTION, DEF, or DEFINE
        if fn_tok.type == 'DEFINE':
            self.match('FUNCTION')

        if self.current_token().type != 'IDENTIFIER':
            t = self.current_token()
            self.errors.append(
                f"Line {fn_tok.line}, Column {t.column}: Expected valid function identifier after {fn_tok.value}."
            )
            self._skip_to_next_line(fn_tok.line)
            return None

        name_tok = self.consume('IDENTIFIER')
        self.consume('LPAREN')
        params = []
        defaults = {}
        seen_default = False

        if self.current_token().type != 'RPAREN':
            while True:
                if self.current_token().type != 'IDENTIFIER':
                    t = self.current_token()
                    self.errors.append(
                        f"Line {t.line}, Column {t.column}: Expected parameter identifier in function '{name_tok.value}'."
                    )
                    break
                p_tok = self.consume('IDENTIFIER')
                p_name = p_tok.value
                params.append(p_name)

                if self.match('ASSIGN'):
                    defaults[p_name] = self.parse_expression()
                    seen_default = True
                elif seen_default:
                    self.errors.append(
                        f"Line {p_tok.line}, Column {p_tok.column}: Non-default parameter '{p_name}' cannot follow a default parameter in function '{name_tok.value}'."
                    )

                if not self.match('COMMA'):
                    break

        self.consume('RPAREN')
        self.match('COLON')

        body = []
        while self.current_token().type not in BLOCK_BOUNDARY_TOKENS:
            before = self.pos
            stmt = self.parse_statement()
            if stmt is not None:
                body.append(stmt)
            elif self.pos == before:
                self.pos += 1

        if self.match('ENDFUNCTION', 'ENDDEF'):
            pass
        elif self.is_tamil and self.current_token().type in ('STOP', 'EOF'):
            pass
        elif self.current_token().type in ('ENDIF', 'ENDWHILE', 'ENDFOR', 'ELSE', 'ELSE_IF', 'END'):
            bad = self.consume()
            expected = 'END DEF' if fn_tok.type == 'DEF' else 'END FUNCTION'
            self.errors.append(
                f"Line {bad.line}, Column {bad.column}: Unexpected {bad.value or bad.type}; expected {expected} (for function '{name_tok.value}' at line {fn_tok.line})."
            )
        else:
            tok = self.current_token()
            expected = 'END DEF' if fn_tok.type == 'DEF' else 'END FUNCTION'
            self.errors.append(
                f"Line {tok.line}: Missing {expected} for function '{name_tok.value}' starting at line {fn_tok.line}."
            )

        return FunctionDecl(name_tok.value, params, body, defaults=defaults, line=fn_tok.line)

    def parse_return(self):
        ret_tok = self.consume('RETURN')
        tok = self.current_token()
        if tok.type in BLOCK_BOUNDARY_TOKENS or tok.line > ret_tok.line:
            return ReturnStmt(None, line=ret_tok.line)
        val = self._parse_rhs_maybe_tuple(ret_tok.line, 'RETURN')
        self._check_end_of_statement(ret_tok.line)
        return ReturnStmt(val, line=ret_tok.line)

    # ================= Expressions =================

    def parse_expression(self):
        return self.parse_logical_or()

    def parse_logical_or(self):
        node = self.parse_logical_and()
        while self.current_token().type == 'OR':
            op_tok = self.consume('OR')
            right = self.parse_logical_and()
            node = BinaryOp(node, 'OR', right, line=op_tok.line)
        return node

    def parse_logical_and(self):
        node = self.parse_logical_not()
        while self.current_token().type == 'AND':
            op_tok = self.consume('AND')
            right = self.parse_logical_not()
            node = BinaryOp(node, 'AND', right, line=op_tok.line)
        return node

    def parse_logical_not(self):
        if self.current_token().type == 'NOT':
            op_tok = self.consume('NOT')
            return UnaryOp('NOT', self.parse_logical_not(), line=op_tok.line)
        return self.parse_comparison()

    def parse_comparison(self):
        node = self.parse_additive()
        while True:
            tok = self.current_token()
            if tok.type in ('EQ', 'NEQ', 'LT', 'GT', 'LTE', 'GTE', 'IN'):
                op_tok = self.consume()
                right = self.parse_additive()
                node = BinaryOp(node, op_tok.type, right, line=op_tok.line)
            elif tok.type == 'NOT' and self.peek_token().type == 'IN':
                op_tok = self.consume('NOT')
                self.consume('IN')
                right = self.parse_additive()
                node = BinaryOp(node, 'NOT_IN', right, line=op_tok.line)
            elif tok.type == 'IS':
                op_tok = self.consume('IS')
                if self.match('NOT'):
                    right = self.parse_additive()
                    node = BinaryOp(node, 'NEQ', right, line=op_tok.line)
                else:
                    right = self.parse_additive()
                    node = BinaryOp(node, 'EQ', right, line=op_tok.line)
            else:
                break
        return node

    def parse_additive(self):
        node = self.parse_multiplicative()
        while self.current_token().type in ('PLUS', 'MINUS'):
            op_tok = self.consume()
            right = self.parse_multiplicative()
            node = BinaryOp(node, op_tok.type, right, line=op_tok.line)
        return node

    def parse_multiplicative(self):
        node = self.parse_unary()
        while self.current_token().type in ('MUL', 'DIV', 'FLOORDIV', 'MOD'):
            op_tok = self.consume()
            right = self.parse_unary()
            node = BinaryOp(node, op_tok.type, right, line=op_tok.line)
        return node

    def parse_unary(self):
        if self.current_token().type in ('MINUS', 'PLUS', 'NOT'):
            op_tok = self.consume()
            return UnaryOp(op_tok.type, self.parse_unary(), line=op_tok.line)
        return self.parse_power()

    def parse_power(self):
        node = self.parse_postfix()
        if self.current_token().type == 'POW':
            op_tok = self.consume('POW')
            # Right-associative
            right = self.parse_unary()
            node = BinaryOp(node, 'POW', right, line=op_tok.line)
        return node

    def parse_postfix(self):
        node = self.parse_primary()
        while True:
            tok = self.current_token()
            # Postfix operations must start on the same line as the expression
            prev_line = self.tokens[self.pos - 1].line if self.pos > 0 else tok.line
            if tok.line != prev_line:
                break

            if tok.type == 'LPAREN':
                self.consume('LPAREN')
                args = []
                if self.current_token().type != 'RPAREN':
                    args.append(self.parse_expression())
                    while self.match('COMMA'):
                        args.append(self.parse_expression())
                self.consume('RPAREN')
                if isinstance(node, Identifier):
                    node = FunctionCall(node.name, args, line=node.line)
                elif isinstance(node, AttributeAccess):
                    node = MethodCall(node.obj, node.attr, args, line=node.line)
                else:
                    node = FunctionCall(str(node), args, line=tok.line)

            elif tok.type == 'LBRACKET':
                node = self._parse_index_or_slice(node)

            elif tok.type == 'DOT':
                self.consume('DOT')
                m_tok = self.current_token()
                # Allow identifiers or keyword names like .append, .remove, .add
                if m_tok.type == 'IDENTIFIER' or (isinstance(m_tok.value, str) and m_tok.value.isidentifier()):
                    self.consume()
                    attr_name = m_tok.value
                else:
                    self.errors.append(
                        f"Line {m_tok.line}, Column {m_tok.column}: Expected attribute or method name after '.'."
                    )
                    break

                if self.current_token().type == 'LPAREN' and self.current_token().line == m_tok.line:
                    self.consume('LPAREN')
                    args = []
                    if self.current_token().type != 'RPAREN':
                        args.append(self.parse_expression())
                        while self.match('COMMA'):
                            args.append(self.parse_expression())
                    self.consume('RPAREN')
                    node = MethodCall(node, attr_name, args, line=m_tok.line)
                else:
                    node = AttributeAccess(node, attr_name, line=m_tok.line)
            else:
                break
        return node

    def _parse_index_or_slice(self, target_node):
        lb_tok = self.consume('LBRACKET')
        if self.current_token().type == 'RBRACKET':
            self.consume('RBRACKET')
            self.errors.append(f"Line {lb_tok.line}, Column {lb_tok.column}: Empty index in '[]' is not allowed.")
            return ArrayAccess(getattr(target_node, 'name', 'seq'), Literal(0), target=target_node, line=lb_tok.line)

        start = None
        stop = None
        step = None

        if self.current_token().type != 'COLON':
            first_expr = self.parse_expression()
        else:
            first_expr = None

        if self.match('COLON'):
            start = first_expr
            if self.current_token().type not in ('COLON', 'RBRACKET', 'EOF'):
                stop = self.parse_expression()
            if self.match('COLON'):
                if self.current_token().type not in ('RBRACKET', 'EOF'):
                    step = self.parse_expression()
            self.consume('RBRACKET')
            return SliceAccess(target_node, start=start, stop=stop, step=step, line=lb_tok.line)
        else:
            self.consume('RBRACKET')
            name = target_node.name if isinstance(target_node, Identifier) else getattr(target_node, 'name', 'seq')
            return ArrayAccess(name, first_expr, target=target_node, line=lb_tok.line)

    def parse_primary(self):
        tok = self.current_token()
        if tok.type == 'NUMBER':
            self.consume('NUMBER')
            return Literal(tok.value, raw_type='NUMBER', line=tok.line)
        elif tok.type == 'STRING':
            self.consume('STRING')
            return Literal(tok.value, raw_type='STRING', line=tok.line)
        elif tok.type == 'BOOLEAN':
            self.consume('BOOLEAN')
            return Literal(tok.value, raw_type='BOOLEAN', line=tok.line)
        elif tok.type == 'NONE':
            self.consume('NONE')
            return Literal(None, raw_type='NONE', line=tok.line)
        elif tok.type in ('INPUT', 'READ'):
            self.consume()
            args = []
            if self.current_token().type == 'LPAREN' and self.current_token().line == tok.line:
                self.consume('LPAREN')
                if self.current_token().type != 'RPAREN':
                    args.append(self.parse_expression())
                    while self.match('COMMA'):
                        args.append(self.parse_expression())
                self.consume('RPAREN')
            return FunctionCall('input', args, line=tok.line)
        elif tok.type == 'LIST_KW':
            self.consume('LIST_KW')
            return Identifier('list', line=tok.line)
        elif tok.type == 'IDENTIFIER':
            self.consume('IDENTIFIER')
            return Identifier(tok.value, line=tok.line)
        elif tok.type == 'LBRACKET':
            lb_tok = self.consume('LBRACKET')
            elements = []
            while self.current_token().type not in ('RBRACKET', 'EOF'):
                elements.append(self.parse_expression())
                if not self.match('COMMA'):
                    break
            self.consume('RBRACKET')
            return ListLiteral(elements, line=lb_tok.line)
        elif tok.type == 'LPAREN':
            lp_tok = self.consume('LPAREN')
            # Empty tuple: ()
            if self.match('RPAREN'):
                return TupleLiteral([], line=lp_tok.line)
            first_expr = self.parse_expression()
            # Tuple if comma follows: (10,) or (10, 20)
            if self.match('COMMA'):
                elements = [first_expr]
                while self.current_token().type not in ('RBRACKET', 'RPAREN', 'EOF'):
                    elements.append(self.parse_expression())
                    if not self.match('COMMA'):
                        break
                self.consume('RPAREN')
                return TupleLiteral(elements, line=lp_tok.line)
            self.consume('RPAREN')
            return first_expr
        else:
            self.errors.append(
                f"Line {tok.line}, Column {tok.column}: Expected an expression, got '{tok.value or tok.type}'."
            )
            if tok.type != 'EOF':
                self.consume()
            return Literal(None, line=tok.line)
