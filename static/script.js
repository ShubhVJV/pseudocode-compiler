// Initial Code Placeholders
const placeholders = {
    pseudocode: `START
a = 10
b = 20
IF a < b THEN
    PRINT "a is smaller"
ELSE
    PRINT "b is smaller"
ENDIF
STOP`,
    tamil: `THODANGU
a = 10
b = 20
IRUNDHAL a < b
    KANBI "a is smaller"
ILLAIYEL
    KANBI "b is smaller"
IF_MUDI
MUDI`
};

const editor = document.getElementById('source-code');
const editorTitle = document.getElementById('editor-title');
editor.value = placeholders.pseudocode;

// UI State Toggles


function openTab(tabId, el) {
    document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    
    const target = document.getElementById(tabId);
    target.style.display = 'block';
    target.classList.add('fade-in');
    setTimeout(() => target.classList.remove('fade-in'), 400);
    
    el.classList.add('active');
}

// Compile Code
document.getElementById('btn-compile').addEventListener('click', async () => {
    const code = editor.value;
    const btnCompile = document.getElementById('btn-compile');
    const btnExecute = document.getElementById('btn-execute');
    const pythonOutput = document.getElementById('python-output');
    const tokenTbody = document.querySelector('#token-table tbody');
    const diagnosticsBox = document.getElementById('diagnostics-box');
    const aiIndicator = document.getElementById('ai-indicator');
    const aiStatus = document.getElementById('ai-status');
    const aiJson = document.getElementById('ai-json');
    const compileStatus = document.getElementById('compile-status');
    
    // UI Loading State
    btnCompile.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Compiling...';
    btnCompile.disabled = true;
    diagnosticsBox.className = 'info-box';
    diagnosticsBox.innerHTML = 'Compiling...';
    compileStatus.className = 'status-badge';
    compileStatus.innerText = 'Working...';
    aiIndicator.style.display = 'none';
    
    let endpoint = '/compile';
    let payload = {};
    if (currentMode === 'flowchart') {
        if (!editorFlow) return;
        payload = editorFlow.export();
        endpoint = '/compile_flowchart';
    } else {
        payload = { code: code };
    }

    try {
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        
        // Auto-show panels in flowchart mode if compile succeeded
        if (currentMode === 'flowchart' && !flowchartPanelsVisible) {
            toggleFlowchartPanels();
        }
        
        updatePipeline(data);
        
        // Tokens
        tokenTbody.innerHTML = '';
        data.tokens.forEach(t => {
            tokenTbody.innerHTML += `<tr><td><span class="badge" style="background:var(--border-color)">${t.type}</span></td><td>${t.value}</td><td>${t.line}</td><td>${t.col}</td></tr>`;
        });
        
        // Symbol Table
        const symbolTbody = document.querySelector('#symbol-table tbody');
        symbolTbody.innerHTML = '';
        if (data.symbol_table) {
            data.symbol_table.forEach(s => {
                symbolTbody.innerHTML += `<tr>
                    <td><strong>${s.name}</strong></td>
                    <td style="color:var(--accent-green)">${s.type}</td>
                    <td>${s.scope}</td>
                    <td><span class="badge" style="background:var(--border-color)">${s.kind}</span></td>
                </tr>`;
            });
        }
        
        // AST Tree
        const astContainer = document.getElementById('ast-tree-container');
        if (data.ast_tree) {
            astContainer.innerHTML = `<div class="ast-node">${renderAST(data.ast_tree)}</div>`;
        } else {
            astContainer.innerHTML = 'No AST generated.';
        }
        if (data.generated_pseudo && currentMode === 'flowchart') {
            editor.value = data.generated_pseudo;
            updateLineNumbers(editor, editorLines);
        }
        
        // CFG Mermaid
        const cfgContainer = document.getElementById('cfg-container');
        if (data.cfg_mermaid) {
            try {
                const { svg } = await mermaid.render('mermaid-svg-' + Date.now(), data.cfg_mermaid);
                cfgContainer.innerHTML = svg;
            } catch (err) {
                console.error("Mermaid error:", err);
                cfgContainer.innerHTML = `<pre style="color:red">Mermaid syntax error</pre>`;
            }
        } else {
            cfgContainer.innerHTML = 'No CFG generated.';
        }
        
        // TAC & IR
        document.getElementById('tac-container').innerText = data.tac ? data.tac.join('\n') : 'No TAC generated.';
        document.getElementById('opt-container').innerText = data.optimized_ir ? data.optimized_ir.join('\n') : 'No Optimized IR.';
        
        // Handle Errors (If manual failed and AI didn't rescue)
        let manualErrors = [];
        if (data.lex_errors && data.lex_errors.length) manualErrors.push(...data.lex_errors);
        if (data.parse_errors && data.parse_errors.length) manualErrors.push(...data.parse_errors);
        if (data.semantic_errors && data.semantic_errors.length) manualErrors.push(...data.semantic_errors);
        
        if (!data.success) {
            diagnosticsBox.className = 'info-box error';
            diagnosticsBox.innerHTML = `<strong>Compilation Failed:</strong><br><br>${manualErrors.join('<br>')}`;
            pythonOutput.innerText = "Compilation failed.";
            compileStatus.className = 'status-badge error';
            compileStatus.innerText = 'Failed';
            btnExecute.disabled = true;
        } else {
            diagnosticsBox.className = 'info-box success';
            diagnosticsBox.innerHTML = "<strong>Success:</strong> Code compiled perfectly!";
            pythonOutput.innerText = data.python_code || "No code generated.";
            compileStatus.className = 'status-badge success';
            compileStatus.innerText = 'Success';
            btnExecute.disabled = false;
        }
        
        updateLineNumbers({value: pythonOutput.innerText}, pythonLines);
        
        // AI Fallback Handler
        if (data.ai_used) {
            aiIndicator.style.display = 'flex';
            diagnosticsBox.className = 'info-box warning';
            diagnosticsBox.innerHTML = `<strong>Warning (AI Assisted):</strong> Encountered syntax/semantic issues, but successfully recovered using AI.<br><br><strong>Original Errors:</strong><br>See AI Insights tab for details.`;
            aiStatus.className = 'info-box warning';
            aiStatus.innerHTML = `<strong>AI Activated:</strong> ${data.ai_reason}`;
            aiJson.innerText = JSON.stringify(data.ai_structured, null, 2);
            compileStatus.className = 'status-badge warning';
            compileStatus.innerText = 'AI Fixed';
        } else {
            aiStatus.className = 'info-box';
            aiStatus.innerHTML = "AI not used for this translation (Deterministic Compilation).";
            aiJson.innerText = "";
        }
        
    } catch (e) {
        diagnosticsBox.className = 'info-box error';
        diagnosticsBox.innerHTML = `Network error: ${e.message}`;
        compileStatus.className = 'status-badge error';
        compileStatus.innerText = 'Network Error';
    } finally {
        btnCompile.innerHTML = '<i class="fa-solid fa-play"></i> Compile';
        btnCompile.disabled = false;
    }
});

