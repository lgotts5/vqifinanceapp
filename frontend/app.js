document.addEventListener('DOMContentLoaded', () => {
    const API_BASE = window.location.hostname === 'localhost' ? 'http://localhost:8000' : '';

    const form             = document.getElementById('pricing-form');
    const submitBtn        = document.getElementById('submit-btn');
    const resultsContainer = document.getElementById('results-container');
    const errorBanner      = document.getElementById('error-banner');
    const statusIndicator  = document.querySelector('.status-indicator');
    const statusText       = document.querySelector('.status-text');
    const terminalContent  = document.getElementById('terminal-content');
    const runNote          = document.getElementById('run-note');

    const resPrimary    = document.getElementById('result-primary');
    const resClassical  = document.getElementById('result-classical');
    const resQubits     = document.getElementById('result-qubits');
    const resTime       = document.getElementById('result-time');
    const resCi         = document.getElementById('result-ci');
    const ciRow         = document.getElementById('ci-row');
    const labelPrimary  = document.getElementById('label-primary');
    const labelClass    = document.getElementById('label-classical');

    // ── Ticker quote fetch ────────────────────────────────────
    const fetchQuoteBtn  = document.getElementById('fetch-quote-btn');
    const tickerStatus   = document.getElementById('ticker-status');

    const flashField = (el) => {
        el.classList.remove('field-filled');
        void el.offsetWidth; // reflow to restart animation
        el.classList.add('field-filled');
    };

    fetchQuoteBtn.addEventListener('click', async () => {
        const ticker = document.getElementById('ticker').value.trim().toUpperCase();
        if (!ticker) { tickerStatus.textContent = 'Enter a ticker first.'; tickerStatus.className = 'ticker-status error'; return; }

        fetchQuoteBtn.disabled = true;
        tickerStatus.className = 'ticker-status';
        tickerStatus.textContent = 'Fetching...';

        try {
            const resp = await fetch(`${API_BASE}/api/quote/${encodeURIComponent(ticker)}`);
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                throw new Error(err.detail || `Error ${resp.status}`);
            }
            const data = await resp.json();

            const priceEl = document.getElementById('stockPrice');
            const volEl   = document.getElementById('volatility');
            priceEl.value = data.price;
            volEl.value   = +(data.volatility * 100).toFixed(2);  // decimal → %
            flashField(priceEl);
            flashField(volEl);

            tickerStatus.textContent = `${data.name} — $${data.price}`;
            tickerStatus.className   = 'ticker-status ok';
        } catch (err) {
            tickerStatus.textContent = err.message;
            tickerStatus.className   = 'ticker-status error';
        } finally {
            fetchQuoteBtn.disabled = false;
        }
    });
    const confBadge     = document.getElementById('confidence-badge');

    // ── 3-D tilt on the glass panel ──────────────────────────
    const glassPanel = document.querySelector('.glass-panel');
    document.addEventListener('mousemove', (e) => {
        if (window.innerWidth < 992) return;
        const xAxis = (window.innerWidth  / 2 - e.pageX) / 50;
        const yAxis = (window.innerHeight / 2 - e.pageY) / 50;
        glassPanel.style.transform = `rotateY(${xAxis}deg) rotateX(${yAxis}deg) translateZ(0)`;
    });
    document.addEventListener('mouseleave', () => {
        glassPanel.style.transform = 'rotateY(0deg) rotateX(0deg) translateZ(0)';
        glassPanel.style.transition = 'transform 0.5s ease';
    });
    glassPanel.addEventListener('mouseenter', () => {
        glassPanel.style.transition = 'none';
    });

    // Update the bottom note based on selected method
    document.getElementById('optionStyle').addEventListener('change', (e) => {
        const style = e.target.value;
        if (style === 'american') {
            runNote.textContent = 'American pricing uses classical backward induction — results are fast.';
        } else {
            runNote.textContent = 'European & Asian methods use QAE and may take 15–60 s.';
        }
    });

    // ── Enable/disable ex-div step based on dividend value ───
    const dividendInput    = document.getElementById('dividend');
    const exDivStepGroup   = document.getElementById('exDivStepGroup');
    dividendInput.addEventListener('input', () => {
        const hasDividend = parseFloat(dividendInput.value) > 0;
        exDivStepGroup.style.opacity      = hasDividend ? '1'    : '0.4';
        exDivStepGroup.style.pointerEvents = hasDividend ? 'auto' : 'none';
    });

    // ── Terminal log helper ───────────────────────────────────
    const addLog = (msg, type = 'info') => {
        const line = document.createElement('div');
        line.className = 'log-line';
        const now = new Date();
        const ts  = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}:${String(now.getSeconds()).padStart(2,'0')}.${String(now.getMilliseconds()).padStart(3,'0')}`;
        const cls = type === 'success' ? 'log-success' : type === 'warn' ? 'log-warn' : 'log-info';
        line.innerHTML = `<span class="log-time">[${ts}]</span> <span class="${cls}">${msg}</span>`;
        terminalContent.appendChild(line);
        terminalContent.scrollTop = terminalContent.scrollHeight;
    };

    const showError = (msg) => {
        errorBanner.textContent = msg;
        errorBanner.style.display = 'block';
    };

    const clearError = () => {
        errorBanner.textContent = '';
        errorBanner.style.display = 'none';
    };

    // ── Compute T (years to expiry) ───────────────────────────
    const calcT = (dateStr) => {
        const today  = new Date();
        const expiry = new Date(dateStr);
        const msPerYear = 365.25 * 24 * 60 * 60 * 1000;
        return (expiry - today) / msPerYear;
    };

    // ── Form submit ───────────────────────────────────────────
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        clearError();

        // Read inputs
        const ticker      = document.getElementById('ticker').value.toUpperCase() || 'N/A';
        const S           = parseFloat(document.getElementById('stockPrice').value);
        const K           = parseFloat(document.getElementById('strikePrice').value);
        const volPct      = parseFloat(document.getElementById('volatility').value);
        const rPct        = parseFloat(document.getElementById('riskFreeRate').value);
        const expiryStr   = document.getElementById('expirationDate').value;
        const optionType  = document.getElementById('optionType').value;
        const optionStyle = document.getElementById('optionStyle').value;

        // Validate
        if (!expiryStr) { showError('Please select an expiration date.'); return; }
        const T = calcT(expiryStr);
        if (T <= 0) { showError('Expiration date must be in the future.'); return; }
        if (isNaN(S) || S <= 0) { showError('Stock price must be a positive number.'); return; }
        if (isNaN(K) || K <= 0) { showError('Strike price must be a positive number.'); return; }
        if (isNaN(volPct) || volPct <= 0) { showError('Volatility must be a positive number.'); return; }

        // Convert % → decimal
        const vol = volPct / 100;
        const r   = rPct   / 100;

        // UI: loading state
        submitBtn.classList.add('loading');
        submitBtn.disabled = true;
        statusIndicator.classList.add('computing');
        statusText.textContent = 'QPU Computing...';
        resultsContainer.style.display = 'block';
        terminalContent.innerHTML = '';
        ciRow.style.display = 'none';
        resPrimary.textContent   = '---';
        resClassical.textContent = '---';
        resQubits.textContent    = '---';
        resTime.textContent      = '---';
        resCi.textContent        = '---';

        addLog(`Initializing pricing engine for ${ticker}...`);
        addLog(`Style: ${optionStyle} | Type: ${optionType} | S=$${S} K=$${K} vol=${volPct}% r=${rPct}% T=${T.toFixed(4)}yr`);

        if (optionStyle === 'european' || optionStyle === 'asian') {
            addLog(`Encoding probability distribution into quantum state...`);
            addLog(`Running Iterative Amplitude Estimation (epsilon=0.01, alpha=0.05)...`, 'warn');
        } else {
            addLog(`Running classical backward induction on ${Math.pow(2,6)-1}-step binomial tree...`);
        }

        // Call the real API
        const D           = parseFloat(document.getElementById('dividend').value)    || 0;
        const ex_div_step = parseInt(document.getElementById('exDivStep').value, 10) || 4;

        let data;
        try {
            const resp = await fetch(`${API_BASE}/api/price`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    option_style: optionStyle,
                    option_type:  optionType,
                    S, K, vol, r, T,
                    D,
                    ex_div_step,
                }),
            });

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                throw new Error(err.detail || `Server error ${resp.status}`);
            }

            data = await resp.json();
        } catch (err) {
            addLog(`Error: ${err.message}`, 'warn');
            showError(`Pricing failed: ${err.message}`);
            submitBtn.classList.remove('loading');
            submitBtn.disabled = false;
            statusIndicator.classList.remove('computing');
            statusText.textContent = 'QPU Idle';
            return;
        }

        // Render backend logs into the terminal
        if (data.logs && data.logs.length) {
            data.logs.forEach((line, i) => {
                const type = line.toLowerCase().includes('error') ? 'warn'
                           : line.toLowerCase().includes('qae')   ? 'success'
                           : 'info';
                addLog(line, type);
            });
        }

        // ── Populate metric cards ────────────────────────────
        const hasQAE = data.qae_price !== null && data.qae_price !== undefined;

        if (hasQAE) {
            // European / Asian: primary = QAE price, secondary = classical
            labelPrimary.textContent  = 'QAE Estimated Price';
            resPrimary.textContent    = `$${data.qae_price.toFixed(4)}`;
            labelClass.textContent    = 'Classical Price';
            resClassical.textContent  = `$${data.classical_price.toFixed(4)}`;
            confBadge.textContent     = '95% Confidence Interval';
            confBadge.style.display   = '';

            if (data.confidence_interval) {
                const [lo, hi] = data.confidence_interval;
                resCi.textContent     = `[$${lo.toFixed(4)},  $${hi.toFixed(4)}]`;
                ciRow.style.display   = 'block';
            }

            if (data.circuit) {
                resQubits.textContent = data.circuit.qubits;
            } else {
                resQubits.textContent = 'N/A';
            }
        } else {
            // American: primary = classical, no QAE card
            labelPrimary.textContent  = 'Classical Price';
            resPrimary.textContent    = `$${data.classical_price.toFixed(4)}`;
            labelClass.textContent    = 'Method';
            resClassical.textContent  = 'Classical Only';
            confBadge.style.display   = 'none';
            ciRow.style.display       = 'none';
            resQubits.textContent     = 'N/A';
        }

        resTime.textContent = `${data.execution_time_ms} ms`;

        addLog(`Simulation complete.`, 'success');

        // UI: restore
        submitBtn.classList.remove('loading');
        submitBtn.disabled = false;
        statusIndicator.classList.remove('computing');
        statusText.textContent = 'QPU Idle';
    });
});
