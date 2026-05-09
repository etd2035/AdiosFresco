import os
import json
from fractions import Fraction
from flask import Flask, render_template, jsonify, request, send_from_directory

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE_DIR, 'recipes.json'), 'r', encoding='utf-8') as f:
    RECIPES = json.load(f)

# Convert any imperial weight units to metric on load
_IMPERIAL_TO_G = {'oz': 28.35, 'lb': 453.59, 'lbs': 453.59, 'pound': 453.59, 'pounds': 453.59}
for _r in RECIPES:
    for _ing in _r['ingredientes']:
        _factor = _IMPERIAL_TO_G.get(_ing['unidad'].lower())
        if _factor:
            _ing['cantidad'] = round(_ing['cantidad'] * _factor)
            _ing['unidad'] = 'g'

PANTRY_FILE = os.path.join(BASE_DIR, 'pantry.json')


# ── Image extraction ──────────────────────────────────────────────────────────

def extract_images():
    """Extract the main dish photo from each recipe's PDF on first run."""
    os.makedirs('static/images', exist_ok=True)
    try:
        import fitz
    except ImportError:
        print("  [!] pymupdf not installed — skipping image extraction")
        return

    for recipe in RECIPES:
        out_path = f"static/images/{recipe['id']}.jpg"
        if os.path.exists(out_path):
            continue
        pdf_path = recipe.get('pdf_file', '')
        if not pdf_path or not os.path.exists(pdf_path):
            print(f"  [!] PDF not found for {recipe['id']}: {pdf_path}")
            continue
        try:
            doc = fitz.open(pdf_path)
            # Search ALL pages for the largest image (handles different PDF layouts)
            best_xref = None
            best_area = 0
            for page_num in range(len(doc)):
                for img in doc[page_num].get_images(full=True):
                    xref, _, w, h = img[0], img[1], img[2], img[3]
                    if w * h > best_area:
                        best_area = w * h
                        best_xref = xref
            if best_xref is None:
                print(f"  [!] No images found in {pdf_path}")
                continue
            img_data = doc.extract_image(best_xref)
            with open(out_path, 'wb') as f:
                f.write(img_data['image'])
            print(f"  [✓] Extracted image for {recipe['id']}")
        except Exception as e:
            print(f"  [!] Error extracting image for {recipe['id']}: {e}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_pantry():
    if os.path.exists(PANTRY_FILE):
        with open(PANTRY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_pantry(items):
    with open(PANTRY_FILE, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def parse_qty(val):
    try:
        if isinstance(val, (int, float)):
            return float(val)
        return float(Fraction(str(val)))
    except Exception:
        return 0.0


def format_qty(qty, unit):
    if qty <= 0:
        return f"0 {unit}"

    # Metric weight/volume units — always whole numbers
    if unit.lower() in ('g', 'kg', 'ml', 'l'):
        return f"{int(round(qty))} {unit}"

    # Snap fractional part to nearest common cooking fraction
    FRACS = [
        (0.125, '\u215b'),   # ⅛
        (0.25,  '\u00bc'),   # ¼
        (0.333, '\u2153'),   # ⅓
        (0.375, '\u215c'),   # ⅜
        (0.5,   '\u00bd'),   # ½
        (0.625, '\u215d'),   # ⅝
        (0.667, '\u2154'),   # ⅔
        (0.75,  '\u00be'),   # ¾
        (0.875, '\u215e'),   # ⅞
    ]

    whole = int(qty)
    frac = qty - whole

    best_sym, best_diff = None, float('inf')
    for val, sym in FRACS:
        diff = abs(frac - val)
        if diff < best_diff:
            best_diff, best_sym = diff, sym

    if best_diff < 0.06:
        if whole == 0:
            return f"{best_sym} {unit}"
        return f"{whole}{best_sym} {unit}"
    if frac < 0.06:
        return f"{int(round(qty))} {unit}"
    return f"{qty:.1f} {unit}"


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/recipes')
def get_recipes():
    return jsonify(RECIPES)


@app.route('/pdfs/<path:filename>')
def serve_pdf(filename):
    return send_from_directory('.', filename)


# Pantry CRUD
@app.route('/api/pantry', methods=['GET'])
def get_pantry():
    return jsonify(sorted(load_pantry(), key=str.lower))


@app.route('/api/pantry', methods=['POST'])
def add_pantry():
    item = request.json.get('item', '').strip()
    if not item:
        return jsonify({'error': 'Item vacío'}), 400
    items = load_pantry()
    if not any(i.lower() == item.lower() for i in items):
        items.append(item)
        save_pantry(items)
    return jsonify(sorted(items, key=str.lower))


@app.route('/api/pantry/<path:item>', methods=['DELETE'])
def delete_pantry(item):
    items = load_pantry()
    items = [i for i in items if i.lower() != item.lower()]
    save_pantry(items)
    return jsonify(sorted(items, key=str.lower))


# Shopping list — grouped by recipe, pantry items filtered out
@app.route('/api/shopping-list', methods=['POST'])
def shopping_list():
    data = request.json
    recipe_ids = data.get('recipe_ids', [])
    persons = int(data.get('persons', 2))
    scale = persons / 2

    pantry = {p.lower() for p in load_pantry()}
    selected = [r for r in RECIPES if r['id'] in recipe_ids]

    sections = []
    excluded_count = 0

    for recipe in selected:
        base = recipe.get('base_persons', 2)
        recipe_scale = persons / base
        items = []
        for ing in recipe['ingredientes']:
            if ing['nombre'].lower() in pantry:
                excluded_count += 1
                continue
            qty = parse_qty(ing['cantidad']) * recipe_scale
            items.append({
                'nombre': ing['nombre'],
                'cantidad': format_qty(qty, ing['unidad']),
                'refrigerar': ing.get('refrigerar', False)
            })
        sections.append({
            'recipe_id': recipe['id'],
            'recipe_nombre': recipe['nombre'],
            'recipe_emoji': recipe['emoji'],
            'items': items
        })

    return jsonify({
        'sections': sections,
        'persons': persons,
        'excluded_pantry_count': excluded_count
    })


# ── Start ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("")
    print("  Mis Recetas - Planificador Semanal")
    print("  ====================================")
    print("  Extrayendo fotos de los PDFs...")
    extract_images()
    print("  Servidor iniciado en: http://localhost:5000")
    print("  Presiona Ctrl+C para detener")
    print("")
    app.run(debug=False, port=5000)
