import re

class Token:
    def __init__(self, type_, value, line, column):
        self.type = type_
        self.value = value
        self.line = line
        self.column = column

    def __repr__(self):
        return f"Token({self.type}, {repr(self.value)}, Line: {self.line}, Col: {self.column})"

TAMIL_TANGLISH_KEYWORDS = {
    'THODANGU': 'START', 'தொடங்கு': 'START',
    'MUDI': 'STOP', 'முடி': 'STOP',
    'PADI': 'READ', 'படி': 'READ',
    'KANBI': 'PRINT', 'காண்பி': 'PRINT', 'EZHUDHU': 'PRINT', 'எழுது': 'PRINT',
    'ARIVI': 'DECLARE', 'அறிவி': 'DECLARE',
    'AMAI': 'SET', 'அமை': 'SET',
    'IRUNDHAL': 'IF', 'இருந்தால்': 'IF',
    'ILLAIYEL': 'ELSE', 'இல்லையேல்': 'ELSE',
    'ILLAIYEL IRUNDHAL': 'ELSE_IF', 'இல்லையேல் இருந்தால்': 'ELSE_IF',
    'AGA': 'FOR', 'ஆக': 'FOR',
    'VARAI': 'WHILE', 'வரை': 'WHILE',
    'THIRUMBU': 'RETURN', 'திரும்பு': 'RETURN',
    'MATRUM': 'AND', 'மற்றும்': 'AND',
    'ALLADHU': 'OR', 'அல்லது': 'OR',
    'ILLAI': 'NOT', 'இல்லை': 'NOT',
    'KONDUVA': 'IMPORT', 'கொண்டுவா': 'IMPORT',
    'APPODHU': 'THEN', 'அப்போது': 'THEN',
    'IF_MUDI': 'ENDIF',
    'SEI': 'DO', 'செய்': 'DO',
    'WHILE_MUDI': 'ENDWHILE',
    'FOR_MUDI': 'ENDFOR',
    'SEYALPADU': 'FUNCTION', 'செயல்பாடு': 'FUNCTION',
    'FUNCTION_MUDI': 'ENDFUNCTION',
}

PSEUDOCODE_KEYWORDS = {
    'START': 'START',
    'STOP': 'STOP',
    'READ': 'READ',
    'INPUT': 'INPUT',
    'PRINT': 'PRINT',
    'DISPLAY': 'PRINT',
    'OUTPUT': 'PRINT',
    'DECLARE': 'DECLARE',
    'LET': 'LET',
    'ASSIGN': 'ASSIGN_KW',
    'BE': 'BE',
    'IF': 'IF',
    'THEN': 'THEN',
    'ELSE': 'ELSE',
    'ELIF': 'ELSE_IF',
    'ELSEIF': 'ELSE_IF',
    'ENDIF': 'ENDIF',
    'FOR': 'FOR',
    'EACH': 'EACH',
    'IN': 'IN',
    'FROM': 'FROM',
    'TO': 'TO',
    'THROUGH': 'THROUGH',
    'THRU': 'THROUGH',
    'DOWN': 'DOWN',
    'DOWNTO': 'DOWNTO',
    'STEP': 'STEP',
    'BY': 'STEP',
    'ENDFOR': 'ENDFOR',
    'WHILE': 'WHILE',
    'DO': 'DO',
    'ENDWHILE': 'ENDWHILE',
    'FUNCTION': 'FUNCTION',
    'DEF': 'DEF',
    'DEFINE': 'DEFINE',
    'PROCEDURE': 'FUNCTION',
    'PROC': 'FUNCTION',
    'ENDFUNCTION': 'ENDFUNCTION',
    'ENDDEF': 'ENDDEF',
    'ENDPROCEDURE': 'ENDFUNCTION',
    'ENDPROC': 'ENDFUNCTION',
    'END': 'END',
    'RETURN': 'RETURN',
    'BREAK': 'BREAK',
    'CONTINUE': 'CONTINUE',
    'AND': 'AND',
    'OR': 'OR',
    'NOT': 'NOT',
    'IS': 'IS',
    'TRUE': 'BOOLEAN',
    'FALSE': 'BOOLEAN',
    'NONE': 'NONE',
    'NULL': 'NONE',
    'IMPORT': 'IMPORT',
}

# Combined dictionary for backward reference if imported externally
KEYWORDS = {**PSEUDOCODE_KEYWORDS, **TAMIL_TANGLISH_KEYWORDS}

