# RADAR AI — First Leg (protótipo Replit)

## O que faz
- Descobre contratos perpétuos USDT elegíveis da Binance Futures.
- Exibe os contratos de maior volume dentro do limite selecionado (20/50/100).
- Consulta preço, variação 24h, volume, Open Interest atual e funding.
- Consulta o order book sob demanda com profundidade até 100 níveis.
- Calcula um desequilíbrio simples entre notional de bids e asks.
- Permite calcular stop/alvo para operações fictícias.

## Limitações importantes
Este é o primeiro protótipo, não o radar completo do Bulltard:
- Não captura o order book de todos os contratos continuamente.
- Não calcula variação histórica do OI nem fluxo de trades executados.
- O score é heurístico, baseado em variação de 24h, volume e disponibilidade do OI; não é um modelo preditivo e pode não produzir score acima do limite.
- O livro REST é um instantâneo e não uma visão sincronizada do fluxo.
- Não envia ordens nem exige chave API.
- Replit gratuito pode ter limites de uso/execução e não deve ser tratado como servidor garantido 24/7.

## Como executar
1. Crie um Repl Python no Replit.
2. Envie `main.py` e `requirements.txt` para o projeto (ou importe o ZIP).
3. Clique Run. Se pedir comando, use `streamlit run main.py --server.address 0.0.0.0 --server.port 3000`.
4. Abra a Webview do Replit.
