import pytest
from transpiler.flowchart_parser import parse_flowchart_payload

def test_svg_flowchart_extraction():
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

    res = parse_flowchart_payload(sample_svg, target='pseudocode')
    assert "START" in res['generated_pseudo']
    assert "PRINT" in res['generated_pseudo']
    assert res['python_code'] != ""

def test_tamil_target():
    sample_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 480">
    <rect x="120" y="25" width="120" height="40" rx="20" fill="#22c55e"/>
    <text x="180" y="50">START</text>
    <polygon points="230,335 330,335 315,300 215,300" fill="#3b82f6"/>
    <text x="272" y="322">PRINT 42</text>
    <rect x="120" y="420" width="120" height="40" rx="20" fill="#ef4444"/>
    <text x="180" y="445">END</text>
    </svg>"""

    res = parse_flowchart_payload(sample_svg, target='tamil')
    assert "THODANGU" in res['generated_pseudo']
    assert "KANBI" in res['generated_pseudo']
    assert "MUDI" in res['generated_pseudo']

def test_factorial_svg():
    sample_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 480" width="100%" height="100%">
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
        <line x1="235" y1="265" x2="290" y2="265" stroke="#00ff00" stroke-width="2"/>
        <line x1="290" y1="265" x2="290" y2="340" stroke="#00ff00" stroke-width="2"/>
        <line x1="290" y1="340" x2="245" y2="340" stroke="#00ff00" stroke-width="2" marker-end="url(#arrow2)"/>
        <rect x="95" y="325" width="150" height="35" rx="5" fill="#a855f7"/>
        <text x="170" y="347" fill="#fff" font-family="sans-serif" font-weight="bold" font-size="11" text-anchor="middle">FACT = FACT*I, I = I+1</text>
        <line x1="95" y1="342" x2="50" y2="342" stroke="#00ff00" stroke-width="2"/>
        <line x1="50" y1="342" x2="50" y2="210" stroke="#00ff00" stroke-width="2"/>
        <line x1="50" y1="210" x2="170" y2="210" stroke="#00ff00" stroke-width="2"/>
        <line x1="170" y1="210" x2="170" y2="225" stroke="#00ff00" stroke-width="2" marker-end="url(#arrow2)"/>
        <line x1="170" y1="300" x2="170" y2="385" stroke="#00ff00" stroke-width="2" marker-end="url(#arrow2)"/>
        <polygon points="100,420 240,420 220,390 80,390" fill="#3b82f6"/>
        <text x="160" y="408" fill="#fff" font-family="sans-serif" font-weight="bold" font-size="12" text-anchor="middle">PRINT FACT</text>
        <line x1="160" y1="420" x2="160" y2="445" stroke="#00ff00" stroke-width="2" marker-end="url(#arrow2)"/>
        <rect x="110" y="445" width="100" height="30" rx="15" fill="#ef4444"/>
        <text x="160" y="465" fill="#fff" font-family="sans-serif" font-weight="bold" font-size="12" text-anchor="middle">END</text>
    </svg>"""
    res = parse_flowchart_payload(sample_svg, target='pseudocode')
    assert "START" in res['generated_pseudo']
    assert res['generated_pseudo'] is not None