// Execute Python Code
document.getElementById('btn-execute').addEventListener('click', async () => {
    const code = document.getElementById('python-output').innerText;
    const input = document.getElementById('stdin').value;
    const execOut = document.getElementById('execution-output');
    const btnExecute = document.getElementById('btn-execute');
    
    btnExecute.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Executing...';
    btnExecute.disabled = true;
    execOut.innerHTML = "Executing...";
    execOut.style.color = "inherit";
    
    try {
        const res = await fetch('/execute', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({code, input})
        });
        const data = await res.json();
        
        if (data.success) {
            execOut.innerText = data.output || "(Program exited with no output)";
            execOut.style.color = "#a7f3d0"; // nice green
        } else {
            execOut.innerText = `Error:\n${data.error}`;
            execOut.style.color = "#ef4444"; // error red
        }
    } catch (e) {
        execOut.innerText = `Network error: ${e.message}`;
        execOut.style.color = "#ef4444";
    } finally {
        btnExecute.innerHTML = '<i class="fa-solid fa-terminal"></i> Execute';
        btnExecute.disabled = false;
    }
});

// AST Visualizer
function renderAST(node, key = null) {
    if (node === null) return '<span class="ast-value">null</span>';
    
    if (Array.isArray(node)) {
        if (node.length === 0) return '<span class="ast-value">[]</span>';
        let html = '<div class="ast-children">';
        node.forEach((child, i) => {
            html += `<div class="ast-node">
                <span class="ast-key">[${i}]:</span>
                ${renderAST(child)}
            </div>`;
        });
        html += '</div>';
        return html;
    }
    
    if (typeof node === 'object') {
        const type = node._type || 'Object';
        let html = `<span class="ast-type">${type}</span><div class="ast-children">`;
        
        for (const [k, v] of Object.entries(node)) {
            if (k === '_type') continue;
            html += `<div class="ast-node">
                <span class="ast-key">${k}:</span>
                ${renderAST(v, k)}
            </div>`;
        }
        html += '</div>';
        return html;
    }
    
    return `<span class="ast-value">${JSON.stringify(node)}</span>`;
}

