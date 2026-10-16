import asyncio
import json
import time
from collections import deque
from datetime import datetime, timezone

import aiohttp
import pandas as pd
import streamlit as st
import websockets

st.set_page_config(page_title="RADAR AI — First Leg", page_icon="📡", layout="wide")

REST = "https://fapi.binance.com"
WS = "wss://fstream.binance.com/stream?streams="
st.title("📡 RADAR AI — FIRST LEG")
st.caption("Scanner experimental de futuros USDT da Binance • Somente análise e simulação; não envia ordens.")

with st.sidebar:
    st.header("Configuração")
    refresh_sec = st.slider("Atualização do painel (segundos)", 3, 15, 5)
    max_symbols = st.selectbox("Contratos exibidos", [20, 50, 100], index=1)
    min_score = st.slider("Pontuação mínima", 50, 90, 65)
    st.warning("Protótipo: o score é heurístico e ainda precisa de backtest. Não é recomendação financeira.")

@st.cache_data(ttl=300)
def get_symbols():
    import requests
    r = requests.get(f"{REST}/fapi/v1/exchangeInfo", timeout=15)
    r.raise_for_status()
    data = r.json()
    return sorted([
        s["symbol"] for s in data["symbols"]
        if s.get("contractType") == "PERPETUAL"
        and s.get("quoteAsset") == "USDT"
        and s.get("status") == "TRADING"
    ])

@st.cache_data(ttl=20)
def get_tickers():
    import requests
    r = requests.get(f"{REST}/fapi/v1/ticker/24hr", timeout=15)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=20)
def get_oi(symbol):
    import requests
    r = requests.get(f"{REST}/fapi/v1/openInterest", params={"symbol": symbol}, timeout=8)
    r.raise_for_status()
    return float(r.json()["openInterest"])

@st.cache_data(ttl=20)
def get_funding(symbol):
    import requests
    r = requests.get(f"{REST}/fapi/v1/premiumIndex", params={"symbol": symbol}, timeout=8)
    r.raise_for_status()
    return float(r.json()["lastFundingRate"])

def fmt(x, digits=4):
    try:
        return f"{float(x):,.{digits}f}"
    except Exception:
        return "—"

symbols = []
error = None
try:
    symbols = get_symbols()
    tickers = get_tickers()
except Exception as e:
    st.error("Erro ao conectar com a Binance:")
    st.exception(e)
    st.stop()

ticker_map = {x["symbol"]: x for x in tickers}
eligible = [s for s in symbols if s in ticker_map]
eligible.sort(key=lambda s: float(ticker_map[s].get("quoteVolume", 0)), reverse=True)
watch = eligible[:max_symbols]

st.info(f"Contratos perpétuos USDT elegíveis encontrados: **{len(eligible)}**. Este protótipo mostra os {len(watch)} de maior volume de 24h; não captura ainda o order book de todos os contratos continuamente.")
rows = []
progress = st.progress(0, text="Consultando indicadores...")
for i, sym in enumerate(watch):
    t = ticker_map[sym]
    price = float(t["lastPrice"])
    change = float(t["priceChangePercent"])
    qvol = float(t.get("quoteVolume", 0))
    try:
        oi = get_oi(sym)
    except Exception:
        oi = None
    try:
        funding = get_funding(sym)
    except Exception:
        funding = None

    # Heuristic score: momentum + volume rank proxy + OI availability.
    # Not a predictive model and does not use a historical OI delta yet.
    momentum = min(abs(change) / 8.0, 1.0) * 25
    volume_score = min((qvol / 100_000_000), 1.0) * 20
    oi_score = 10 if oi is not None and oi > 0 else 0
    score = round(min(momentum + volume_score + oi_score, 55), 1)
    direction = "LONG" if change > 0 else ("SHORT" if change < 0 else "NEUTRO")
    if score >= min_score:
        status = "OBSERVAR — score"
    elif abs(change) >= 3:
        status = "MOVIMENTO FORTE"
    else:
        status = "Aguardar"
    rows.append({
        "Símbolo": sym,
        "Preço": price,
        "Variação 24h %": change,
        "Volume 24h USDT": qvol,
        "Open Interest": oi,
        "Funding %": funding * 100 if funding is not None else None,
        "Viés": direction,
        "Score (0–100)": score,
        "Estado": status,
    })
    progress.progress((i + 1) / len(watch), text=f"Consultando {sym} ({i+1}/{len(watch)})")
progress.empty()

df = pd.DataFrame(rows)
if df.empty:
    st.warning("Nenhum dado retornado.")
    st.stop()

strong = df[df["Score (0–100)"] >= min_score]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Contratos analisados", len(df))
c2.metric("Movimentos ≥ 3%", int((df["Variação 24h %"].abs() >= 3).sum()))
c3.metric("Observações acima do score", len(strong))
c4.metric("Maior variação 24h", f"{df['Variação 24h %'].abs().max():.2f}%")

