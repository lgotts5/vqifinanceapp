# VQI Quantum Option Pricing App

Integrates the **Vanderbilt Quantum Initiative** frontend with the **QAEFINAL.py** quantum pricing engine via a FastAPI backend.

---

## Project Structure

```
vqi-finance-app/
├── frontend/
│   ├── index.html      ← Pricing UI (updated form + real results)
│   ├── overview.html   ← About page (unchanged)
│   ├── styles.css      ← All styling (unchanged)
│   └── app.js          ← Calls the real FastAPI backend
├── backend/
│   ├── main.py         ← FastAPI app + static file server
│   ├── QAEFINAL.py     ← Pricing engine (minimal refactor of original)
│   └── requirements.txt
└── README.md
```

---

## Setup

### 1. Create and activate a virtual environment

```bash
cd ~/Desktop/vqi-finance-app
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r backend/requirements.txt
```

### 3. Run the server

```bash
cd backend
uvicorn main:app --reload --port 8000
```

### 4. Open the app

Visit **http://localhost:8000** in your browser.

---

## How It Works

| Step | What happens |
|------|-------------|
| You fill out the form | Stock price, strike, expiry, volatility, risk-free rate, option style |
| `app.js` sends `POST /api/price` | JSON payload with all parameters |
| `main.py` routes to `QAEFINAL.py` | Calls `price_european`, `price_american`, or `price_asian` |
| Results returned as JSON | Classical price, QAE price, 95% CI, circuit stats, runtime logs |
| UI renders results | Metric cards + live terminal log output |

---

## Pricing Methods

| Method | Algorithm | Notes |
|--------|-----------|-------|
| **European** | Iterative QAE (fully quantum) | ~15–60 s on laptop. True quantum advantage. |
| **American** | Classical backward induction | Fast (~1 s). QAE not applicable (sequential decisions). |
| **Asian** | Hybrid: classical paths + QAE | ~5–20 s. Classical path enumeration, QAE estimates E[payoff]. |

---

## API

`POST /api/price`

```json
{
  "option_style": "european",
  "option_type": "call",
  "S": 100,
  "K": 100,
  "vol": 0.2,
  "r": 0.05,
  "T": 1.0,
  "D": 0,
  "ex_div_step": 4
}
```

`GET /api/health` — returns `{"status": "ok"}`

---

## Changes from Original Files

**QAEFINAL.py** (minimal refactor):
- Functions (`price_european`, `price_american`, `price_asian`) now accept parameters instead of reading module-level globals
- `plt.show()` removed — server has no display; numerical results are returned instead
- Each function returns a structured dict + logs list

**Frontend**:
- Form updated: "Current Option Price" → "Stock Price", added Volatility %, Risk-Free Rate %, and Pricing Method (option style) fields
- `app.js` replaces the fake sleep/random simulation with a real `fetch` call to `POST /api/price`
- Results display: QAE price, classical price, 95% CI, qubits, execution time all populated from real backend data
