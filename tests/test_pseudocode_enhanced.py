import ast as py_ast
import pytest
from app import app
from transpiler import TranspilerPipeline
from transpiler.execution import ExecutionModule
from transpiler.flowchart_compiler import drawflow_to_pseudo


def compile_and_run(code: str, stdin_data: str = ""):
    pipeline = TranspilerPipeline()
    res = pipeline.compile(code)
    assert not res["lex_errors"], f"Lex errors: {res['lex_errors']}"
    assert not res["parse_errors"], f"Parse errors: {res['parse_errors']}"
    assert not res["semantic_errors"], f"Semantic errors: {res['semantic_errors']}"
    assert res["success"] is True
    assert not res["ai_used"]
    # Verify generated Python is syntactically valid Python
    py_ast.parse(res["python_code"])
    runner = ExecutionModule(timeout=5)
    exec_res = runner.execute(res["python_code"], stdin_data)
    assert exec_res["success"], f"Runtime error: {exec_res['error']}\nCode:\n{res['python_code']}"
    return res, exec_res["output"].rstrip("\r\n")


def compile_expect_error(code: str):
    pipeline = TranspilerPipeline()
    res = pipeline.compile(code)
    all_errors = res["lex_errors"] + res["parse_errors"] + res["semantic_errors"]
    assert not res["success"] or len(all_errors) > 0, f"Expected error for:\n{code}\nGot Python:\n{res['python_code']}"
    return all_errors


# =====================================================================
# 23.1 Assignment Tests & Rejection of SET
# =====================================================================

def test_direct_and_alias_assignments():
    code = """
x = 10
LET y = 20
ASSIGN z = 30
LET name BE "Alice"
ASSIGN total TO x + y + z
active = TRUE
inactive = FALSE
empty_val = NONE
null_val = NULL
x += 5
y -= 3
z *= 2
PRINT x, y, z, name, total, active, inactive, empty_val, null_val
"""
    _, out = compile_and_run(code)
    assert out == "15 17 60 Alice 60 True False None None"


def test_compound_division_and_arithmetic_precedence():
    code = """
a = 20
a /= 4
b = 2 + 3 * 4
c = (2 + 3) * 4
d = 17 // 5
e = 17 % 5
f = 2 ** 3 ** 2
PRINT a, b, c, d, e, f
"""
    _, out = compile_and_run(code)
    assert out == "5.0 14 20 3 2 512"


def test_set_keyword_rejected_as_assignment():
    errors = compile_expect_error("SET x = 10")
    assert any("SET" in e and "not supported" in e for e in errors)

    errors2 = compile_expect_error("""
a = 1
SET b = a + 2
PRINT b
""")
    assert any("SET" in e for e in errors2)


def test_set_allowed_in_strings_identifiers_and_python_set():
    code = """
msg = "SET x = 10 and IF y THEN END IF"
set_count = 3
unique_items = set([1, 2, 2, 3])
PRINT msg
PRINT set_count
PRINT len(unique_items)
"""
    _, out = compile_and_run(code)
    assert out.splitlines() == [
        "SET x = 10 and IF y THEN END IF",
        "3",
        "3"
    ]


def test_equality_versus_assignment_and_membership():
    code = """
a = 10
b = 10
is_same = a == b
is_diff = a != 5
blocked = ["Bob", "Eve"]
name = "Alice"
IF is_same AND is_diff AND name NOT IN blocked AND "Bob" IN blocked THEN
PRINT "OK"
END IF
"""
    _, out = compile_and_run(code)
    assert out == "OK"


# =====================================================================
# 23.2 Indentation & Block Terminator Tests
# =====================================================================

def test_indentation_independence_functions_and_conditionals():
    code_a = """FUNCTION add(a, b)
RETURN a + b
END FUNCTION
PRINT add(3, 4)"""

    code_b = """FUNCTION add(a, b)
    RETURN a + b
END FUNCTION
PRINT add(3, 4)"""

    code_c = """FUNCTION add(a, b)
            RETURN a + b
      END FUNCTION
    PRINT add(3, 4)"""

    _, out_a = compile_and_run(code_a)
    _, out_b = compile_and_run(code_b)
    _, out_c = compile_and_run(code_c)
    assert out_a == out_b == out_c == "7"


