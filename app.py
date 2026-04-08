# AI tools (Claude by Anthropic) were used during development to support
# debugging and problem solving, in accordance with CS50's academic honesty policy.

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

# AI-assisted: dynamic schema detection and column name normalisation
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

# AI-assisted: date range detection logic
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

# AI-assisted: two-stage prompt engineering approach, question intent
# detection logic, and smart column selection algorithm were designed
# with AI assistance.

@app.route('/query', methods=['POST'])
def query():
    if 'schema' not in session:
        return jsonify({'error': 'No data loaded'}), 400

    question = request.json.get('question', '').strip()
    if not question:
        return jsonify({'error': 'No question provided'}), 400

    schema = session['schema']
    sample_rows = json.loads(session.get('sample_rows', '[]'))
    sample_str = json.dumps(sample_rows, indent=2, default=str)

    # Detect question intent upfront
    ranking_keywords = ['highest', 'lowest', 'best', 'worst', 'most',
                        'least', 'top', 'bottom', 'which', 'winner']
    is_ranking_question = any(kw in question.lower() for kw in ranking_keywords)

    # First API call: generate SQL and chart metadata
    # AI-assisted: prompt structure and SQL generation instructions
    prompt = f"""You are a SQL and data analysis expert.

The user has uploaded a CSV file loaded into a SQLite table called 'user_data'.

Schema: {schema}

Sample rows:
{sample_str}

The user asks: "{question}"

You MUST return a valid JSON object with EXACTLY these four fields, no exceptions:

1. "sql": a valid SQLite SELECT query. Important rules:
   - For "which X had highest/lowest Y" questions, return ALL rows ordered by Y descending
   - For "show X by Y" or "what is X by Y" questions, order by the label column ascending so charts read naturally left to right
   - Never use LIMIT unless the user explicitly asks for a specific number of results
   - Always use SELECT, never INSERT/UPDATE/DELETE/DROP
   - Column names must match the schema exactly
   - Always include an explicit ORDER BY clause
   - For profit margin questions, always calculate it as:
     ROUND((SUM(revenue) - SUM(cost)) * 100.0 / SUM(revenue), 2) AS profit_margin
     Never return raw profit as a substitute for margin percentage
   - Always name percentage columns with 'margin', 'rate' or 'percent' 
     in the column alias so they can be identified correctly

2. "answer_prefix": a single sentence introducing the answer.
   - For ranking questions: "December 2024 had the highest profit margin at 60.3%."
   - For display questions: "Here is total revenue broken down by month."

3. "chart_type": one of "line", "bar", "pie", "table"
   - Use "line" for time series data ordered chronologically
   - Use "bar" for category comparisons
   - Use "pie" for proportional breakdowns
   - Use "table" for multi-column results

4. "chart_label": what the chart is showing, max 8 words

If the question cannot be answered from this data, set sql to null and explain in answer_prefix.

Return ONLY the JSON object. No markdown, no backticks, no preamble."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)

        if not result.get('sql'):
            return jsonify({
                'answer': result.get(
                    'answer_prefix',
                    'That question could not be answered from your data. '
                    'Try rephrasing or ask about a specific column.'),
                'explanation': '',
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
                'explanation': '',
                'chart_type': 'none',
                'columns': [],
                'rows': []
            })

        if not rows:
            return jsonify({
                'answer': 'No results found for that question.',
                'explanation': '',
                'chart_type': 'none',
                'columns': [],
                'rows': []
            })

        # Smart column selection - prefer margin/percent/rate columns
        priority_keywords = ['margin', 'percent', 'rate', 'pct', 'ratio']

        numeric_columns = [c for c in columns
                          if any(isinstance(r.get(c), (int, float))
                                 for r in rows)]
        
        # AI-assisted: scoring algorithm for selecting the most meaningful chart column
        def priority_score(col):
            col_lower = col.lower()
            # Exact match gets highest score
            if col_lower == 'profit_margin':
                return 999
            for i, kw in enumerate(priority_keywords):
                if kw in col_lower:
                    return len(priority_keywords) - i
            return 0

        priority_cols = [c for c in numeric_columns if priority_score(c) > 0]
        chart_value_col = (
            max(priority_cols, key=priority_score)
            if priority_cols
            else (numeric_columns[-1] if numeric_columns else None)
        )
        chart_label_col = columns[0]

        # Find the actual best row by chart_value_col for ranking questions
        if is_ranking_question and rows and chart_value_col:
            best_row = max(
                rows,
                key=lambda r: r.get(chart_value_col, 0)
                if isinstance(r.get(chart_value_col), (int, float)) else 0
            )
        else:
            best_row = rows[0]

        # Build answer based on question type
        if rows and chart_value_col:
            best_label = best_row.get(chart_label_col, '')
            best_value = best_row.get(chart_value_col, '')
            if isinstance(best_value, float):
                best_value_str = f"{best_value:.2f}"
            else:
                best_value_str = str(best_value)

            if is_ranking_question:
                answer = (f"{best_label} had the highest "
                         f"{chart_value_col.replace('_', ' ')} "
                         f"at {best_value_str}.")
            else:
                answer = (f"Here is {chart_value_col.replace('_', ' ')} "
                         f"broken down by {chart_label_col.replace('_', ' ')}.")
        else:
            answer = result.get('answer_prefix', 'Here are the results.')

        # Build top_result_str for explanation prompt
        first_val = best_row.get(chart_value_col, '') if chart_value_col else ''
        if isinstance(first_val, float):
            first_val_str = f"{first_val:.2f}"
        else:
            first_val_str = str(first_val)

        if is_ranking_question:
            top_result_str = (
                f"{best_row.get(chart_label_col, '')} with "
                f"{chart_value_col.replace('_', ' ') if chart_value_col else 'value'} "
                f"of {first_val_str}"
            )
            explanation_instruction = (
                f"Write 2-3 sentences referencing {top_result_str} specifically. "
                f"Explain what the metric means, how it was calculated, and include "
                f"the actual figures for this result only. Do not reference other "
                f"time periods unless making a direct comparison."
            )
        else:
            top_result_str = (
                f"all {chart_label_col.replace('_', ' ')}s showing "
                f"{chart_value_col.replace('_', ' ') if chart_value_col else 'values'} "
                f"across the full period"
            )
            explanation_instruction = (
                f"Write 2-3 sentences describing the overall trend in the data. "
                f"Mention the highest and lowest points by name and any notable "
                f"patterns or changes over time. Use plain English."
            )

        # Second API call: generate explanation from actual results
        # AI-assisted: explanation prompt structure and grounding instructions
        explanation_prompt = f"""You are a data analyst explaining query results to a business user.

The user asked: "{question}"

The actual query results are:
{json.dumps(rows, indent=2, default=str)}

{explanation_instruction}

Return a JSON object with one field: "explanation"

Return ONLY the JSON object. No markdown, no backticks, no preamble."""

        explanation_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": explanation_prompt}],
            response_format={"type": "json_object"}
        )
        explanation_result = json.loads(
            explanation_response.choices[0].message.content)

        # Add to history
        history = session.get('history', [])
        history.insert(0, {
            'question': question,
            'answer_prefix': answer,
            'row_count': len(rows)
        })
        session['history'] = history[:10]
        session.modified = True

        return jsonify({
            'answer': answer,
            'explanation': explanation_result.get('explanation', ''),
            'chart_type': result.get('chart_type', 'table'),
            'chart_label': result.get('chart_label', ''),
            'chart_value_col': chart_value_col,
            'chart_label_col': chart_label_col,
            'columns': columns,
            'rows': rows
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/demo')
def load_demo():
    """Load a pre-built demo dataset."""
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