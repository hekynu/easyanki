from flask import Flask, render_template, request, redirect, url_for, Response
import sqlite3
import os
import re
import shutil
import zipfile
import io
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'ankiapp_fixed_final_v10'

UPLOAD_FOLDER = os.path.join('static', 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def get_db():
    db_path = os.path.join(os.path.dirname(__file__), 'flashcards.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row 
    return conn

@app.route('/')
def dashboard():
    db = get_db()
    all_cards = db.execute('SELECT strength, reviews FROM cards').fetchall()
    total_cards = len(all_cards)
    all_time_reviews = db.execute('SELECT SUM(reviews) FROM cards').fetchone()[0] or 0
    today_start = datetime.now().strftime('%Y-%m-%d') + " 00:00:00"
    daily_count = db.execute('SELECT COUNT(*) FROM cards WHERE reviews > 0 AND last_review >= ?', (today_start,)).fetchone()[0] or 0

    bins = {"0-20%": 0, "20-40%": 0, "40-60%": 0, "60-80%": 0, "80-100%": 0}
    total_strength = 0
    for c in all_cards:
        s = float(c['strength'] or 0.0)
        total_strength += s
        if s < 0.2: bins["0-20%"] += 1
        elif s < 0.4: bins["20-40%"] += 1
        elif s < 0.6: bins["40-60%"] += 1
        elif s < 0.8: bins["60-80%"] += 1
        else: bins["80-100%"] += 1

    mastery_avg = round((total_strength / total_cards) * 100) if total_cards > 0 else 0
    return render_template('dashboard.html', total=total_cards, mastery_percent=mastery_avg, bins=bins, daily_count=daily_count, all_time_reviews=all_time_reviews)

@app.route('/study')
def study():
    db = get_db()
    all_cards = db.execute('SELECT * FROM cards ORDER BY strength ASC LIMIT 100').fetchall()
    if not all_cards: return redirect(url_for('add_card'))
    import random
    target = random.choice(all_cards)
    return render_template('study.html', card=target)

@app.route('/exit')
def exit_study():
    return redirect(url_for('dashboard'))

@app.route('/review/<int:card_id>', methods=['POST'])
def review(card_id):
    choice = request.form.get('choice')
    db = get_db()
    card = db.execute('SELECT strength, level FROM cards WHERE id = ?', (card_id,)).fetchone()
    cur_s, level = float(card['strength'] or 0.0), card['level'] or 0
    if choice == 'forgot': cur_s, level = 0.0, max(0, level - 1)
    elif choice == 'ng': cur_s = max(0.0, cur_s - 0.2)
    elif choice == 'good': level += 1; cur_s += 0.2
    elif choice == 'best': level += 2; cur_s += 0.4
    new_s = min(max(0.0, cur_s), min(1.0, (level + 1) * 0.34))
    db.execute('UPDATE cards SET strength=?, level=?, reviews=reviews+1, weight=?, last_review=? WHERE id=?',
               (new_s, level, int((1-new_s)*100), datetime.now().strftime('%Y-%m-%d %H:%M:%S'), card_id))
    db.commit()
    return redirect(url_for('study'))

@app.route('/add', methods=['GET', 'POST'])
def add_card():
    if request.method == 'POST':
        front, back = request.form.get('front'), request.form.get('back')
        file = request.files.get('image')
        img_html = ""
        if file and file.filename != '':
            filename = f"{uuid.uuid4().hex}.png"
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            img_html = f'<br><img src="/static/uploads/{filename}" style="max-width:100%;">'
        if front and back:
            db = get_db()
            db.execute('INSERT INTO cards (front, back, strength, level, weight, last_review, reviews) VALUES (?, ?, 0.0, 0, 100, ?, 0)',
                       (front, back + img_html, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            db.commit()
            return redirect(url_for('dashboard'))
    return render_template('add.html')

@app.route('/search')
def search():
    query = request.args.get('q', '')
    db = get_db()
    res = db.execute('SELECT * FROM cards WHERE front LIKE ? OR back LIKE ? LIMIT 200', ('%'+query+'%', '%'+query+'%')).fetchall()
    return render_template('search.html', results=res, query=query)

@app.route('/edit/<int:card_id>', methods=['GET', 'POST'])
def edit_card(card_id):
    db = get_db()
    if request.method == 'POST':
        front, back = request.form.get('front'), request.form.get('back')
        file = request.files.get('image')
        if file and file.filename != '':
            filename = f"{uuid.uuid4().hex}.png"
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            back += f'<br><img src="/static/uploads/{filename}" style="max-width:100%;">'
        db.execute('UPDATE cards SET front = ?, back = ? WHERE id = ?', (front, back, card_id))
        db.commit()
        return redirect(url_for('search', q=front))
    card = db.execute('SELECT * FROM cards WHERE id = ?', (card_id,)).fetchone()
    return render_template('edit.html', card=card)

@app.route('/delete/<int:card_id>', methods=['POST'])
def delete_card(card_id):
    db = get_db()
    db.execute('DELETE FROM cards WHERE id = ?', (card_id,))
    db.commit()
    return redirect(url_for('search'))

@app.route('/import')
def import_page():
    return render_template('import.html')

@app.route('/run_import', methods=['POST'])
def run_import():
    file = request.files.get('file')
    if not file: return "No file."
    db = get_db()
    card_pattern = re.compile(r'<card>(.*?)</card>', re.DOTALL)
    field_pattern = re.compile(r"<rich-text\s+name=['\"](.*?)['\"]>(.*?)</rich-text>", re.DOTALL)
    blob_pattern = re.compile(r'\{\{blob\s+([a-f0-9]+)\}\}')
    html_cleaner = re.compile(r'<(?!img|/img|br).*?>')
    try:
        with zipfile.ZipFile(io.BytesIO(file.read()), 'r') as z:
            xml_path = next((n for n in z.namelist() if n.endswith('.xml')), None)
            xml_content = z.read(xml_path).decode('utf-8', errors='ignore')
            cards = card_pattern.findall(xml_content)
            db.execute('BEGIN')
            for card_block in cards:
                field_map = {name: content for name, content in field_pattern.findall(card_block)}
                f_raw, b_raw = field_map.get('Front', ''), field_map.get('Back', '')
                for text_field in [f_raw, b_raw]:
                    for b_id in blob_pattern.findall(text_field):
                        b_path = next((n for n in z.namelist() if b_id in n), None)
                        if b_path:
                            d_path = os.path.join(UPLOAD_FOLDER, f"{b_id}.png")
                            if not os.path.exists(d_path):
                                with z.open(b_path) as src, open(d_path, 'wb') as dst: shutil.copyfileobj(src, dst)
                front = blob_pattern.sub(r'<img src="/static/uploads/\1.png" style="max-width:100%;">', f_raw)
                back = blob_pattern.sub(r'<img src="/static/uploads/\1.png" style="max-width:100%;">', b_raw)
                front, back = html_cleaner.sub('', front).strip(), html_cleaner.sub('', back).strip()
                if front or back:
                    db.execute('INSERT INTO cards (front, back, strength, level, weight, last_review, reviews) VALUES (?, ?, 0.0, 0, 100, ?, 0)', 
                               (front, back, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            db.commit()
        return redirect(url_for('dashboard'))
    except Exception as e:
        db.rollback(); return f"Error: {e}"

@app.route('/export_zip')
def export_zip():
    db = get_db()
    cards = db.execute('SELECT * FROM cards').fetchall()
    root = ET.Element("deck")
    cards_node = ET.SubElement(root, "cards")
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for card in cards:
            card_node = ET.SubElement(cards_node, "card")
            for field_name, content in [("Front", card['front']), ("Back", card['back'])]:
                clean_content = content
                found_blobs = re.findall(r'src="/static/uploads/(.*?)\.png"', content)
                for b_id in found_blobs:
                    clean_content = re.sub(fr'<img.*src="/static/uploads/{b_id}\.png".*?>', f'{{{{blob {b_id}}}}}', clean_content)
                    img_path = os.path.join(UPLOAD_FOLDER, f"{b_id}.png")
                    if os.path.exists(img_path): zf.write(img_path, f"{b_id}")
                field_node = ET.SubElement(card_node, "rich-text")
                field_node.set("name", field_name)
                field_node.text = clean_content
        zf.writestr("deck.xml", ET.tostring(root, encoding='utf-8'))
    memory_file.seek(0)
    return Response(memory_file, mimetype="application/zip", headers={"Content-Disposition": "attachment; filename=ankiapp_export.zip"})

@app.route('/delete_all', methods=['POST'])
def delete_all():
    db = get_db()
    db.execute('DELETE FROM cards'); db.commit(); db.close()
    conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), 'flashcards.db'), isolation_level=None)
    conn.execute('VACUUM'); conn.close()
    if os.path.exists(UPLOAD_FOLDER):
        for f in os.listdir(UPLOAD_FOLDER): os.unlink(os.path.join(UPLOAD_FOLDER, f))
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    # '0.0.0.0' allows Tailscale to route the traffic to the app
    app.run(debug=False, host='0.0.0.0', port=8080)