def test_inconsistent_indentation_conditionals_and_terminators():
    code1 = """
x = 5
IF x > 0 THEN
PRINT "Positive"
ELSE
PRINT "Not positive"
END IF
"""
    code2 = """
x = -3
    IF x > 0:
            PRINT "Positive"
      ELSE:
        PRINT "Not positive"
  ENDIF
"""
    code3 = """
marks = 82
IF marks >= 90
PRINT "A"
ELSE IF marks >= 75
PRINT "B"
ELIF marks >= 60 THEN
PRINT "C"
ELSEIF marks >= 50:
PRINT "D"
ELSE
PRINT "F"
END IF
"""
    assert compile_and_run(code1)[1] == "Positive"
    assert compile_and_run(code2)[1] == "Not positive"
    assert compile_and_run(code3)[1] == "B"


def test_crlf_tabs_comments_and_strings():
    code = (
        "# Header comment\r\n"
        "COMMENT Another comment line\r\n"
        "// Leading slash comment\r\n"
        "\tx = 10 // 3\r\n"
        "  \t  msg = \"  spaced   # not comment // still string  \"\r\n"
        "PRINT x\r\n"
        "PRINT msg\r\n"
    )
    res, out = compile_and_run(code)
    lines = out.splitlines()
    assert lines[0] == "3"
    assert lines[1] == "  spaced   # not comment // still string  "


def test_missing_and_mismatched_terminators_produce_errors():
    # Missing END IF
    errs1 = compile_expect_error("""
x = 10
IF x > 5 THEN
    PRINT x
""")
    assert any("Missing END IF" in e for e in errs1)

    # Mismatched terminator: END FOR instead of END IF
    errs2 = compile_expect_error("""
x = 10
IF x > 5 THEN
    PRINT x
END FOR
""")
    assert any("Unexpected END FOR" in e and "expected END IF" in e for e in errs2)

    # Unexpected top-level terminator
    errs3 = compile_expect_error("""
x = 10
END WHILE
""")
    assert any("Unexpected END WHILE" in e for e in errs3)

    # Missing expression after '='
    errs4 = compile_expect_error("""
x =
y = 5
""")
    assert any("Expected an expression after '='" in e for e in errs4)


# =====================================================================
# 23.3 Function Tests
# =====================================================================

def test_function_variants_and_default_params():
    code = """
FUNCTION zero_param()
RETURN 42
END FUNCTION

DEF greet(name, greeting = "Hello"):
PRINT greeting, name
END DEF

DEFINE FUNCTION compute(a, b = 10)
RETURN a * b
END FUNCTION

PRINT zero_param()
greet("Alice")
greet("Bob", "Hi")
PRINT compute(5)
PRINT compute(5, 3)
"""
    _, out = compile_and_run(code)
    assert out.splitlines() == [
        "42",
        "Hello Alice",
        "Hi Bob",
        "50",
        "15"
    ]


def test_function_local_scope_does_not_leak():
    code = """
FUNCTION helper(x)
local_only = x + 1
RETURN local_only
END FUNCTION

res = helper(5)
PRINT local_only
"""
    errs = compile_expect_error(code)
    assert any("Undeclared variable 'local_only'" in e for e in errs)


def test_function_validation_errors():
    # Duplicate function definition
    errs_dup_fn = compile_expect_error("""
FUNCTION foo(a)
RETURN a
END FUNCTION

FUNCTION foo(a, b)
RETURN a + b
END FUNCTION
""")
    assert any("Duplicate function definition 'foo'" in e for e in errs_dup_fn)

    # Duplicate parameter name
    errs_dup_param = compile_expect_error("""
FUNCTION add(a, a)
RETURN a
END FUNCTION
""")
    assert any("Duplicate parameter 'a'" in e for e in errs_dup_param)

    # Wrong argument count
    errs_arg_count = compile_expect_error("""
FUNCTION add(a, b)
RETURN a + b
END FUNCTION

x = add(1, 2, 3)
""")
    assert any("Function 'add' expects 2 arguments but received 3" in e for e in errs_arg_count)

    # RETURN outside function
    errs_ret = compile_expect_error("""
x = 10
RETURN x
""")
    assert any("RETURN used outside a function" in e for e in errs_ret)


# =====================================================================
# 23.4 List Tests
# =====================================================================

