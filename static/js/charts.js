// AI-assisted: chart rendering logic, column selection fallback,
// and y-axis formatting callback developed with AI assistance.

let currentChart = null;

function askQuestion(question) {
    document.getElementById('questionInput').value = question;
    submitQuestion(question);
}

document.getElementById('askBtn').addEventListener('click', function() {
    const question = document.getElementById('questionInput').value.trim();
    if (question) submitQuestion(question);
});

document.getElementById('questionInput').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        const question = this.value.trim();
        if (question) submitQuestion(question);
    }
});

function submitQuestion(question) {
    const btn = document.getElementById('askBtn');
    const resultSection = document.getElementById('resultSection');

    btn.textContent = 'Thinking...';
    btn.disabled = true;
    resultSection.style.display = 'block';
    resultSection.classList.add('loading');

    // Clear previous explanation immediately
    const existingExplanation = document.getElementById('explanationText');
    if (existingExplanation) existingExplanation.remove();
    
    document.getElementById('answerText').textContent = '';

    fetch('/query', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({question: question})
    })
    .then(r => r.json())
    .then(data => {
        console.log('API response:', data);
        btn.textContent = 'Ask';
        btn.disabled = false;
        resultSection.classList.remove('loading');

        if (data.error) {
            document.getElementById('answerText').textContent =
                'Error: ' + data.error;
            return;
        }

        displayResult(data);
    })
    .catch(err => {
        btn.textContent = 'Ask';
        btn.disabled = false;
        resultSection.classList.remove('loading');
        document.getElementById('answerText').textContent =
            'Something went wrong. Please try again.';
        console.error(err);
    });
}

function displayResult(data) {
    document.getElementById('resultSection').style.display = 'block';
    document.getElementById('answerText').textContent = data.answer;

    // Show explanation if present
    const existingExplanation = document.getElementById('explanationText');
    if (existingExplanation) existingExplanation.remove();

    if (data.explanation) {
        const explanation = document.createElement('p');
        explanation.id = 'explanationText';
        explanation.className = 'explanation-text';
        explanation.textContent = data.explanation;
        document.getElementById('answerText').after(explanation);
    }

    document.getElementById('tableContainer').innerHTML = '';

    if (currentChart) {
        currentChart.destroy();
        currentChart = null;
    }

    const canvas = document.getElementById('myChart');

    if (data.chart_type === 'table' || !data.rows || !data.rows.length) {
        canvas.style.display = 'none';
        if (data.rows && data.rows.length) {
            renderTable(data.columns, data.rows);
        }
        return;
    }

    canvas.style.display = 'block';

    // Use server-provided column hints, fall back to first/last columns
    const labelCol = data.chart_label_col || Object.keys(data.rows[0])[0];
    const valueCol = data.chart_value_col || Object.keys(data.rows[0])[1];

    // Sort rows chronologically for time-based labels
    const isTimeSeries = data.rows.every(r => 
    /^\d{4}/.test(String(r[labelCol]))
    );

    const sortedRows = isTimeSeries 
    ? [...data.rows].sort((a, b) => 
        String(a[labelCol]).localeCompare(String(b[labelCol])))
    : data.rows;


    const labels = sortedRows.map(r => r[labelCol]);
    const values = sortedRows.map(r => r[valueCol]);

    const colours = [
        '#4F46E5','#7C3AED','#2563EB','#059669',
        '#D97706','#DC2626','#0891B2','#65A30D'
    ];

    currentChart = new Chart(canvas, {
        type: data.chart_type === 'pie' ? 'pie' :
              data.chart_type === 'line' ? 'line' : 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: data.chart_label || 'Result',
                data: values,
                backgroundColor: data.chart_type === 'pie' ?
                    colours : colours[0],
                borderColor: colours[0],
                borderWidth: data.chart_type === 'line' ? 2 : 0,
                fill: false,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: data.chart_type === 'pie' }
            },
            scales: data.chart_type !== 'pie' ? {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            if (value >= 1000) {
                                return '£' + value.toLocaleString();
                            }
                            if (value >= 1 || value === 0) {
                                return value % 1 !== 0 ?
                                    value.toFixed(2) : value;
                            }
                            // Small decimals - show as-is without % suffix
                            return value.toFixed(2);
                        }
                    }
                }
            } : {}
        }
    });
}

function renderTable(columns, rows) {
    if (!rows.length) return;
    let html = '<table><thead><tr>';
    columns.forEach(col => {
        html += `<th>${col.replace(/_/g, ' ')}</th>`;
    });
    html += '</tr></thead><tbody>';
    rows.forEach(row => {
        html += '<tr>';
        columns.forEach(col => {
            let val = row[col] ?? '';
            if (typeof val === 'number' && val % 1 !== 0) {
                val = val.toFixed(2);
            }
            html += `<td>${val}</td>`;
        });
        html += '</tr>';
    });
    html += '</tbody></table>';
    document.getElementById('tableContainer').innerHTML = html;
}