tab1, tab2, tab3 = st.tabs(["📡 Scanner", "📚 Order book", "🧪 Simulação"])
with tab1:
    st.subheader("Scanner de oportunidades")
    st.caption("Score atual é apenas um filtro heurístico baseado em variação de 24h e volume. Ainda não é o score final com fluxo, variação do OI e histórico do livro.")
    show = df.sort_values("Score (0–100)", ascending=False).copy()
    st.dataframe(show, use_container_width=True, hide_index=True, column_config={
        "Preço": st.column_config.NumberColumn(format="%.8f"),
        "Variação 24h %": st.column_config.NumberColumn(format="%.2f%%"),
        "Volume 24h USDT": st.column_config.NumberColumn(format="%.0f"),
        "Open Interest": st.column_config.NumberColumn(format="%.2f"),
        "Funding %": st.column_config.NumberColumn(format="%.5f%%"),
        "Score (0–100)": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f"),
    })
    st.download_button("Baixar scanner CSV", df.to_csv(index=False).encode("utf-8"), "radar_scanner.csv", "text/csv")
with tab2:
    st.subheader("Order book — consulta sob demanda")
    selected = st.selectbox("Escolha um contrato", watch, index=0)
    depth = st.selectbox("Profundidade", [5, 10, 20, 100], index=2)
    if st.button("Consultar livro agora"):
        import requests
        try:
            r = requests.get(f"{REST}/fapi/v1/depth", params={"symbol": selected, "limit": depth}, timeout=10)
            r.raise_for_status()
            book = r.json()
            bids = pd.DataFrame(book["bids"], columns=["Preço compra", "Quantidade"])
            asks = pd.DataFrame(book["asks"], columns=["Preço venda", "Quantidade"])
            bids["Preço compra"] = bids["Preço compra"].astype(float)
            bids["Quantidade"] = bids["Quantidade"].astype(float)
            asks["Preço venda"] = asks["Preço venda"].astype(float)
            asks["Quantidade"] = asks["Quantidade"].astype(float)
            bid_notional = (bids["Preço compra"] * bids["Quantidade"]).sum()
            ask_notional = (asks["Preço venda"] * asks["Quantidade"]).sum()
            total = bid_notional + ask_notional
            imbalance = (bid_notional - ask_notional) / total * 100 if total else 0
            a, b, c = st.columns(3)
            a.metric("Liquidez compra (USDT)", f"{bid_notional:,.0f}")
            b.metric("Liquidez venda (USDT)", f"{ask_notional:,.0f}")
            c.metric("Desequilíbrio", f"{imbalance:+.2f}%")
            st.caption("Instantâneo REST: não é um livro sincronizado em tempo real nem prova de intenção. Ordens podem ser canceladas.")
            l, rcol = st.columns(2)
            with l:
                st.write("**Compras (bids)**")
                st.dataframe(bids, use_container_width=True, hide_index=True)
            with rcol:
                st.write("**Vendas (asks)**")
                st.dataframe(asks, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Erro ao consultar order book: {e}")
with tab3:
    st.subheader("Simulação manual")
    st.write("Registre uma operação fictícia. Nenhuma ordem é enviada à Binance.")
    with st.form("paper_trade"):
        sym = st.selectbox("Contrato", watch, key="sim_symbol")
        side = st.radio("Direção", ["LONG", "SHORT"], horizontal=True)
        entry = st.number_input("Preço de entrada simulado", min_value=0.0, value=float(ticker_map[sym]["lastPrice"]), format="%.8f")
        stop_pct = st.number_input("Stop (%)", min_value=0.1, max_value=20.0, value=1.0, step=0.1)
        target_pct = st.number_input("Alvo (%)", min_value=0.1, max_value=50.0, value=2.0, step=0.1)
        size = st.number_input("Tamanho fictício da posição (USDT)", min_value=1.0, value=10.0, step=1.0)
        submitted = st.form_submit_button("Calcular níveis")
    if submitted and entry > 0:
        if side == "LONG":
            stop = entry * (1 - stop_pct/100)
            target = entry * (1 + target_pct/100)
        else:
            stop = entry * (1 + stop_pct/100)
            target = entry * (1 - target_pct/100)
        st.success(f"{side} {sym} • Entrada: {entry:.8f} • Stop: {stop:.8f} • Alvo: {target:.8f}")
        st.write(f"Movimento até o stop: aproximadamente -{size*stop_pct/100:.2f} USDT; até o alvo: +{size*target_pct/100:.2f} USDT, antes de taxas, slippage e funding. Estimativa didática, não lucro garantido.")

st.caption("Dados públicos da Binance. Este protótipo não usa chave API, não envia ordens e não deve ser usado como sinal financeiro sem validação.")
time.sleep(0.1)
if st.button("🔄 Atualizar dados agora"):
    st.cache_data.clear()
    st.rerun()
