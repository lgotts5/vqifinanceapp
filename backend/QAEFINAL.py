"""
Quantum Option Pricing Engine
==============================
Minimal refactor of QAEFINAL.py for API use.
Original pricing logic is preserved exactly — only changes are:
  - Functions accept parameters instead of module-level globals
  - plt.show() removed (server context; no display available)
  - Results returned as dicts with a logs list instead of printed

Prices three types of options using a CRR binomial tree and QAE:
  1. European  — FULLY QUANTUM. QAE genuinely prices the option.
  2. American  — CLASSICAL ONLY. Backward induction on binomial tree.
  3. Asian     — HYBRID. Classical path enumeration, QAE estimates expectation.
"""

import numpy as np
from math import comb

from qiskit import QuantumCircuit
from qiskit_algorithms import IterativeAmplitudeEstimation, EstimationProblem
from qiskit.circuit.library import StatePreparation


# ─────────────────────────────────────────────────────────────
#  DIVIDEND HELPER
# ─────────────────────────────────────────────────────────────
def _stock_price(S0, u, d, dt, step, j, D, r, ex_div_step):
    """
    Returns the stock price at node (step, j) adjusted for a discrete
    cash dividend D paid at ex_div_step. If D=0 returns standard CRR price.
    """
    raw = S0 * (u ** j) * (d ** (step - j))
    if D > 0 and step < ex_div_step:
        pv_div = D * np.exp(-r * (ex_div_step - step) * dt)
        raw    = raw - pv_div
    return raw


# ─────────────────────────────────────────────────────────────
#  QAE HELPER
# ─────────────────────────────────────────────────────────────
def _run_qae(probs, payoff_vals, epsilon, alpha, logs):
    """
    Encode (probs, payoff_vals) into a quantum circuit via StatePreparation
    and run Iterative Amplitude Estimation.
    Returns (a_hat, confidence_interval, max_payoff, circuit).
    """
    max_payoff = float(payoff_vals.max())
    if max_payoff <= 0:
        raise ValueError("max_payoff is 0 — option is entirely out of the money.")

    ratios   = payoff_vals / max_payoff
    combined = []
    for p, f in zip(probs, ratios):
        combined.append(np.sqrt(p * (1.0 - float(f))))   # |i, 0>
        combined.append(np.sqrt(p * float(f)))            # |i, 1>

    combined = np.array(combined, dtype=float)
    combined /= np.linalg.norm(combined)

    num_qubits = int(np.log2(len(combined)))
    circuit    = QuantumCircuit(num_qubits)
    circuit.append(StatePreparation(combined, normalize=True), range(num_qubits))

    problem = EstimationProblem(state_preparation=circuit, objective_qubits=[0])
    ae      = IterativeAmplitudeEstimation(epsilon_target=epsilon, alpha=alpha)
    result  = ae.estimate(problem)

    logs.append(f"Number of iterations  : {len(result.powers)}")
    logs.append(f"Shots per iteration   : {result.shots}")

    a_hat = float(result.estimation)
    ci    = np.array(result.confidence_interval, dtype=float)
    return a_hat, ci, max_payoff, circuit