// Line Numbers Logic
function updateLineNumbers(textarea, lineNumbersEl) {
    const linesCount = textarea.value.split('\n').length;
    let linesHtml = '';
    for (let i = 1; i <= linesCount; i++) {
        linesHtml += i + '<br>';
    }
    lineNumbersEl.innerHTML = linesHtml;
}

const editorLines = document.getElementById('editor-lines');
const pythonLines = document.getElementById('python-lines');
const pythonOutput = document.getElementById('python-output');

editor.addEventListener('input', () => {
    updateLineNumbers(editor, editorLines);
});

// Sync scrolling
editor.addEventListener('scroll', () => {
    editorLines.scrollTop = editor.scrollTop;
});
pythonOutput.addEventListener('scroll', () => {
    pythonLines.scrollTop = pythonOutput.scrollTop;
});

// Run once on load
updateLineNumbers(editor, editorLines);

updateLineNumbers({value: pythonOutput.innerText}, pythonLines);

// Pipeline UI logic
function updatePipeline(data) {
    const container = document.getElementById('pipeline-container');
    const chevron = document.getElementById('pipeline-chevron');
    if (container && container.style.display === 'none') {
        container.style.display = 'block';
        if (chevron) chevron.style.transform = 'rotate(180deg)';
    }

    const steps = ['lex', 'parse', 'sem', 'ai', 'ir', 'gen'];
    steps.forEach(s => {
        const el = document.getElementById('step-' + s);
        if (el) el.className = 'pipeline-step';
    });
    
    document.querySelectorAll('.pipeline-connector').forEach(el => {
        el.className = 'pipeline-connector';
    });

    const stepLex = document.getElementById('step-lex');
    const stepParse = document.getElementById('step-parse');
    const stepSem = document.getElementById('step-sem');
    const stepAi = document.getElementById('step-ai');
    const stepIr = document.getElementById('step-ir');
    const stepGen = document.getElementById('step-gen');
    
    const connLexParse = document.getElementById('conn-lex-parse');
    const connParseSem = document.getElementById('conn-parse-sem');
    const connSemIr = document.getElementById('conn-sem-ir');
    const connAiIr = document.getElementById('conn-ai-ir');
    const connIrGen = document.getElementById('conn-ir-gen');

    // Reset visibility
    stepAi.style.display = 'none';
    connAiIr.style.display = 'none';
    
    const dLex = document.getElementById('detail-lex');
    const dParse = document.getElementById('detail-parse');
    const dSem = document.getElementById('detail-sem');
    const dAi = document.getElementById('detail-ai');
    const dIr = document.getElementById('detail-ir');
    const dGen = document.getElementById('detail-gen');

    // 1. Lexical
    if (data.lex_errors && data.lex_errors.length > 0) {
        stepLex.classList.add('error');
        dLex.innerText = `${data.lex_errors.length} error(s)`;
        if (data.ai_used) {
            connLexParse.classList.add('warning');
            stepLex.classList.replace('error', 'warning');
        } else {
            connLexParse.classList.add('error');
            return;
        }
    } else {
        stepLex.classList.add('success');
        connLexParse.classList.add('success');
        dLex.innerText = `${data.tokens ? data.tokens.length : 0} tokens`;
    }

    // 2. Parse
    if (data.parse_errors && data.parse_errors.length > 0) {
        stepParse.classList.add('error');
        dParse.innerText = `${data.parse_errors.length} error(s)`;
        if (data.ai_used) {
            connParseSem.classList.add('warning');
            stepParse.classList.replace('error', 'warning');
        } else {
            connParseSem.classList.add('error');
            return;
        }
    } else {
        stepParse.classList.add('success');
        connParseSem.classList.add('success');
        dParse.innerText = `AST Created`;
    }

    // 3. Semantic
    if (data.semantic_errors && data.semantic_errors.length > 0) {
        stepSem.classList.add('error');
        dSem.innerText = `${data.semantic_errors.length} error(s)`;
        if (data.ai_used) {
            connSemIr.classList.add('warning');
            stepSem.classList.replace('error', 'warning');
        } else {
            connSemIr.classList.add('error');
            return;
        }
    } else {
        stepSem.classList.add('success');
        connSemIr.classList.add('success');
        dSem.innerText = `${data.symbol_table ? data.symbol_table.length : 0} symbols`;
    }

    // 4. AI
    if (data.ai_used) {
        stepAi.style.display = 'flex';
        connAiIr.style.display = 'block';
        
        stepAi.classList.add('success'); // AI successfully recovered it
        connAiIr.classList.add('success');
        dAi.innerText = `Auto-Fixed AST`;
        
        // Hide sem->ir direct line to show it routed through AI
        connSemIr.style.display = 'none';
    } else {
        connSemIr.style.display = 'block';
    }

    // 5. IR Optimizer
    if (data.success) {
        stepIr.classList.add('success');
        connIrGen.classList.add('success');
        const optLines = data.optimized_ir ? data.optimized_ir.length : 0;
        dIr.innerText = `${optLines} instructions`;
    } else {
        stepIr.classList.add('error');
        connIrGen.classList.add('error');
        dIr.innerText = 'Skipped';
        return;
    }

    // 6. Code Gen
    if (data.success) {
        stepGen.classList.add('success');
        dGen.innerText = `${data.python_code ? data.python_code.split('\\n').length : 0} lines`;
    } else {
        stepGen.classList.add('error');
        dGen.innerText = 'Failed';
    }
}

