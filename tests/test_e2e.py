import pytest
from transpiler import TranspilerPipeline

def test_structured_pseudocode():
    code = """START
DECLARE a = 5
DECLARE b = 10
IF a < b THEN
    PRINT a
ELSE
    PRINT b
ENDIF
STOP"""
    pipeline = TranspilerPipeline()
    result = pipeline.compile(code)
    
    assert not result["lex_errors"]
    assert not result["parse_errors"]
    assert not result["semantic_errors"]
    assert not result["ai_used"]
    assert "a = 5" in result["python_code"]
    assert "if (a < b):" in result["python_code"]

def test_tamil_keywords():
    code = """THODANGU
ARIVI a = 5
ARIVI b = 10
IRUNDHAL a < b
    KANBI a
ILLAIYEL
    KANBI b
MUDI"""
    pipeline = TranspilerPipeline()
    result = pipeline.compile(code)
    
    assert not result["lex_errors"]
    assert not result["parse_errors"]
    assert not result["semantic_errors"]
    assert not result["ai_used"]

def test_undeclared_variable():
    code = """START
a = b + 5
STOP"""
    pipeline = TranspilerPipeline()
    result = pipeline.compile(code)
    
    assert len(result["semantic_errors"]) > 0
    assert any("Undeclared variable 'b'" in err for err in result["semantic_errors"])

def test_duplicate_declaration():
    code = """START
DECLARE a = 5
DECLARE a = 10
STOP"""
    pipeline = TranspilerPipeline()
    result = pipeline.compile(code)
    
    assert len(result["semantic_errors"]) > 0
    assert "Duplicate declaration of 'a'" in result["semantic_errors"][0]

def test_natural_language_rule_based():
    code = "add 5 and 6"
    pipeline = TranspilerPipeline()
    result = pipeline.compile(code)
    
    assert not result["ai_used"]
    assert "sum = (5 + 6)" in result["python_code"]

def test_while_loop():
    code = """START
DECLARE i = 0
WHILE i < 5 DO
    PRINT i
    i = i + 1
ENDWHILE
STOP"""
    pipeline = TranspilerPipeline()
    result = pipeline.compile(code)
    assert "while (i < 5):" in result["python_code"]

def test_import():
    code = """START
IMPORT math
IMPORT os
STOP"""
    pipeline = TranspilerPipeline()
    result = pipeline.compile(code)
    
    assert len(result["semantic_errors"]) == 1
    assert "not approved" in result["semantic_errors"][0]
    assert "os" in result["semantic_errors"][0]