# ─────────────────────────────────────────────────────────────
#  METHOD 1 — EUROPEAN OPTION
# ─────────────────────────────────────────────────────────────
def price_european(S, K, vol, r, T, call,
                   D=0, ex_div_step=4,
                   num_uncertainty_qubits=6, epsilon=0.01, alpha=0.05):
    logs     = []
    label    = f"European {'Call' if call else 'Put'}"
    discount = np.exp(-r * T)

    N  = (2 ** num_uncertainty_qubits) - 1
    dt = T / N
    u  = np.exp(vol * np.sqrt(dt))
    d  = 1.0 / u
    q  = (np.exp(r * dt) - d) / (u - d)

    if not (0.0 < q < 1.0):
        raise ValueError(f"Risk-neutral prob q={q:.4f} out of (0,1). Check input parameters.")

    j   = np.arange(N + 1)
    S_T = np.array([_stock_price(S, u, d, dt, N, int(k), D, r, ex_div_step) for k in j])

    probs = np.array(
        [comb(N, int(k)) * (q ** k) * ((1 - q) ** (N - k)) for k in j],
        dtype=float
    )
    probs /= probs.sum()

    payoff_vals     = np.maximum(0.0, S_T - K) if call else np.maximum(0.0, K - S_T)
    classical_price = discount * float(np.dot(probs, payoff_vals))

    logs.append(f"Running QAE for {label}...")
    a_hat, ci, max_payoff, circuit = _run_qae(probs, payoff_vals, epsilon, alpha, logs)

    qae_price = discount * a_hat * max_payoff
    ci_price  = (discount * ci * max_payoff).tolist()

    logs.append(f"Classical price           : ${classical_price:.4f}")
    logs.append(f"QAE estimated price       : ${qae_price:.4f}")
    logs.append(f"QAE raw amplitude a       : {a_hat:.6f}")
    logs.append(f"95% CI (price)            : [${ci_price[0]:.4f},  ${ci_price[1]:.4f}]")

    from qiskit.compiler import transpile
    transpiled  = transpile(circuit, basis_gates=['u', 'cx'], optimization_level=0)
    ops         = transpiled.count_ops()
    total_gates = sum(ops.values())

    logs.append(f"Qubits                : {circuit.num_qubits}")
    logs.append(f"Single qubit gates (u): {ops.get('u', 0)}")
    logs.append(f"Two qubit gates (cx)  : {ops.get('cx', 0)}")
    logs.append(f"Total gates           : {total_gates}")

    return {
        "option_style": "european",
        "option_type":  "call" if call else "put",
        "classical_price":     round(classical_price, 4),
        "qae_price":           round(qae_price, 4),
        "qae_amplitude":       round(a_hat, 6),
        "confidence_interval": [round(ci_price[0], 4), round(ci_price[1], 4)],
        "circuit": {
            "qubits":             circuit.num_qubits,
            "single_qubit_gates": ops.get('u', 0),
            "two_qubit_gates":    ops.get('cx', 0),
            "total_gates":        total_gates,
        },
        "logs": logs,
    }


# ─────────────────────────────────────────────────────────────
#  METHOD 2 — AMERICAN OPTION  (classical only)
# ─────────────────────────────────────────────────────────────
def price_american(S, K, vol, r, T, call,
                   D=0, ex_div_step=4, num_uncertainty_qubits=6):
    logs  = []
    label = f"American {'Call' if call else 'Put'}"

    N         = (2 ** num_uncertainty_qubits) - 1
    dt        = T / N
    u         = np.exp(vol * np.sqrt(dt))
    d         = 1.0 / u
    q         = (np.exp(r * dt) - d) / (u - d)
    disc_step = np.exp(-r * dt)

    if not (0.0 < q < 1.0):
        raise ValueError(f"Risk-neutral prob q={q:.4f} out of (0,1). Check input parameters.")

    j   = np.arange(N + 1)
    S_T = np.array([_stock_price(S, u, d, dt, N, int(k), D, r, ex_div_step) for k in j])

    option = np.maximum(0.0, S_T - K) if call else np.maximum(0.0, K - S_T)

    logs.append(f"Running classical backward induction for {label}...")
    for step in range(N - 1, -1, -1):
        j_step   = np.arange(step + 1)
        S_step   = np.array([_stock_price(S, u, d, dt, step, int(k), D, r, ex_div_step) for k in j_step])
        held     = disc_step * (q * option[1:step + 2] + (1 - q) * option[0:step + 1])
        exercise = np.maximum(0.0, S_step - K) if call else np.maximum(0.0, K - S_step)
        option   = np.maximum(held, exercise)

    american_price = float(option[0])

    logs.append(f"Classical price (backward induction): ${american_price:.4f}")
    logs.append("Note: QAE is not used for American options.")
    logs.append("American pricing requires sequential backward induction across all nodes,")
    logs.append("which cannot be encoded as a single amplitude estimation problem.")

    return {
        "option_style": "american",
        "option_type":  "call" if call else "put",
        "classical_price":     round(american_price, 4),
        "qae_price":           None,
        "qae_amplitude":       None,
        "confidence_interval": None,
        "circuit":             None,
        "logs":                logs,
    }


