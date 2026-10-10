import re

class Token:
    def __init__(self, type_, value, line, column):
        self.type = type_
        self.value = value
        self.line = line
        self.column = column

    def __repr__(self):
        return f"Token({self.type}, {repr(self.value)}, Line: {self.line}, Col: {self.column})"

KEYWORDS = {
    'START': 'START', 'THODANGU': 'START', 'தொடங்கு': 'START',
    'STOP': 'STOP', 'MUDI': 'STOP', 'முடி': 'STOP',
    'READ': 'READ', 'PADI': 'READ', 'படி': 'READ',
    'PRINT': 'PRINT', 'KANBI': 'PRINT', 'காண்பி': 'PRINT', 'EZHUDHU': 'PRINT', 'எழுது': 'PRINT',
    'DECLARE': 'DECLARE', 'ARIVI': 'DECLARE', 'அறிவி': 'DECLARE',
    'SET': 'SET', 'AMAI': 'SET', 'அமை': 'SET',
    'IF': 'IF', 'IRUNDHAL': 'IF', 'இருந்தால்': 'IF',
    'ELSE': 'ELSE', 'ILLAIYEL': 'ELSE', 'இல்லையேல்': 'ELSE',
    'ELSE IF': 'ELSE_IF', 'ILLAIYEL IRUNDHAL': 'ELSE_IF', 'இல்லையேல் இருந்தால்': 'ELSE_IF',
    'FOR': 'FOR', 'AGA': 'FOR', 'ஆக': 'FOR',
    'WHILE': 'WHILE', 'VARAI': 'WHILE', 'வரை': 'WHILE',
    'RETURN': 'RETURN', 'THIRUMBU': 'RETURN', 'திரும்பு': 'RETURN',
    'AND': 'AND', 'MATRUM': 'AND', 'மற்றும்': 'AND',
    'OR': 'OR', 'ALLADHU': 'OR', 'அல்லது': 'OR',
    'NOT': 'NOT', 'ILLAI': 'NOT', 'இல்லை': 'NOT',
    'IMPORT': 'IMPORT', 'KONDUVA': 'IMPORT', 'கொண்டுவா': 'IMPORT',
    'THEN': 'THEN', 'APPODHU': 'THEN', 'அப்போது': 'THEN',
    'ENDIF': 'ENDIF', 'IF_MUDI': 'ENDIF',
    'DO': 'DO', 'SEI': 'DO', 'செய்': 'DO',
    'ENDWHILE': 'ENDWHILE', 'WHILE_MUDI': 'ENDWHILE',
    'TO': 'TO', 'VARAI': 'TO',
    'ENDFOR': 'ENDFOR', 'FOR_MUDI': 'ENDFOR',
    'FUNCTION': 'FUNCTION', 'SEYALPADU': 'FUNCTION', 'செயல்பாடு': 'FUNCTION',
    'ENDFUNCTION': 'ENDFUNCTION', 'FUNCTION_MUDI': 'ENDFUNCTION',
}

TOKEN_TYPES = [
    ('NUMBER',   r'\d+(\.\d*)?'),
    ('STRING',   r'"[^"]*"'),
    ('IDENTIFIER', r'[a-zA-Z_][a-zA-Z0-9_\.]*|[\u0B80-\u0BFF]+'), # Matches English (with optional dots for modules) and Tamil letters
    ('PLUS',     r'\+'),
    ('MINUS',    r'-'),
    ('MUL',      r'\*'),
    ('DIV',      r'/'),
    ('MOD',      r'%'),
    ('GTE',      r'>='),
    ('LTE',      r'<='),
    ('GT',       r'>'),
    ('LT',       r'<'),
    ('EQ',       r'=='),
    ('NEQ',      r'!='),
    ('ASSIGN',   r'='),
    ('LPAREN',   r'\('),
    ('RPAREN',   r'\)'),
    ('LBRACE',   r'\{'),
    ('RBRACE',   r'\}'),
    ('LBRACKET', r'\['),
    ('RBRACKET', r'\]'),
    ('COMMA',    r','),
    ('NEWLINE',  r'\n'),
    ('SKIP',     r'[ \t\r]+'),
    ('MISMATCH', r'.'),
]

class LexicalError(Exception):
    pass

class Lexer:
    def __init__(self, code):
        self.code = code
        self.tokens = []
        self.errors = []
    
    def tokenize(self):
        line_num = 1
        line_start = 0
        tok_regex = '|'.join('(?P<%s>%s)' % pair for pair in TOKEN_TYPES)
        
        for mo in re.finditer(tok_regex, self.code):
            kind = mo.lastgroup
            value = mo.group()
            column = mo.start() - line_start + 1
            
            if kind == 'NUMBER':
                value = float(value) if '.' in value else int(value)
                self.tokens.append(Token(kind, value, line_num, column))
            elif kind == 'STRING':
                self.tokens.append(Token(kind, value[1:-1], line_num, column))
            elif kind == 'IDENTIFIER':
                upper_val = value.upper()
                if upper_val in KEYWORDS:
                    kind = KEYWORDS[upper_val]
                self.tokens.append(Token(kind, value, line_num, column))
            elif kind == 'NEWLINE':
                line_start = mo.end()
                line_num += 1
            elif kind == 'SKIP':
                pass
            elif kind == 'MISMATCH':
                self.errors.append(f"Lexical Error at line {line_num}, column {column}: Unexpected character '{value}'")
            else:
                self.tokens.append(Token(kind, value, line_num, column))
        
        self.tokens.append(Token('EOF', '', line_num, column if 'column' in locals() else 1))
        return self.tokens, self.errors
