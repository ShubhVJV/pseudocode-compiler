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
function updateLineNumbers(el, lineNumbersEl) {
    if (!el || !lineNumbersEl) return;
    const text = (el.value !== undefined) ? el.value : (el.innerText || '');
    const linesCount = text ? text.split('\n').length : 1;
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
        dGen.innerText = `${data.python_code ? data.python_code.split('\n').length : 0} lines`;
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
    
    const uploadPanel = document.getElementById('flowchart-upload-panel');
    const flowchartPanel = document.getElementById('flowchart-panel');
    const editorPanel = document.getElementById('editor-panel');
    const outputPanel = document.getElementById('output-panel');
    const gutterV = document.getElementById('gutter-v');
    const gutterH = document.getElementById('gutter-h');
    const insp = document.getElementById('bottom-pane');
    const pipe = document.getElementById('pipeline-container');
    const topPane = document.querySelector('.top-pane');

    if (mode === 'flowchart') {
        flowchartPanelsVisible = false;
        editorPanel.style.display = 'none';
        outputPanel.style.display = 'none';
        if (uploadPanel) uploadPanel.style.display = 'none';
        gutterV.style.display = 'none';
        gutterH.style.display = 'none';
        if (insp) insp.style.display = 'none';
        if (pipe) pipe.style.display = 'none';
        
        flowchartPanel.style.display = 'flex';
        topPane.style.flex = '1';
        topPane.style.minHeight = '100%';
        
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
    } else if (mode === 'flowchart-upload') {
        flowchartPanelsVisible = false;
        editorPanel.style.display = 'none';
        outputPanel.style.display = 'none';
        flowchartPanel.style.display = 'none';
        gutterV.style.display = 'none';
        gutterH.style.display = 'none';
        if (insp) insp.style.display = 'none';
        if (pipe) pipe.style.display = 'none';
        
        if (uploadPanel) uploadPanel.style.display = 'flex';
        topPane.style.flex = '1';
        topPane.style.minHeight = '100%';
    } else {
        if (uploadPanel) uploadPanel.style.display = 'none';
        flowchartPanel.style.display = 'none';
        editorPanel.style.display = 'flex';
        outputPanel.style.display = 'flex';
        gutterV.style.display = 'block';
        gutterH.style.display = 'block';
        
        if (insp) insp.style.display = 'flex';
        if (pipe) pipe.style.display = 'block';
        
        topPane.style.flex = '2';
        topPane.style.minHeight = '250px';
        
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

// --- Flowchart Upload Logic ---
const flowchartFileInput = document.getElementById('flowchart-file-input');
const uploadDropzone = document.getElementById('upload-dropzone');
const dropzonePrompt = document.getElementById('dropzone-prompt');
const uploadPreviewArea = document.getElementById('upload-preview-area');
const previewImage = document.getElementById('preview-image');
const previewFilename = document.getElementById('preview-filename');
const previewFilesize = document.getElementById('preview-filesize');
const btnRemovePreview = document.getElementById('btn-remove-preview');
const btnProcessUpload = document.getElementById('btn-process-upload');
const uploadStatusBox = document.getElementById('upload-status-box');

let activeFlowchartFile = null;

function displayUploadedImage(src, name, sizeFormatted) {
    if (previewImage) previewImage.src = src;
    if (previewFilename) previewFilename.innerText = name;
    if (previewFilesize) previewFilesize.innerText = sizeFormatted;
    if (dropzonePrompt) dropzonePrompt.style.display = 'none';
    if (uploadPreviewArea) uploadPreviewArea.style.display = 'flex';
    if (uploadStatusBox) {
        uploadStatusBox.style.display = 'none';
        uploadStatusBox.className = 'info-box';
    }
}

function resetUploadPreview() {
    activeFlowchartFile = null;
    if (flowchartFileInput) flowchartFileInput.value = '';
    if (previewImage) previewImage.src = '';
    if (dropzonePrompt) dropzonePrompt.style.display = 'flex';
    if (uploadPreviewArea) uploadPreviewArea.style.display = 'none';
    if (uploadStatusBox) uploadStatusBox.style.display = 'none';
}

if (flowchartFileInput) {
    flowchartFileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (!file) return;
        activeFlowchartFile = file;
        const reader = new FileReader();
        reader.onload = (evt) => {
            const sizeStr = (file.size / 1024).toFixed(1) + ' KB';
            displayUploadedImage(evt.target.result, file.name, sizeStr);
        };
        reader.readAsDataURL(file);
    });
}

