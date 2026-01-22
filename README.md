# Stract – Relatórios CSV (Flask)

Servidor Flask que consome a API pública da Stract e expõe relatórios **CSV** em tempo real.

## Requisitos

* Python 3.10+
* Dependências mínimas: `Flask`, `requests`

## Instalação

```bash
python3 -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

## Configuração


```bash
export AUTH_TOKEN="SelecaoStract2026"
export API_BASE="https://sidebar.stract.to/api"
```

## Execução

```bash
python3 app.py
# o servidor sobe em http://localhost:5000
```

## Endpoints

* `/` – informações do candidato (nome, e-mail, LinkedIn)
* `/{plataforma}` – **todos os anúncios** da plataforma; colunas: campos de insights + `Account Name` (sem IDs)
* `/{plataforma}/resumo` – **1 linha por conta**; soma colunas numéricas; textos vazios; preserva `Account Name`
* `/geral` – **todas as plataformas**; inclui `Platform` e `Account Name`; união de todos os campos; calcula **Cost per Click** quando faltar (spend/clicks)
* `/geral/resumo` – **1 linha por plataforma**; soma colunas numéricas; textos vazios; preserva `Platform`

> Plataformas típicas retornadas pela API: `meta_ads`, `ga4`, `tiktok_insights`.

## Exemplos (cURL)

```bash
# raiz
curl -s http://localhost:5000/

# geral (CSV)
curl -s http://localhost:5000/geral | head

# resumo geral
curl -s http://localhost:5000/geral/resumo | head

# por plataforma
curl -s http://localhost:5000/meta_ads | head
curl -s http://localhost:5000/meta_ads/resumo | head
```

## Notas de implementação

* **Sem IDs** em nenhuma tabela: removemos `id`, `*_id` e `* id` (sem afetar campos como `paid`).
* **CPC**: quando ausente, calculamos `Cost per Click = spend / clicks` (fica vazio se `clicks == 0`).
* **Paginação**: suportamos `pagination.current/total`, `next` (URL absoluta/relativa) e **param `page`**; se a API não indicar paginação, paramos após a primeira página (evita loop).
* **Timeout e retries** leves em chamadas HTTP.
