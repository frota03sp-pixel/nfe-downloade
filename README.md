# 📎 NFe Downloader

Sistema web para download de XMLs de NF-e via servico **NFeDistribuicaoDFe** da SEFAZ (NT 2014.002).

## 🚀 Deploy no Render

### Passo 1: Preparar o certificado
```bash
openssl pkcs12 -in certificado.pfx -out cert.pem -clcerts -nokeys
openssl pkcs12 -in certificado.pfx -out key.pem -nocerts -nodes

# Linux/Mac:
base64 -w 0 cert.pem > cert_b64.txt
base64 -w 0 key.pem > key_b64.txt

# Windows (PowerShell):
[Convert]::ToBase64String([IO.File]::ReadAllBytes("cert.pem")) | Out-File cert_b64.txt
[Convert]::ToBase64String([IO.File]::ReadAllBytes("key.pem")) | Out-File key_b64.txt
```

### Passo 2: Subir para o GitHub

Crie um repositorio e suba todos os arquivos.

### Passo 3: Configurar no Render

1. Acesse render.com → New → Web Service
2. Conecte seu repositorio
3. Runtime: Python 3
4. Build: `pip install -r requirements.txt`
5. Start: `gunicorn app:app --workers 2 --timeout 120`
6. Health Check: `/health`

### Passo 4: Variaveis de Ambiente

| Variavel | Descricao |
|---|---|
| `NFE_AMBIENTE` | `1` (Producao) ou `2` (Homologacao) |
| `NFE_CUF_AUTOR` | Codigo IBGE da UF (ex: 35 = SP) |
| `NFE_CNPJ` | CNPJ do certificado (14 digitos) |
| `NFE_CERT_PEM_B64` | Conteudo do cert_b64.txt (base64) |
| `NFE_KEY_PEM_B64` | Conteudo do key_b64.txt (base64) |

## 📖 Como Usar

1. Acesse a URL do app
2. Cole as chaves de acesso ou faca upload de .txt
3. Clique em Baixar XMLs
4. O sistema retorna um .zip com os XMLs + log

## ⚠️ Limites da SEFAZ

- 20 consultas por hora por chave
- Pausa de 3s entre consultas
- Documentos disponiveis por 90 dias
- Max 50 documentos por resposta