import requests

def test_upload_api():
    sample_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 480">
    <rect x="120" y="25" width="120" height="40" rx="20" fill="#22c55e"/>
    <text x="180" y="50">START</text>
    <polygon points="110,145 250,145 230,110 90,110" fill="#3b82f6"/>
    <text x="170" y="132">INPUT A</text>
    <polygon points="230,335 330,335 315,300 215,300" fill="#3b82f6"/>
    <text x="272" y="322">PRINT A</text>
    <rect x="120" y="420" width="120" height="40" rx="20" fill="#ef4444"/>
    <text x="180" y="445">END</text>
    </svg>"""

    res = requests.post('http://127.0.0.1:5000/upload_flowchart', json={
        'image': sample_svg,
        'filename': 'test.svg',
        'engine': 'shape-ocr',
        'target': 'pseudocode'
    })

    assert res.status_code == 200
    data = res.json()
    assert 'START' in data['generated_pseudo']
    assert data['python_code'] != ''
    print("\n[OK] Upload Flowchart endpoint response:\n", data['generated_pseudo'])

def test_upload_factorial():
    factorial_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 480" width="100%" height="100%">
        <rect width="360" height="480" fill="#0b0f19" rx="10"/>
        <rect x="120" y="20" width="120" height="36" rx="18" fill="#22c55e"/>
        <text x="180" y="44" fill="#000" font-family="sans-serif" font-weight="bold" font-size="13" text-anchor="middle">START</text>
        <polygon points="110,120 250,120 230,90 90,90" fill="#3b82f6"/>
        <text x="170" y="108" fill="#fff" font-family="sans-serif" font-weight="bold" font-size="12" text-anchor="middle">INPUT N</text>
        <rect x="100" y="155" width="140" height="35" rx="5" fill="#a855f7"/>
        <text x="170" y="177" fill="#fff" font-family="sans-serif" font-weight="bold" font-size="12" text-anchor="middle">FACT = 1, I = 1</text>
        <polygon points="170,230 235,265 170,300 105,265" fill="#f59e0b"/>
        <text x="170" y="270" fill="#000" font-family="sans-serif" font-weight="bold" font-size="12" text-anchor="middle">I &lt;= N ?</text>
        <rect x="95" y="325" width="150" height="35" rx="5" fill="#a855f7"/>
        <text x="170" y="347" fill="#fff" font-family="sans-serif" font-weight="bold" font-size="11" text-anchor="middle">FACT = FACT*I, I = I+1</text>
        <polygon points="100,420 240,420 220,390 80,390" fill="#3b82f6"/>
        <text x="160" y="408" fill="#fff" font-family="sans-serif" font-weight="bold" font-size="12" text-anchor="middle">PRINT FACT</text>
        <rect x="110" y="445" width="100" height="30" rx="15" fill="#ef4444"/>
        <text x="160" y="465" fill="#fff" font-family="sans-serif" font-weight="bold" font-size="12" text-anchor="middle">END</text>
    </svg>"""

    res = requests.post('http://127.0.0.1:5000/upload_flowchart', json={
        'image': factorial_svg,
        'filename': 'factorial_calculator.svg',
        'engine': 'shape-ocr',
        'target': 'pseudocode'
    })

    assert res.status_code == 200
    data = res.json()
    assert data['success'] is True
    assert 'WHILE' in data['generated_pseudo']
    assert 'while' in data['python_code']