def test_lists_indexing_slicing_and_operations():
    code = """
empty_list = []
numbers = [10, 20, 30]
nested = [[1, 2], [3, 4]]
first = numbers[0]
last = numbers[-1]
numbers[1] = 50
numbers.append(40)
numbers.remove(10)
APPEND 60 TO numbers
ADD 70 TO numbers
REMOVE 50 FROM numbers
CREATE LIST extra = [100, 200]
sub = numbers[1:3]
nested[0][1] = 99
size = len(numbers)
PRINT empty_list
PRINT first, last, size
PRINT numbers
PRINT sub
PRINT nested[0][1]
PRINT extra
"""
    _, out = compile_and_run(code)
    assert out.splitlines() == [
        "[]",
        "10 30 4",
        "[30, 40, 60, 70]",
        "[40, 60]",
        "99",
        "[100, 200]"
    ]


# =====================================================================
# 23.5 Tuple Tests
# =====================================================================

def test_tuples_literals_unpacking_and_paren_distinction():
    code = """
empty_tuple = ()
single_item = (10,)
just_int = (10)
point = (10, 20)
nested = ((1, 2), (3, 4))
first = point[0]
sliced = (1, 2, 3, 4)[1:3]
x, y = point
PRINT type(empty_tuple).__name__
PRINT type(single_item).__name__
PRINT type(just_int).__name__
PRINT first, x, y
PRINT sliced
PRINT nested[1][0]
"""
    _, out = compile_and_run(code)
    assert out.splitlines() == [
        "tuple",
        "tuple",
        "int",
        "10 10 20",
        "(2, 3)",
        "3"
    ]


def test_tuple_validation_errors():
    # Unpacking count mismatch
    errs_unpack = compile_expect_error("""
point = (10, 20)
a, b, c = point
""")
    assert any("Tuple unpacking mismatch" in e for e in errs_unpack)

    # Tuple immutability on indexed assignment
    errs_immut = compile_expect_error("""
point = (10, 20)
point[0] = 99
""")
    assert any("Cannot modify tuple 'point'" in e for e in errs_immut)

    # Tuple immutability on append
    errs_append = compile_expect_error("""
point = (10, 20)
APPEND 30 TO point
""")
    assert any("tuple" in e.lower() for e in errs_append)


# =====================================================================
# 23.6 Loop Tests
# =====================================================================

def test_while_and_for_loops_with_break_continue_and_steps():
    code = """
# For-each loop with break and continue
items = [1, 2, 3, 4, 5, 6]
kept = []
FOR EACH n IN items
IF n == 2 THEN
CONTINUE
END IF
IF n == 5 THEN
BREAK
END IF
APPEND n TO kept
END FOR
PRINT kept

# Step loop ascending
evens = []
FOR i FROM 0 TO 10 STEP 2
evens.append(i)
END FOR
PRINT evens

# Descending loop with DOWN TO
desc = []
FOR i FROM 5 DOWN TO 0 STEP 1
desc.append(i)
END FOR
PRINT desc

#FOR i IN RANGE
r_list = []
FOR i IN RANGE(0, 4)
r_list.append(i)
END FOR
PRINT r_list
"""
    _, out = compile_and_run(code)
    assert out.splitlines() == [
        "[1, 3, 4]",
        "[0, 2, 4, 6, 8]",
        "[5, 4, 3, 2, 1]",
        "[0, 1, 2, 3]"
    ]


def test_loop_semantic_errors():
    # Zero step
    errs_zero = compile_expect_error("""
FOR i FROM 0 TO 10 STEP 0
PRINT i
END FOR
""")
    assert any("Numeric range step cannot be zero" in e for e in errs_zero)

    # BREAK outside loop
    errs_break = compile_expect_error("""
x = 1
BREAK
""")
    assert any("BREAK used outside a loop" in e for e in errs_break)

    # CONTINUE outside loop
    errs_cont = compile_expect_error("""
x = 1
CONTINUE
""")
    assert any("CONTINUE used outside a loop" in e for e in errs_cont)


# =====================================================================
# 23.7 Combined Programs (Tests A, B, C, D, E)
# =====================================================================

def test_combined_program_a_sum_positive():
    code = """FUNCTION sum_positive(numbers)
total = 0
FOR EACH number IN numbers
IF number > 0 THEN
total = total + number
END IF
END FOR
RETURN total
END FUNCTION

values = [10, -2, 5]
result = sum_positive(values)
PRINT result"""
    _, out = compile_and_run(code)
    assert out == "15"


def test_combined_program_b_recursive_factorial():
    code = """FUNCTION factorial(n)
IF n <= 1 THEN
RETURN 1
ELSE
RETURN n * factorial(n - 1)
END IF
END FUNCTION

PRINT factorial(5)"""
    _, out = compile_and_run(code)
    assert out == "120"


