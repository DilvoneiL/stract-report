# Stract – Relatórios CSV (Flask)

Servidor Flask que consome a API pública da Stract e expõe relatórios **CSV** em tempo real.

## Requisitos

* Python 3.10+
* Dependências mínimas: `Flask`, `requests`

## Instalação

```bash
python3 -m venv .venv
# Windows (PowerShell): .venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

## Configuração (sem `.env`)

Defina as variáveis **no terminal** antes de executar:

```bash
export AUTH_TOKEN="token_de_exemplo"
export API_BASE="https://sidebar.stract.to/api"
# opcionais:
export HTTP_TIMEOUT=12
export RETRY_ATTEMPTS=2
```

> No Windows (PowerShell):
>
> ```powershell
> $env:AUTH_TOKEN="token_de_exemplo"
> $env:API_BASE="https://sidebar.stract.to/api"
> $env:HTTP_TIMEOUT="12"
> $env:RETRY_ATTEMPTS="2"
> ```

## Execução

### Desenvolvimento (Flask)

```bash
python wsgi.py
# o servidor sobe em http://localhost:5000
```

### (opcional, com gunicorn)

```bash
gunicorn wsgi:app --workers 2 --threads 2 --bind 0.0.0.0:5000 --access-logfile -
```

## Endpoints

* `/` – informações do candidato (nome, e-mail, LinkedIn).
* `/{plataforma}` – **todos os anúncios** da plataforma; colunas: campos de insights + `Account Name` (sem IDs).
* `/{plataforma}/resumo` – **1 linha por conta**; soma colunas numéricas; texto vazio nas não-numéricas; preserva `Account Name`.
* `/geral` – **todas as plataformas**; inclui `Platform` e `Account Name`; união de todos os campos; calcula **Cost per Click** quando faltar (`spend/clicks`).
* `/geral/resumo` – **1 linha por plataforma**; soma colunas numéricas; texto vazio nas não-numéricas; preserva `Platform`.
* `/healthz` – healthcheck simples (`{"status": "ok"}`).

> Plataformas típicas retornadas pela API: `meta_ads`, `ga4`, `tiktok_insights`.

## Exemplos (cURL)

```bash
# raiz
curl -s http://localhost:5000/

# geral (CSV)
curl -s http://localhost:5000/geral | head

# resumo geral (CSV)
curl -s http://localhost:5000/geral/resumo | head

# por plataforma
curl -s http://localhost:5000/meta_ads | head
curl -s http://localhost:5000/meta_ads/resumo | head
```

## Saídas esperadas (logs)

Ao acessar os endpoints, você deve ver respostas 200 no console, por exemplo:

```
127.0.0.1 - - [23/Jan/2026 13:10:10] "GET / HTTP/1.1" 200 -
127.0.0.1 - - [23/Jan/2026 13:10:20] "GET /geral HTTP/1.1" 200 -
127.0.0.1 - - [23/Jan/2026 13:11:35] "GET /geral/resumo HTTP/1.1" 200 -
127.0.0.1 - - [23/Jan/2026 13:12:11] "GET /meta_ads HTTP/1.1" 200 -
127.0.0.1 - - [23/Jan/2026 13:12:26] "GET /ga4 HTTP/1.1" 200 -
127.0.0.1 - - [23/Jan/2026 13:12:38] "GET /tiktok_insights HTTP/1.1" 200 -
127.0.0.1 - - [23/Jan/2026 13:12:53] "GET /meta_ads/resumo HTTP/1.1" 200 -
127.0.0.1 - - [23/Jan/2026 13:13:07] "GET /tiktok_insights/resumo HTTP/1.1" 200 -
127.0.0.1 - - [23/Jan/2026 13:13:34] "GET /ga4/resumo HTTP/1.1" 200 -
```

## Notas de implementação

* **Sem IDs** em nenhuma tabela: removemos chaves `id`, `*_id` e `* id` (sem afetar campos como `paid`).
* **CPC**: quando ausente, calculamos `Cost per Click = spend / clicks` (fica vazio se `clicks == 0`).
* **Paginação**: suportamos três formas:

  * `pagination.current/total`;
  * `next` (URL absoluta **ou** relativa), que é seguida **diretamente**;
  * parâmetro `page` (1..N) quando aplicável.
* **Resiliência**: `requests.Session` com **Retry** (429/5xx) e **timeout** padrão.
* **Segurança**: cabeçalhos básicos (`X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`)