import os
import json
import sqlite3
import pandas as pd
from flask import (Flask, render_template, request,
                   redirect, url_for, session, jsonify)
from openai import OpenAI
from config import Config
from demo_data import DEMO_CSV

app = Flask(__name__)
app.config.from_object(Config)
client = OpenAI(api_key=app.config['OPENAI_API_KEY'])

def allowed_file(filename):
    return ('.' in filename and
            filename.rsplit('.', 1)[1].lower()
            in app.config['ALLOWED_EXTENSIONS'])

def get_db():
    db_path = os.path.join('instance', 'datatalk.db')
    os.makedirs('instance', exist_ok=True)
    return sqlite3.connect(db_path)

def load_csv_to_db(filepath):
    """Load any CSV into SQLite, auto-detecting schema."""
    df = pd.read_csv(filepath)

    # Clean column names (remove spaces, special chars)
    df.columns = (df.columns.str.strip()
                            .str.replace(' ', '_')
                            .str.replace(r'[^\w]', '', regex=True)
                            .str.lower())

    conn = get_db()
    df.to_sql('user_data', conn,
              if_exists='replace', index=False)
    conn.close()
    return df

def get_schema_string(df):
    """Generate schema description from any dataframe."""
    type_map = {
        'int64': 'INTEGER',
        'float64': 'REAL',
        'object': 'TEXT',
        'datetime64[ns]': 'DATE',
        'bool': 'INTEGER'
    }
    cols = [f"{col} ({type_map.get(str(dtype), 'TEXT')})"
            for col, dtype in df.dtypes.items()]
    return ", ".join(cols)

def get_data_summary(df):
    """Generate a human-readable summary of the uploaded data."""
    summary = {
        'rows': len(df),
        'columns': list(df.columns),
        'column_count': len(df.columns)
    }

    # Find date columns and get range
    for col in df.columns:
        if 'date' in col.lower() or 'time' in col.lower():
            try:
                dates = pd.to_datetime(df[col])
                summary['date_range'] = (
                    f"{dates.min().strftime('%b %Y')} "
                    f"to {dates.max().strftime('%b %Y')}"
                )
                break
            except Exception:
                pass

    return summary

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template('index.html',
                                   error='No file selected')

        file = request.files['file']

        if file.filename == '':
            return render_template('index.html',
                                   error='No file selected')

        if file and allowed_file(file.filename):
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            filepath = os.path.join(
                app.config['UPLOAD_FOLDER'], 'current.csv')
            file.save(filepath)

            df = load_csv_to_db(filepath)
            summary = get_data_summary(df)
            schema = get_schema_string(df)
            sample_rows = df.head(3).to_dict(orient='records')

            # Store in session for use in dashboard
            session['schema'] = schema
            session['summary'] = summary
            session['sample_rows'] = json.dumps(
                sample_rows, default=str)
            session['history'] = []

            return redirect(url_for('dashboard'))

    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if 'schema' not in session:
        return redirect(url_for('index'))

    summary = session.get('summary', {})
    history = session.get('history', [])
    return render_template('dashboard.html',
                           summary=summary,
                           history=history)

@app.route('/query', methods=['POST'])
def query():
    if 'schema' not in session:
        return jsonify({'error': 'No data loaded'}), 400

    question = request.json.get('question', '').strip()
    if not question:
        return jsonify({'error': 'No question provided'}), 400

    schema = session['schema']
    sample_rows = json.loads(session.get('sample_rows', '[]'))

    # Build the prompt
    sample_str = json.dumps(sample_rows, indent=2, default=str)

    prompt = f"""You are a SQL and data analysis expert.

The user has uploaded a CSV file loaded into a SQLite table called 'user_data'.

Schema: {schema}

Sample rows:
{sample_str}

The user asks: "{question}"

Return ONLY a valid JSON object with these fields:
- "sql": a valid SQLite SELECT query that answers the question
- "answer_prefix": a short plain English intro to the answer (max 20 words)
- "chart_type": one of "line", "bar", "pie", "table"
- "chart_label": what the chart is showing (max 8 words)

Rules:
- Use only valid SQLite syntax
- Always use SELECT, never INSERT/UPDATE/DELETE/DROP
- Column names must match the schema exactly
- If the question cannot be answered from this data,
  set sql to null and explain in answer_prefix"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )

        result = json.loads(
            response.choices[0].message.content)

        if not result.get('sql'):
            return jsonify({
                'answer': result.get(
                    'answer_prefix',
                    'That question could not be answered from your data. '
                    'Try rephrasing or ask about a specific column.'),
                'chart_type': 'none',
                'columns': [],
                'rows': []
            })

        # Run the SQL safely
        try:
            conn = get_db()
            cursor = conn.execute(result['sql'])
            columns = [desc[0] for desc in cursor.description]
            rows = [dict(zip(columns, row))
                    for row in cursor.fetchall()]
            conn.close()
        except Exception as sql_error:
            return jsonify({
                'answer': 'Could not run that query against your data. '
                          'Try asking in a different way.',
                'chart_type': 'none',
                'columns': [],
                'rows': []
            })

        if not rows:
            return jsonify({
                'answer': 'No results found for that question.',
                'chart_type': 'none',
                'columns': [],
                'rows': []
            })

        # Add to history
        history = session.get('history', [])
        history.insert(0, {
            'question': question,
            'answer_prefix': result.get('answer_prefix', ''),
            'row_count': len(rows)
        })
        session['history'] = history[:10]
        session.modified = True

        return jsonify({
            'answer': result.get('answer_prefix', ''),
            'chart_type': result.get('chart_type', 'table'),
            'chart_label': result.get('chart_label', ''),
            'columns': columns,
            'rows': rows
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/demo')
def load_demo():
    """Load a pre-built demo dataset."""
    import io
    demo_data = DEMO_CSV

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    filepath = os.path.join(
        app.config['UPLOAD_FOLDER'], 'current.csv')

    with open(filepath, 'w') as f:
        f.write(demo_data)

    df = load_csv_to_db(filepath)
    summary = get_data_summary(df)
    schema = get_schema_string(df)
    sample_rows = df.head(3).to_dict(orient='records')

    session['schema'] = schema
    session['summary'] = summary
    session['sample_rows'] = json.dumps(
        sample_rows, default=str)
    session['history'] = []

    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)