if (uploadDropzone) {
    ['dragenter', 'dragover'].forEach(eventName => {
        uploadDropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            uploadDropzone.classList.add('dragover');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        uploadDropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            uploadDropzone.classList.remove('dragover');
        }, false);
    });

    uploadDropzone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files && files.length > 0) {
            const file = files[0];
            activeFlowchartFile = file;
            const reader = new FileReader();
            reader.onload = (evt) => {
                const sizeStr = (file.size / 1024).toFixed(1) + ' KB';
                displayUploadedImage(evt.target.result, file.name, sizeStr);
            };
            reader.readAsDataURL(file);
        }
    });
}

if (btnRemovePreview) {
    btnRemovePreview.addEventListener('click', (e) => {
        e.stopPropagation();
        resetUploadPreview();
    });
}

if (btnProcessUpload) {
    btnProcessUpload.addEventListener('click', async () => {
        if (!uploadStatusBox) return;
        if (!previewImage || !previewImage.src || previewImage.src === '') {
            uploadStatusBox.className = 'info-box warning';
            uploadStatusBox.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Please upload a flowchart image or select a sample diagram first.';
            uploadStatusBox.style.display = 'block';
            return;
        }

        const engine = document.getElementById('vision-model-select') ? document.getElementById('vision-model-select').value : 'shape-ocr';
        const target = document.getElementById('output-target-select') ? document.getElementById('output-target-select').value : 'pseudocode';
        const origBtnText = btnProcessUpload.innerHTML;

        btnProcessUpload.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Extracting & Transpiling...';
        btnProcessUpload.disabled = true;
        uploadStatusBox.className = 'info-box';
        uploadStatusBox.innerHTML = '<i class="fa-solid fa-microscope"></i> Analyzing diagram geometry and extracting pseudocode...';
        uploadStatusBox.style.display = 'block';

        try {
            const res = await fetch('/upload_flowchart', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    image: previewImage.src,
                    filename: previewFilename ? previewFilename.innerText : '',
                    engine: engine,
                    target: target
                })
            });

            const data = await res.json();

            if (data.generated_pseudo) {
                // Populate main editor
                editor.value = data.generated_pseudo;
                updateLineNumbers(editor, editorLines);

                // Populate Python output
                const pythonOutput = document.getElementById('python-output');
                const pythonLines = document.getElementById('python-lines');
                if (pythonOutput) pythonOutput.innerText = data.python_code || 'No code generated';
                if (pythonLines && pythonOutput) updateLineNumbers({value: pythonOutput.innerText}, pythonLines);

                // Update pipeline visualizer & diagnostics
                updatePipeline(data);

                // Populate Tokens
                const tokenTbody = document.querySelector('#token-table tbody');
                if (tokenTbody && data.tokens) {
                    tokenTbody.innerHTML = '';
                    data.tokens.forEach(t => {
                        tokenTbody.innerHTML += `<tr><td><span class="badge" style="background:var(--border-color)">${t.type}</span></td><td>${t.value}</td><td>${t.line}</td><td>${t.col}</td></tr>`;
                    });
                }

                // Populate Symbol Table
                const symbolTbody = document.querySelector('#symbol-table tbody');
                if (symbolTbody && data.symbol_table) {
                    symbolTbody.innerHTML = '';
                    data.symbol_table.forEach(s => {
                        symbolTbody.innerHTML += `<tr>
                            <td><strong>${s.name}</strong></td>
                            <td style="color:var(--accent-green)">${s.type}</td>
                            <td>${s.scope}</td>
                            <td><span class="badge" style="background:var(--border-color)">${s.kind}</span></td>
                        </tr>`;
                    });
                }

                // Populate AST & CFG
                const astContainer = document.getElementById('ast-tree-container');
                if (astContainer) {
                    astContainer.innerHTML = data.ast_tree ? `<div class="ast-node">${renderAST(data.ast_tree)}</div>` : 'No AST generated.';
                }

                // Enable execution button
                const btnExecute = document.getElementById('btn-execute');
                if (btnExecute && data.python_code) {
                    btnExecute.disabled = false;
                }

                const modeToOpen = target === 'tamil' ? 'tamil' : 'pseudocode';
                uploadStatusBox.className = 'info-box success';
                uploadStatusBox.innerHTML = `
                    <div style="display: flex; flex-direction: column; gap: 8px;">
                        <div><i class="fa-solid fa-circle-check" style="color: var(--accent-green)"></i> <strong>Extraction Complete!</strong> Flowchart parsed into <code>${target}</code>.</div>
                        <div style="background: rgba(0,0,0,0.3); padding: 8px; border-radius: 4px; font-family: monospace; font-size: 0.82rem; max-height: 100px; overflow-y: auto;">
                            ${data.generated_pseudo.replace(/\n/g, '<br>')}
                        </div>
                        <div style="display: flex; gap: 10px; margin-top: 5px;">
                            <button type="button" class="btn secondary-btn btn-sm" onclick="switchMode('${modeToOpen}', document.querySelector('.nav-links li[data-mode=${modeToOpen}]'))">
                                <i class="fa-solid fa-laptop-code"></i> Open Code & Output View
                            </button>
                            <button type="button" class="btn primary-btn btn-sm" onclick="document.getElementById('btn-execute').click()">
                                <i class="fa-solid fa-play"></i> Execute Now
                            </button>
                        </div>
                    </div>
                `;
            } else if (data.error) {
                uploadStatusBox.className = 'info-box error';
                uploadStatusBox.innerHTML = `<i class="fa-solid fa-circle-xmark"></i> <strong>Backend Error:</strong> ${data.error}`;
            } else {
                uploadStatusBox.className = 'info-box warning';
                uploadStatusBox.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Could not extract valid statements from flowchart. Try a different image or engine.';
            }
        } catch (err) {
            uploadStatusBox.className = 'info-box error';
            uploadStatusBox.innerHTML = `<i class="fa-solid fa-circle-xmark"></i> Failed to process flowchart: ${err.message}`;
        } finally {
            btnProcessUpload.innerHTML = origBtnText;
            btnProcessUpload.disabled = false;
        }
    });
}

