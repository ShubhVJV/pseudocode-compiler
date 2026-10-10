import os
from flask import Flask, request, jsonify, render_template
from transpiler import TranspilerPipeline
from transpiler.execution import ExecutionModule

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/compile', methods=['POST'])
def compile_code():
    data = request.json
    code = data.get('code', '')
    
    pipeline = TranspilerPipeline()
    result = pipeline.compile(code)
    
    return jsonify(result)

@app.route('/compile_flowchart', methods=['POST'])
def compile_flowchart():
    data = request.json
    from transpiler.flowchart_compiler import drawflow_to_pseudo
    pseudo = drawflow_to_pseudo(data)
    
    pipeline = TranspilerPipeline()
    result = pipeline.compile(pseudo)
    result["generated_pseudo"] = pseudo
    return jsonify(result)

@app.route('/execute', methods=['POST'])
def execute_code():
    data = request.json
    code = data.get('code', '')
    user_input = data.get('input', '')
    
    runner = ExecutionModule(timeout=5)
    exec_result = runner.execute(code, user_input)
    
    return jsonify(exec_result)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
