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