// Sample Flowcharts (SVG generation)
function loadSampleFlowchart(sampleKey) {
    let svgContent = '';
    let fileName = '';

    if (sampleKey === 'max_two') {
        fileName = 'max_of_two_numbers.svg';
        svgContent = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 480" width="100%" height="100%">
            <defs>
                <marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                    <path d="M 0 1 L 10 5 L 0 9 z" fill="#00ff00" />
                </marker>
            </defs>
            <rect width="360" height="480" fill="#0b0f19" rx="10"/>
            <!-- Start -->
            <rect x="120" y="25" width="120" height="40" rx="20" fill="#22c55e"/>
            <text x="180" y="50" fill="#000" font-family="sans-serif" font-weight="bold" font-size="14" text-anchor="middle">START</text>
            <line x1="180" y1="65" x2="180" y2="105" stroke="#00ff00" stroke-width="2" marker-end="url(#arrow)"/>
            <!-- Input -->
            <polygon points="110,145 250,145 230,110 90,110" fill="#3b82f6"/>
            <text x="170" y="132" fill="#fff" font-family="sans-serif" font-weight="bold" font-size="13" text-anchor="middle">INPUT A, B</text>
            <line x1="170" y1="145" x2="170" y2="185" stroke="#00ff00" stroke-width="2" marker-end="url(#arrow)"/>
            <!-- Decision -->
            <polygon points="170,190 240,230 170,270 100,230" fill="#f59e0b"/>
            <text x="170" y="235" fill="#000" font-family="sans-serif" font-weight="bold" font-size="13" text-anchor="middle">A &gt; B ?</text>
            <!-- Branch True -->
            <line x1="240" y1="230" x2="280" y2="230" stroke="#00ff00" stroke-width="2"/>
            <line x1="280" y1="230" x2="280" y2="295" stroke="#00ff00" stroke-width="2" marker-end="url(#arrow)"/>
            <text x="255" y="222" fill="#00ff00" font-size="11" font-family="sans-serif">True</text>
            <polygon points="230,335 330,335 315,300 215,300" fill="#3b82f6"/>
            <text x="272" y="322" fill="#fff" font-family="sans-serif" font-weight="bold" font-size="12" text-anchor="middle">PRINT A</text>
            <!-- Branch False -->
            <line x1="100" y1="230" x2="60" y2="230" stroke="#00ff00" stroke-width="2"/>
            <line x1="60" y1="230" x2="60" y2="295" stroke="#00ff00" stroke-width="2" marker-end="url(#arrow)"/>
            <text x="65" y="222" fill="#ff4444" font-size="11" font-family="sans-serif">False</text>
            <polygon points="20,335 120,335 105,300 5,300" fill="#3b82f6"/>
            <text x="62" y="322" fill="#fff" font-family="sans-serif" font-weight="bold" font-size="12" text-anchor="middle">PRINT B</text>
            <!-- Merge to End -->
            <line x1="272" y1="335" x2="272" y2="390" stroke="#00ff00" stroke-width="2"/>
            <line x1="62" y1="335" x2="62" y2="390" stroke="#00ff00" stroke-width="2"/>
            <line x1="62" y1="390" x2="180" y2="390" stroke="#00ff00" stroke-width="2"/>
            <line x1="272" y1="390" x2="180" y2="390" stroke="#00ff00" stroke-width="2"/>
            <line x1="180" y1="390" x2="180" y2="415" stroke="#00ff00" stroke-width="2" marker-end="url(#arrow)"/>
            <!-- End -->
            <rect x="120" y="420" width="120" height="40" rx="20" fill="#ef4444"/>
            <text x="180" y="445" fill="#fff" font-family="sans-serif" font-weight="bold" font-size="14" text-anchor="middle">END</text>
        </svg>`;
    } else if (sampleKey === 'factorial') {
        fileName = 'factorial_calculator.svg';
        svgContent = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 480" width="100%" height="100%">
            <defs>
                <marker id="arrow2" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                    <path d="M 0 1 L 10 5 L 0 9 z" fill="#00ff00" />
                </marker>
            </defs>
            <rect width="360" height="480" fill="#0b0f19" rx="10"/>
            <rect x="120" y="20" width="120" height="36" rx="18" fill="#22c55e"/>
            <text x="180" y="44" fill="#000" font-family="sans-serif" font-weight="bold" font-size="13" text-anchor="middle">START</text>
            <line x1="180" y1="56" x2="180" y2="85" stroke="#00ff00" stroke-width="2" marker-end="url(#arrow2)"/>
            <polygon points="110,120 250,120 230,90 90,90" fill="#3b82f6"/>
            <text x="170" y="108" fill="#fff" font-family="sans-serif" font-weight="bold" font-size="12" text-anchor="middle">INPUT N</text>
            <line x1="170" y1="120" x2="170" y2="150" stroke="#00ff00" stroke-width="2" marker-end="url(#arrow2)"/>
            <rect x="100" y="155" width="140" height="35" rx="5" fill="#a855f7"/>
            <text x="170" y="177" fill="#fff" font-family="sans-serif" font-weight="bold" font-size="12" text-anchor="middle">FACT = 1, I = 1</text>
            <line x1="170" y1="190" x2="170" y2="225" stroke="#00ff00" stroke-width="2" marker-end="url(#arrow2)"/>
            <polygon points="170,230 235,265 170,300 105,265" fill="#f59e0b"/>
            <text x="170" y="270" fill="#000" font-family="sans-serif" font-weight="bold" font-size="12" text-anchor="middle">I &lt;= N ?</text>
            <!-- Loop -->
            <line x1="235" y1="265" x2="290" y2="265" stroke="#00ff00" stroke-width="2"/>
            <line x1="290" y1="265" x2="290" y2="340" stroke="#00ff00" stroke-width="2"/>
            <line x1="290" y1="340" x2="245" y2="340" stroke="#00ff00" stroke-width="2" marker-end="url(#arrow2)"/>
            <rect x="95" y="325" width="150" height="35" rx="5" fill="#a855f7"/>
            <text x="170" y="347" fill="#fff" font-family="sans-serif" font-weight="bold" font-size="11" text-anchor="middle">FACT = FACT*I, I = I+1</text>
            <line x1="95" y1="342" x2="50" y2="342" stroke="#00ff00" stroke-width="2"/>
            <line x1="50" y1="342" x2="50" y2="210" stroke="#00ff00" stroke-width="2"/>
            <line x1="50" y1="210" x2="170" y2="210" stroke="#00ff00" stroke-width="2"/>
            <line x1="170" y1="210" x2="170" y2="225" stroke="#00ff00" stroke-width="2" marker-end="url(#arrow2)"/>
            <!-- Exit Loop -->
            <line x1="170" y1="300" x2="170" y2="385" stroke="#00ff00" stroke-width="2" marker-end="url(#arrow2)"/>
            <polygon points="100,420 240,420 220,390 80,390" fill="#3b82f6"/>
            <text x="160" y="408" fill="#fff" font-family="sans-serif" font-weight="bold" font-size="12" text-anchor="middle">PRINT FACT</text>
            <line x1="160" y1="420" x2="160" y2="445" stroke="#00ff00" stroke-width="2" marker-end="url(#arrow2)"/>
            <rect x="110" y="445" width="100" height="30" rx="15" fill="#ef4444"/>
            <text x="160" y="465" fill="#fff" font-family="sans-serif" font-weight="bold" font-size="12" text-anchor="middle">END</text>
        </svg>`;
    } else {
        fileName = 'odd_even_checker.svg';
        svgContent = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 440" width="100%" height="100%">
            <defs>
                <marker id="arrow3" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                    <path d="M 0 1 L 10 5 L 0 9 z" fill="#00ff00" />
                </marker>
            </defs>
            <rect width="360" height="440" fill="#0b0f19" rx="10"/>
            <rect x="120" y="20" width="120" height="36" rx="18" fill="#22c55e"/>
            <text x="180" y="44" fill="#000" font-family="sans-serif" font-weight="bold" font-size="13" text-anchor="middle">START</text>
            <line x1="180" y1="56" x2="180" y2="90" stroke="#00ff00" stroke-width="2" marker-end="url(#arrow3)"/>
            <polygon points="110,125 250,125 230,95 90,95" fill="#3b82f6"/>
            <text x="170" y="113" fill="#fff" font-family="sans-serif" font-weight="bold" font-size="12" text-anchor="middle">INPUT NUM</text>
            <line x1="170" y1="125" x2="170" y2="165" stroke="#00ff00" stroke-width="2" marker-end="url(#arrow3)"/>
            <polygon points="170,170 240,210 170,250 100,210" fill="#f59e0b"/>
            <text x="170" y="215" fill="#000" font-family="sans-serif" font-weight="bold" font-size="12" text-anchor="middle">NUM % 2 == 0?</text>
            <line x1="240" y1="210" x2="280" y2="210" stroke="#00ff00" stroke-width="2"/>
            <line x1="280" y1="210" x2="280" y2="275" stroke="#00ff00" stroke-width="2" marker-end="url(#arrow3)"/>
            <polygon points="220,315 330,315 315,280 205,280" fill="#3b82f6"/>
            <text x="268" y="302" fill="#fff" font-family="sans-serif" font-weight="bold" font-size="12" text-anchor="middle">PRINT "Even"</text>
            <line x1="100" y1="210" x2="60" y2="210" stroke="#00ff00" stroke-width="2"/>
            <line x1="60" y1="210" x2="60" y2="275" stroke="#00ff00" stroke-width="2" marker-end="url(#arrow3)"/>
            <polygon points="15,315 125,315 110,280 0,280" fill="#3b82f6"/>
            <text x="63" y="302" fill="#fff" font-family="sans-serif" font-weight="bold" font-size="12" text-anchor="middle">PRINT "Odd"</text>
            <line x1="268" y1="315" x2="268" y2="365" stroke="#00ff00" stroke-width="2"/>
            <line x1="63" y1="315" x2="63" y2="365" stroke="#00ff00" stroke-width="2"/>
            <line x1="63" y1="365" x2="170" y2="365" stroke="#00ff00" stroke-width="2"/>
            <line x1="268" y1="365" x2="170" y2="365" stroke="#00ff00" stroke-width="2"/>
            <line x1="170" y1="365" x2="170" y2="390" stroke="#00ff00" stroke-width="2" marker-end="url(#arrow3)"/>
            <rect x="110" y="390" width="120" height="36" rx="18" fill="#ef4444"/>
            <text x="170" y="414" fill="#fff" font-family="sans-serif" font-weight="bold" font-size="13" text-anchor="middle">END</text>
        </svg>`;
    }

    const encodedSvg = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgContent);
    activeFlowchartFile = { name: fileName, size: 2840 };
    displayUploadedImage(encodedSvg, fileName, '2.8 KB (Sample)');
}
