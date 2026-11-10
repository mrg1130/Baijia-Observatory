import ast
import math

METRICS = ['views', 'likes', 'comments', 'shares', 'favorites', 'live_views', 'unread']
FORMULA_FIELDS = set(METRICS + ['interactions'])


def parse_formula(expression):
    if not expression or len(expression) > 300:
        raise ValueError('请输入不超过 300 字符的公式')
    try:
        tree = ast.parse(expression, mode='eval')
    except SyntaxError:
        raise ValueError('公式格式有误') from None
    nodes = list(ast.walk(tree))
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Name, ast.Load, ast.Constant,
               ast.Add, ast.Sub, ast.Mult, ast.Div, ast.UAdd, ast.USub)
    if len(nodes) > 100 or any(not isinstance(n, allowed) for n in nodes):
        raise ValueError('公式只支持指标、数字、加减乘除和括号')
    for n in nodes:
        if isinstance(n, ast.Name) and n.id not in FORMULA_FIELDS:
            raise ValueError(f'不支持的指标：{n.id}')
        if isinstance(n, ast.Constant) and (type(n.value) not in (int, float) or not math.isfinite(n.value) or abs(n.value) > 1e12):
            raise ValueError('公式中的数字无效')
    return tree


def calculate(expression, values):
    tree = parse_formula(expression)

    def visit(n):
        if isinstance(n, ast.Expression):
            return visit(n.body)
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.Name):
            return values.get(n.id)
        if isinstance(n, ast.UnaryOp):
            v = visit(n.operand)
            return None if v is None else (-v if isinstance(n.op, ast.USub) else v)
        a, b = visit(n.left), visit(n.right)
        if a is None or b is None or (isinstance(n.op, ast.Div) and b == 0):
            return None
        if isinstance(n.op, ast.Add):
            return a + b
        if isinstance(n.op, ast.Sub):
            return a - b
        if isinstance(n.op, ast.Mult):
            return a * b
        return a / b
    try:
        v = visit(tree)
        return round(v, 6) if v is not None and math.isfinite(v) else None
    except (OverflowError, ZeroDivisionError):
        return None


def enrich(row):
    row = dict(row)
    parts = [row.get(k) for k in ('likes', 'comments', 'shares', 'favorites')]
    row['interactions'] = sum(parts) if all(v is not None for v in parts) else None
    row['engagement'] = calculate('interactions / views * 100', row)
    return row


def summarize(rows, calculators=()):
    totals, coverage = {}, {}
    for key in METRICS + ['interactions']:
        available = [r[key] for r in rows if r.get(key) is not None]
        totals[key] = sum(available) if available else None
        coverage[key] = len(available)
    # Rate uses the exact same population in numerator and denominator.
    paired = [r for r in rows if r.get('interactions') is not None and r.get('views') is not None]
    totals['engagement'] = calculate('interactions / views * 100', {
        'interactions': sum(r['interactions'] for r in paired), 'views': sum(r['views'] for r in paired)})
    coverage['engagement'] = len(paired)
    custom = []
    for calc in calculators:
        if calc['aggregation'] == 'totals':
            fields = {n.id for n in ast.walk(parse_formula(calc['expression'])) if isinstance(n, ast.Name)}
            eligible = [r for r in rows if all(r.get(k) is not None for k in fields)]
            values = {k: sum(r[k] for r in eligible) if eligible else None for k in fields}
            value = calculate(calc['expression'], values) if eligible else None
            count = len(eligible)
        else:
            vals = [calculate(calc['expression'], r) for r in rows]
            vals = [v for v in vals if v is not None]
            count = len(vals)
            value = None if not vals else {'sum': sum, 'average': lambda x: sum(x) / len(x), 'max': max, 'min': min}[calc['aggregation']](vals)
        custom.append({**dict(calc), 'value': value, 'coverage': count})
    return {'count': len(rows), 'totals': totals, 'coverage': coverage, 'custom': custom}