TOKEN_TYPES = [
    ('TRIPLE_STRING', r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\''),
    ('STRING',        r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\''),
    ('UNTERM_STRING', r'"""[\s\S]*|\'\'\'[\s\S]*|"(?:\\.|[^"\\\n])*|\'(?:\\.|[^\'\\\n])*'),
    ('COMMENT',       r'#[^\n]*|(?i:\bCOMMENT\b)[^\n]*'),
    ('INVALID_IDENT', r'\d+[a-zA-Z_][a-zA-Z0-9_]*'),
    ('NUMBER',        r'\d+(?:\.\d+)?'),
    ('IDENTIFIER',    r'[a-zA-Z_][a-zA-Z0-9_]*|[\u0B80-\u0BFF]+'),
    ('POW_ASSIGN',    r'\*\*='),
    ('FLOORDIV_ASSIGN', r'//='),
    ('PLUS_ASSIGN',   r'\+='),
    ('MINUS_ASSIGN',  r'-='),
    ('MUL_ASSIGN',    r'\*='),
    ('DIV_ASSIGN',    r'/='),
    ('MOD_ASSIGN',    r'%='),
    ('POW',           r'\*\*'),
    ('FLOORDIV',      r'//'),
    ('PLUS',          r'\+'),
    ('MINUS',         r'-'),
    ('MUL',           r'\*'),
    ('DIV',           r'/'),
    ('MOD',           r'%'),
    ('GTE',           r'>='),
    ('LTE',           r'<='),
    ('NEQ',           r'!=|<>'),
    ('EQ',            r'=='),
    ('GT',            r'>'),
    ('LT',            r'<'),
    ('ASSIGN',        r'='),
    ('LPAREN',        r'\('),
    ('RPAREN',        r'\)'),
    ('LBRACE',        r'\{'),
    ('RBRACE',        r'\}'),
    ('LBRACKET',      r'\['),
    ('RBRACKET',      r'\]'),
    ('COMMA',         r','),
    ('COLON',         r':'),
    ('DOT',           r'\.'),
    ('NEWLINE',       r'\n'),
    ('SKIP',          r'[ \t]+'),
    ('MISMATCH',      r'.'),
]

class LexicalError(Exception):
    pass

def detect_tamil_mode(code):
    if re.search(r'[\u0B80-\u0BFF]', code):
        return True
    # Check for Tanglish keywords outside strings
    stripped = re.sub(r'"[^"]*"|\'[^\']*\'', '', code)
    words = {w.upper() for w in re.findall(r'\b[a-zA-Z_]+\b', stripped)}
    return bool(words & set(TAMIL_TANGLISH_KEYWORDS.keys()))