// Pipeline Toggle Logic
function togglePipeline() {
    const container = document.getElementById('pipeline-container');
    const chevron = document.getElementById('pipeline-chevron');
    if (container.style.display === 'none') {
        container.style.display = 'block';
        chevron.style.transform = 'rotate(180deg)';
    } else {
        container.style.display = 'none';
        chevron.style.transform = 'rotate(0deg)';
    }
}

// Resizer Logic
const gutterH = document.getElementById('gutter-h');
const gutterV = document.getElementById('gutter-v');
const topPane = document.getElementById('top-pane');
const editorPanel = document.getElementById('editor-panel');
const outputPanel = document.getElementById('output-panel');

let isResizingH = false;
let isResizingV = false;

gutterH.addEventListener('mousedown', (e) => {
    isResizingH = true;
    gutterH.classList.add('active');
    document.body.style.cursor = 'col-resize';
});

gutterV.addEventListener('mousedown', (e) => {
    isResizingV = true;
    gutterV.classList.add('active');
    document.body.style.cursor = 'row-resize';
});

document.addEventListener('mousemove', (e) => {
    if (!isResizingH && !isResizingV) return;
    
    // Prevent text selection while dragging
    e.preventDefault();
    
    if (isResizingH) {
        // Calculate new flex basis for editor-panel
        const containerRect = topPane.getBoundingClientRect();
        // Mouse position relative to the container
        const newWidth = e.clientX - containerRect.left;
        const totalWidth = containerRect.width;
        // Set flex-basis as a percentage
        const percentage = (newWidth / totalWidth) * 100;
        
        // Constrain to 10% - 90%
        if (percentage > 10 && percentage < 90) {
            editorPanel.style.flex = `0 0 ${percentage}%`;
            outputPanel.style.flex = `1 1 0%`; // Take up remaining
        }
    }
    
    if (isResizingV) {
        // Find the main-content rect
        const containerRect = document.querySelector('.main-content').getBoundingClientRect();
        const newHeight = e.clientY - containerRect.top;
        const totalHeight = containerRect.height;
        const percentage = (newHeight / totalHeight) * 100;
        
        if (percentage > 20 && percentage < 80) {
            topPane.style.flex = `0 0 ${percentage}%`;
        }
    }
});

document.addEventListener('mouseup', () => {
    isResizingH = false;
    isResizingV = false;
    gutterH.classList.remove('active');
    gutterV.classList.remove('active');
    document.body.style.cursor = 'default';
});

