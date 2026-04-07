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

    fetch('/query', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({question: question})
    })
    .then(r => r.json())
    .then(data => {
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
    document.getElementById('tableContainer').innerHTML = '';

    if (currentChart) {
        currentChart.destroy();
        currentChart = null;
    }

    const canvas = document.getElementById('myChart');

    if (data.chart_type === 'table' || !data.rows.length) {
        canvas.style.display = 'none';
        renderTable(data.columns, data.rows);
        return;
    }

    canvas.style.display = 'block';
    const labels = data.rows.map(r => Object.values(r)[0]);
    const values = data.rows.map(r => Object.values(r)[1]);

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
            }
        }
    });
}

function renderTable(columns, rows) {
    if (!rows.length) return;
    let html = '<table><thead><tr>';
    columns.forEach(col => html += `<th>${col}</th>`);
    html += '</tr></thead><tbody>';
    rows.forEach(row => {
        html += '<tr>';
        columns.forEach(col => html += `<td>${row[col] ?? ''}</td>`);
        html += '</tr>';
    });
    html += '</tbody></table>';
    document.getElementById('tableContainer').innerHTML = html;
}