class Lexer:
    def __init__(self, code):
        # Safely normalize CRLF and CR line endings to LF while preserving lines and strings
        self.raw_code = code
        self.code = code.replace('\r\n', '\n').replace('\r', '\n')
        self.is_tamil = detect_tamil_mode(self.code)
        self.tokens = []
        self.errors = []

    def _unescape_string(self, raw_inner):
        # Preserve standard escape sequences if present
        out = []
        i = 0
        n = len(raw_inner)
        while i < n:
            if raw_inner[i] == '\\' and i + 1 < n:
                nxt = raw_inner[i + 1]
                if nxt == 'n':
                    out.append('\n')
                elif nxt == 't':
                    out.append('\t')
                elif nxt == 'r':
                    out.append('\r')
                elif nxt == '\\':
                    out.append('\\')
                elif nxt == '"':
                    out.append('"')
                elif nxt == "'":
                    out.append("'")
                else:
                    out.append('\\' + nxt)
                i += 2
            else:
                out.append(raw_inner[i])
                i += 1
        return ''.join(out)

    def tokenize(self):
        line_num = 1
        line_start = 0
        tok_regex = '|'.join('(?P<%s>%s)' % pair for pair in TOKEN_TYPES)
        pos = 0
        code_len = len(self.code)

        while pos < code_len:
            mo = re.match(tok_regex, self.code[pos:])
            if not mo:
                break
            kind = mo.lastgroup
            value = mo.group()
            column = pos - line_start + 1
            match_len = len(value)

            if kind == 'FLOORDIV':
                # Distinguish line-comment '//' from floor-division operator '//'
                # If '//' appears at the start of a line or immediately after statement-opening keywords,
                # treat the rest of the line as a comment.
                prev_tok = self.tokens[-1] if self.tokens else None
                is_expr_prev = (
                    prev_tok is not None
                    and prev_tok.line == line_num
                    and prev_tok.type in (
                        'NUMBER', 'STRING', 'BOOLEAN', 'NONE', 'IDENTIFIER',
                        'RPAREN', 'RBRACKET', 'INPUT', 'LIST_KW'
                    )
                )
                if not is_expr_prev:
                    nl_idx = self.code.find('\n', pos)
                    if nl_idx == -1:
                        pos = code_len
                    else:
                        pos = nl_idx
                    continue

            if kind == 'NUMBER':
                num_val = float(value) if '.' in value else int(value)
                self.tokens.append(Token('NUMBER', num_val, line_num, column))
            elif kind == 'TRIPLE_STRING':
                inner = self._unescape_string(value[3:-3])
                self.tokens.append(Token('STRING', inner, line_num, column))
                newlines = value.count('\n')
                if newlines > 0:
                    line_num += newlines
                    last_nl = value.rfind('\n')
                    line_start = pos + last_nl + 1
            elif kind == 'STRING':
                inner = self._unescape_string(value[1:-1])
                self.tokens.append(Token('STRING', inner, line_num, column))
            elif kind == 'UNTERM_STRING':
                self.errors.append(f"Line {line_num}, Column {column}: Unterminated string literal.")
                newlines = value.count('\n')
                if newlines > 0:
                    line_num += newlines
            elif kind == 'COMMENT':
                pass
            elif kind == 'INVALID_IDENT':
                self.errors.append(f"Line {line_num}, Column {column}: Invalid identifier '{value}' (identifiers cannot start with a digit).")
            elif kind == 'IDENTIFIER':
                upper_val = value.upper()
                if self.is_tamil and upper_val in TAMIL_TANGLISH_KEYWORDS:
                    kind = TAMIL_TANGLISH_KEYWORDS[upper_val]
                elif upper_val in PSEUDOCODE_KEYWORDS:
                    kind = PSEUDOCODE_KEYWORDS[upper_val]
                    if kind == 'BOOLEAN':
                        value = True if upper_val == 'TRUE' else False
                    elif kind == 'NONE':
                        value = None
                self.tokens.append(Token(kind, value, line_num, column))
            elif kind == 'NEWLINE':
                line_start = pos + match_len
                line_num += 1
            elif kind == 'SKIP':
                pass
            elif kind == 'MISMATCH':
                self.errors.append(f"Lexical Error at line {line_num}, column {column}: Unexpected character '{value}'")
            else:
                self.tokens.append(Token(kind, value, line_num, column))

            pos += match_len

        self.tokens = self._normalize_multiword_tokens(self.tokens)
        last_col = (code_len - line_start + 1) if code_len >= line_start else 1
        self.tokens.append(Token('EOF', '', line_num, last_col))
        return self.tokens, self.errors

    def _normalize_multiword_tokens(self, tokens):
        """Normalize multi-word block terminators and keywords on the same line into canonical tokens."""
        normalized = []
        i = 0
        n = len(tokens)
        while i < n:
            tok = tokens[i]
            nxt = tokens[i + 1] if i + 1 < n else None

            if nxt and nxt.line == tok.line:
                # END IF / END WHILE / END FOR / END FUNCTION / END DEF / END PROCEDURE
                if tok.type == 'END':
                    if nxt.type == 'IF':
                        normalized.append(Token('ENDIF', 'END IF', tok.line, tok.column))
                        i += 2
                        continue
                    elif nxt.type == 'WHILE':
                        normalized.append(Token('ENDWHILE', 'END WHILE', tok.line, tok.column))
                        i += 2
                        continue
                    elif nxt.type == 'FOR':
                        normalized.append(Token('ENDFOR', 'END FOR', tok.line, tok.column))
                        i += 2
                        continue
                    elif nxt.type == 'FUNCTION':
                        normalized.append(Token('ENDFUNCTION', 'END FUNCTION', tok.line, tok.column))
                        i += 2
                        continue
                    elif nxt.type == 'DEF':
                        normalized.append(Token('ENDDEF', 'END DEF', tok.line, tok.column))
                        i += 2
                        continue
                # ELSE IF
                elif tok.type == 'ELSE' and nxt.type == 'IF':
                    normalized.append(Token('ELSE_IF', 'ELSE IF', tok.line, tok.column))
                    i += 2
                    continue
                # DOWN TO
                elif tok.type == 'DOWN' and nxt.type == 'TO':
                    normalized.append(Token('DOWNTO', 'DOWN TO', tok.line, tok.column))
                    i += 2
                    continue
                # DEFINE FUNCTION
                elif tok.type == 'DEFINE' and nxt.type == 'FUNCTION':
                    normalized.append(Token('FUNCTION', 'DEFINE FUNCTION', tok.line, tok.column))
                    i += 2
                    continue

            normalized.append(tok)
            i += 1
        return normalized