// Pipeline Reset Logic
function resetPipeline() {
    const steps = ['lex', 'parse', 'sem', 'ai', 'ir', 'gen'];
    steps.forEach(s => {
        const el = document.getElementById('step-' + s);
        if (el) el.className = 'pipeline-step';
        const detail = document.getElementById('detail-' + s);
        if (detail) detail.innerText = 'Waiting...';
    });
    document.querySelectorAll('.pipeline-connector').forEach(el => {
        el.className = 'pipeline-connector';
    });
    
    const stepAi = document.getElementById('step-ai');
    const connAiIr = document.getElementById('conn-ai-ir');
    const connSemIr = document.getElementById('conn-sem-ir');
    
    if (stepAi) stepAi.style.display = 'none';
    if (connAiIr) connAiIr.style.display = 'none';
    if (connSemIr) connSemIr.style.display = 'block';
}

editor.addEventListener('input', () => {
    resetPipeline();
});

// Initialize Mermaid
mermaid.initialize({ startOnLoad: false, theme: 'default' });

// --- Flowchart (Drawflow) Logic ---
let editorFlow = null;
let currentMode = 'pseudocode';

function switchMode(mode, element) {
    currentMode = mode;
    document.querySelectorAll('.nav-links li').forEach(el => el.classList.remove('active'));
    if(element) element.classList.add('active');
    
    if (mode === 'flowchart') {
        flowchartPanelsVisible = false;
        document.getElementById('editor-panel').style.display = 'none';
        document.getElementById('output-panel').style.display = 'none';
        document.getElementById('gutter-v').style.display = 'none';
        document.getElementById('gutter-h').style.display = 'none';
        
        const insp = document.getElementById('bottom-pane');
        if (insp) insp.style.display = 'none';
        
        const pipe = document.getElementById('pipeline-container');
        if (pipe) pipe.style.display = 'none';
        
        document.getElementById('flowchart-panel').style.display = 'flex';
        // Make the top pane take the entire height
        document.querySelector('.top-pane').style.flex = '1';
        document.querySelector('.top-pane').style.minHeight = '100%';
        
        // Init drawflow on first open
        if (!editorFlow) {
            const id = document.getElementById("drawflow");
            editorFlow = new Drawflow(id);
            editorFlow.start();
            editorFlow.reroute = true;
            
            
            // Build default flowchart: Maximum of two numbers
            const nStart = spawnNode('start', 50, 150);
            const nInA = spawnNode('input', 250, 150, { input: 'A' });
            const nInB = spawnNode('input', 500, 150, { input: 'B' });
            const nDec = spawnNode('decision', 750, 150, { condition: 'A > B' });
            const nOutA = spawnNode('output', 1050, 50, { output: 'A' });
            const nOutB = spawnNode('output', 1050, 250, { output: 'B' });
            const nEnd = spawnNode('end', 1300, 150);
            
            editorFlow.addConnection(nStart, nInA, 'output_1', 'input_1');
            editorFlow.addConnection(nInA, nInB, 'output_1', 'input_1');
            editorFlow.addConnection(nInB, nDec, 'output_1', 'input_1');
            editorFlow.addConnection(nDec, nOutA, 'output_1', 'input_1');
            editorFlow.addConnection(nDec, nOutB, 'output_2', 'input_1');
            editorFlow.addConnection(nOutA, nEnd, 'output_1', 'input_1');
            editorFlow.addConnection(nOutB, nEnd, 'output_1', 'input_1');
        }
    } else {
        document.getElementById('flowchart-panel').style.display = 'none';
        document.getElementById('editor-panel').style.display = 'flex';
        document.getElementById('output-panel').style.display = 'flex';
        document.getElementById('gutter-v').style.display = 'block';
        document.getElementById('gutter-h').style.display = 'block';
        
        const insp = document.getElementById('bottom-pane');
        if (insp) insp.style.display = 'flex';
        
        const pipe = document.getElementById('pipeline-container');
        if (pipe) pipe.style.display = 'block';
        
        document.querySelector('.top-pane').style.flex = '2';
        document.querySelector('.top-pane').style.minHeight = '250px';
        
        const langMap = {
            'pseudocode': 'START\n\nSTOP',
            'tamil': 'THODANGU\n\nMUDI'
        };
        const titleMap = {
            'pseudocode': 'Pseudocode Input',
            'tamil': 'Tamil / Tanglish Input'
        };
        document.getElementById('source-code').value = langMap[mode] || '';
        document.getElementById('editor-title').innerText = titleMap[mode] || 'Input';
        updateLineNumbers(document.getElementById('source-code'), document.getElementById('editor-lines'));
    }
}