# ─────────────────────────────────────────────────────────────
#  METHOD 3 — ASIAN OPTION  (arithmetic average price, hybrid)
# ─────────────────────────────────────────────────────────────
def price_asian(S, K, vol, r, T, call,
                D=0, ex_div_step=4, n_steps=4, epsilon=0.01, alpha=0.05):
    logs     = []
    label    = f"Asian {'Call' if call else 'Put'} (Arithmetic Avg)"
    discount = np.exp(-r * T)

    dt = T / n_steps
    u  = np.exp(vol * np.sqrt(dt))
    d  = 1.0 / u
    q  = (np.exp(r * dt) - d) / (u - d)

    if not (0.0 < q < 1.0):
        raise ValueError(f"Risk-neutral prob q={q:.4f} out of (0,1). Check input parameters.")

    num_paths    = 2 ** n_steps
    path_probs   = np.zeros(num_paths)
    path_payoffs = np.zeros(num_paths)

    logs.append(f"Enumerating all {num_paths} paths classically for {label}...")
    for idx in range(num_paths):
        price = S
        total = S
        prob  = 1.0
        ups   = 0
        for step in range(n_steps):
            up = (idx >> (n_steps - 1 - step)) & 1
            if up:
                ups  += 1
                prob *= q
            else:
                prob *= (1.0 - q)
            price  = _stock_price(S, u, d, dt, step + 1, ups, D, r, ex_div_step)
            total += price

        avg_price          = total / (n_steps + 1)
        path_probs[idx]    = prob
        path_payoffs[idx]  = max(0.0, avg_price - K) if call else max(0.0, K - avg_price)

    path_probs      /= path_probs.sum()
    classical_payoff = float(np.dot(path_probs, path_payoffs))
    classical_price  = discount * classical_payoff

    logs.append(f"Classical Asian price ({n_steps}-step tree): ${classical_price:.4f}")
    logs.append(f"Running QAE for {label}...")
    a_hat, ci, max_payoff, circuit = _run_qae(path_probs, path_payoffs, epsilon, alpha, logs)

    qae_price = discount * a_hat * max_payoff
    ci_price  = (discount * ci * max_payoff).tolist()

    logs.append(f"QAE estimated price       : ${qae_price:.4f}")
    logs.append(f"QAE raw amplitude a       : {a_hat:.6f}")
    logs.append(f"95% CI (price)            : [${ci_price[0]:.4f},  ${ci_price[1]:.4f}]")

    from qiskit.compiler import transpile
    transpiled  = transpile(circuit, basis_gates=['u', 'cx'], optimization_level=0)
    ops         = transpiled.count_ops()
    total_gates = sum(ops.values())

    logs.append(f"Qubits                : {circuit.num_qubits}")
    logs.append(f"Single qubit gates (u): {ops.get('u', 0)}")
    logs.append(f"Two qubit gates (cx)  : {ops.get('cx', 0)}")
    logs.append(f"Total gates           : {total_gates}")

    return {
        "option_style": "asian",
        "option_type":  "call" if call else "put",
        "classical_price":     round(classical_price, 4),
        "qae_price":           round(qae_price, 4),
        "qae_amplitude":       round(a_hat, 6),
        "confidence_interval": [round(ci_price[0], 4), round(ci_price[1], 4)],
        "circuit": {
            "qubits":             circuit.num_qubits,
            "single_qubit_gates": ops.get('u', 0),
            "two_qubit_gates":    ops.get('cx', 0),
            "total_gates":        total_gates,
        },
        "logs": logs,
    }