def test_combined_program_c_tuple_unpacking():
    code = """point = (10, 20)
x, y = point
PRINT x
PRINT y"""
    _, out = compile_and_run(code)
    assert out.splitlines() == ["10", "20"]


def test_combined_program_d_while_loop_without_indentation():
    code = """i = 0
total = 0
WHILE i < 5 DO
total = total + i
i += 1
END WHILE
PRINT total"""
    _, out = compile_and_run(code)
    assert out == "10"


def test_combined_program_e_numeric_range_semantics():
    code_exclusive = """total = 0
FOR i FROM 0 TO 5
total = total + i
END FOR
PRINT total"""
    res_ex, out_ex = compile_and_run(code_exclusive)
    assert "for i in range(0, 5):" in res_ex["python_code"]
    assert out_ex == "10"

    code_inclusive = """total = 0
FOR i FROM 0 THROUGH 5
total = total + i
END FOR
PRINT total"""
    res_inc, out_inc = compile_and_run(code_inclusive)
    assert "for i in range(0, 6):" in res_inc["python_code"]
    assert out_inc == "15"


# =====================================================================
# 24. Regression Tests for Flowchart, Tamil/Tanglish, and APIs
# =====================================================================

def test_regression_tamil_script_and_tanglish():
    tanglish_code = """THODANGU
ARIVI a = 15
ARIVI b = 25
AMAI a = a + 5
IRUNDHAL a < b APPODHU
    KANBI a
ILLAIYEL
    KANBI b
IF_MUDI
MUDI"""
    pipeline = TranspilerPipeline()
    res1 = pipeline.compile(tanglish_code)
    assert res1["success"]
    assert not res1["lex_errors"] and not res1["parse_errors"] and not res1["semantic_errors"]

    tamil_script_code = """தொடங்கு
அறிவி x = 10
அமை x = x + 20
காண்பி x
முடி"""
    res2 = pipeline.compile(tamil_script_code)
    assert res2["success"]
    runner = ExecutionModule(timeout=5)
    assert runner.execute(res2["python_code"])["output"].strip() == "30"


def test_regression_flowchart_compilation():
    sample_drawflow = {
        "drawflow": {
            "Home": {
                "data": {
                    "1": {"id": 1, "name": "start", "data": {}, "inputs": {}, "outputs": {"output_1": {"connections": [{"node": "2", "output": "input_1"}]}}},
                    "2": {"id": 2, "name": "process", "data": {"process": "A = 10"}, "inputs": {"input_1": {"connections": [{"node": "1", "input": "output_1"}]}}, "outputs": {"output_1": {"connections": [{"node": "3", "output": "input_1"}]}}},
                    "3": {"id": 3, "name": "process", "data": {"process": "B = 20"}, "inputs": {"input_1": {"connections": [{"node": "2", "input": "output_1"}]}}, "outputs": {"output_1": {"connections": [{"node": "4", "output": "input_1"}]}}},
                    "4": {"id": 4, "name": "decision", "data": {"condition": "A < B"}, "inputs": {"input_1": {"connections": [{"node": "3", "input": "output_1"}]}}, "outputs": {
                        "output_1": {"connections": [{"node": "5", "output": "input_1"}]},
                        "output_2": {"connections": [{"node": "6", "output": "input_1"}]}
                    }},
                    "5": {"id": 5, "name": "output", "data": {"output": "B"}, "inputs": {"input_1": {"connections": [{"node": "4", "input": "output_1"}]}}, "outputs": {"output_1": {"connections": [{"node": "7", "output": "input_1"}]}}},
                    "6": {"id": 6, "name": "output", "data": {"output": "A"}, "inputs": {"input_1": {"connections": [{"node": "4", "input": "output_2"}]}}, "outputs": {"output_1": {"connections": [{"node": "7", "output": "input_1"}]}}},
                    "7": {"id": 7, "name": "end", "data": {}, "inputs": {"input_1": {"connections": [{"node": "5", "input": "output_1"}, {"node": "6", "input": "output_1"}]}}, "outputs": {}}
                }
            }
        }
    }
    pseudo = drawflow_to_pseudo(sample_drawflow)
    _, out = compile_and_run(pseudo)
    assert out == "20"