function spawnNode(type, x, y, initialData = {}) {
    let html = '';
    let inputs = 1;
    let outputs = 1;
    let nodeData = { ...initialData };
    
    if (type === 'start') { 
        inputs = 0; 
        html = `<div class="title-box"><i class="fa-solid fa-play"></i> START</div>`;
    }
    else if (type === 'end') { 
        outputs = 0; 
        html = `<div class="title-box"><i class="fa-solid fa-stop"></i> END</div>`;
    }
    else if (type === 'input') {
        if (!('input' in nodeData)) nodeData.input = '';
        html = `<div class="title-box"><i class="fa-solid fa-keyboard"></i> INPUT</div><input type="text" df-input placeholder="Var name (e.g. A)" onmousedown="event.stopPropagation()">`;
    }
    else if (type === 'output') {
        if (!('output' in nodeData)) nodeData.output = '';
        html = `<div class="title-box"><i class="fa-solid fa-print"></i> OUTPUT</div><input type="text" df-output placeholder="Expression (e.g. A + B)" onmousedown="event.stopPropagation()">`;
    }
    else if (type === 'process') {
        if (!('process' in nodeData)) nodeData.process = '';
        html = `<div class="title-box"><i class="fa-solid fa-cog"></i> PROCESS</div><input type="text" df-process placeholder="e.g. A = 10" onmousedown="event.stopPropagation()">`;
    }
    else if (type === 'decision') { 
        outputs = 2; 
        if (!('condition' in nodeData)) nodeData.condition = '';
        html = `<div class="title-box"><i class="fa-solid fa-code-branch"></i> DECISION</div><input type="text" df-condition placeholder="e.g. A > B" onmousedown="event.stopPropagation()"><div style="font-size: 10px; margin-top:5px;">Out 1: True, Out 2: False</div>`;
    }
    else if (type === 'while') { 
        outputs = 2; 
        if (!('condition' in nodeData)) nodeData.condition = '';
        html = `<div class="title-box"><i class="fa-solid fa-redo"></i> WHILE LOOP</div><input type="text" df-condition placeholder="e.g. A < 10" onmousedown="event.stopPropagation()"><div style="font-size: 10px; margin-top:5px;">Out 1: Body, Out 2: Exit</div>`;
    }
    return editorFlow.addNode(type, inputs, outputs, x, y, type, nodeData, html);
}

// Drag logic
function drag(ev) {
    ev.dataTransfer.setData("text/plain", ev.target.getAttribute('data-node'));
}
document.getElementById('drawflow').addEventListener('drop', (ev) => {
    ev.preventDefault();
    const type = ev.dataTransfer.getData("text/plain");
    
    const rect = editorFlow.precanvas.getBoundingClientRect();
    const pos_x = (ev.clientX - rect.left) / editorFlow.zoom;
    const pos_y = (ev.clientY - rect.top) / editorFlow.zoom;
    
    spawnNode(type, pos_x, pos_y);
});
document.getElementById('drawflow').addEventListener('dragover', (ev) => {
    ev.preventDefault();
});
document.getElementById('drawflow').addEventListener('dragenter', (ev) => {
    ev.preventDefault();
});

function toggleInspector() {
    const container = document.getElementById('inspector-container');
    const chevron = document.getElementById('inspector-chevron');
    if (container.style.display === 'none') {
        container.style.display = 'flex';
        chevron.style.transform = 'rotate(0deg)';
        document.getElementById('bottom-pane').style.flex = '1';
    } else {
        container.style.display = 'none';
        chevron.style.transform = 'rotate(180deg)';
        document.getElementById('bottom-pane').style.flex = '0 0 auto';
    }
}

// Toggle output panels when in flowchart mode
let flowchartPanelsVisible = false;
function toggleFlowchartPanels() {
    flowchartPanelsVisible = !flowchartPanelsVisible;
    if (flowchartPanelsVisible) {
        document.getElementById('output-panel').style.display = 'flex';
        document.getElementById('gutter-h').style.display = 'block';
        document.getElementById('bottom-pane').style.display = 'flex';
        document.getElementById('gutter-v').style.display = 'block';
        const pipe = document.getElementById('pipeline-container');
        if (pipe) pipe.style.display = 'block';
    } else {
        document.getElementById('output-panel').style.display = 'none';
        document.getElementById('gutter-h').style.display = 'none';
        document.getElementById('bottom-pane').style.display = 'none';
        document.getElementById('gutter-v').style.display = 'none';
        const pipe = document.getElementById('pipeline-container');
        if (pipe) pipe.style.display = 'none';
    }
}