def test_regression_flask_endpoints_and_schemas():
    client = app.test_client()

    # GET /
    r_index = client.get('/')
    assert r_index.status_code == 200

    # POST /compile
    r_comp = client.post('/compile', json={"code": "x = 5\nPRINT x * 2"})
    assert r_comp.status_code == 200
    data = r_comp.get_json()
    expected_keys = {
        "tokens", "lex_errors", "parse_errors", "semantic_errors",
        "python_code", "ai_used", "ai_reason", "ai_structured",
        "ast_tree", "cfg_mermaid", "tac", "optimized_ir", "symbol_table", "success"
    }
    assert expected_keys.issubset(set(data.keys()))
    assert data["success"] is True

    # POST /execute
    r_exec = client.post('/execute', json={"code": data["python_code"], "input": ""})
    assert r_exec.status_code == 200
    exec_data = r_exec.get_json()
    assert exec_data["success"] is True
    assert exec_data["output"].strip() == "10"


def test_input_and_output_variants_with_stdin():
    code = """
INPUT name
READ age
city = INPUT("City: ")
PRINT name
DISPLAY age
OUTPUT city
"""
    res, out = compile_and_run(code, stdin_data="Alice\n22\nChennai\n")
    assert 'city = input("City: ")' in res["python_code"]
    assert out.splitlines() == ["City: Alice", "22", "Chennai"]


def test_functions_with_lists_and_tuples_and_forward_calls():
    code = """
FUNCTION main_logic(items)
pair = min_and_max(items)
low, high = pair
RETURN [low, high, high - low]
END FUNCTION

FUNCTION min_and_max(arr)
m1 = arr[0]
m2 = arr[0]
FOR item IN arr:
IF item < m1 THEN
m1 = item
END IF
IF item > m2 THEN
m2 = item
END IF
ENDFOR
RETURN (m1, m2)
END FUNCTION

nums = [12, 4, 19, 7]
res = main_logic(nums)
PRINT res
"""
    _, out = compile_and_run(code)
    assert out == "[4, 19, 15]"


def test_nested_loops_and_range_variants_without_indentation():
    code = """
pairs = []
FOR i = 1 THROUGH 3
j = 0
WHILE j < 2
pairs.append((i, j))
j += 1
ENDWHILE
ENDFOR
PRINT pairs

neg_steps = []
FOR k FROM 10 TO 0 STEP -3
neg_steps.append(k)
END FOR
PRINT neg_steps
"""
    _, out = compile_and_run(code)
    assert out.splitlines() == [
        "[(1, 0), (1, 1), (2, 0), (2, 1), (3, 0), (3, 1)]",
        "[10, 7, 4, 1]"
    ]


def test_lexical_and_security_validations():
    # Invalid identifier starting with digit
    errs_id = compile_expect_error("123invalid = 10")
    assert any("Invalid identifier" in e for e in errs_id)

    # Unterminated string literal
    errs_str = compile_expect_error('msg = "unterminated')
    assert any("Unterminated string" in e for e in errs_str)

    # Unapproved import
    errs_imp = compile_expect_error("IMPORT subprocess")
    assert any("not approved" in e for e in errs_imp)


def test_ai_fallback_nlp_and_simple_error_recovery(monkeypatch):
    monkeypatch.setenv("FORCE_AI_IN_TESTS", "1")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_mock_test_key")

    from transpiler.ai_module import AIModule

    # 1. Mock NLP translation
    def mock_nlp_json(self, sys_prompt, usr_prompt):
        return {
            "intent": "Create a list of numbers and print their sum",
            "pseudocode": "nums = [10, 20, 30]\nPRINT sum(nums)"
        }

    monkeypatch.setattr(AIModule, "_request_llm_json", mock_nlp_json)
    pipeline = TranspilerPipeline()
    res = pipeline.compile("please make a list of 10, 20, 30 and print its sum")
    assert res["success"] is True
    assert res["ai_used"] is True
    assert "nums = [10, 20, 30]" in res["python_code"]
    assert "print(sum(nums))" in res["python_code"]

    # 2. Mock security check: AI returning unapproved import is blocked by SemanticAnalyzer
    def mock_unsafe_json(self, sys_prompt, usr_prompt):
        return {
            "intent": "Unsafe import attempt",
            "pseudocode": "IMPORT subprocess\nPRINT 1"
        }

    monkeypatch.setattr(AIModule, "_request_llm_json", mock_unsafe_json)
    pipeline2 = TranspilerPipeline()
    res2 = pipeline2.compile("run a shell command with subprocess")
    assert res2["success"] is False
