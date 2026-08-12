"""
Aplicacao Web - Download de XML via NFeDistribuicaoDFe
Deploy: Render.com
"""

import os
import io
import zipfile
import time
import logging
from datetime import datetime

from flask import Flask, request, render_template, jsonify, send_file

from nfe_client import NFeDistribuicaoDFe

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

def get_env_or_die(key):
    val = os.environ.get(key, "").strip()
    if not val:
        raise RuntimeError(
            f"Variavel de ambiente '{key}' nao definida. "
            f"Configure no Render Dashboard > Environment."
        )
    return val

def criar_cliente() -> NFeDistribuicaoDFe:
    return NFeDistribuicaoDFe(
        tp_amb=get_env_or_die("NFE_AMBIENTE"),
        cuf_autor=get_env_or_die("NFE_CUF_AUTOR"),
        cnpj=get_env_or_die("NFE_CNPJ"),
        cert_pem_b64=get_env_or_die("NFE_CERT_PEM_B64"),
        key_pem_b64=get_env_or_die("NFE_KEY_PEM_B64"),
    )

def extrair_chaves(texto: str) -> list:
    chaves = []
    for linha in texto.splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and len(linha) == 44 and linha.isdigit():
            chaves.append(linha)
    return chaves

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/baixar", methods=["POST"])
def baixar():
    chaves_text = ""

    if "arquivo" in request.files:
        file = request.files["arquivo"]
        if file and file.filename:
            chaves_text = file.read().decode("utf-8")
    elif "chaves" in request.form:
        chaves_text = request.form.get("chaves", "")

    chaves = extrair_chaves(chaves_text)

    if not chaves:
        return jsonify({"erro": "Nenhuma chave valida encontrada (44 digitos)."}), 400

    if len(chaves) > 100:
        return jsonify({
            "erro": f"Maximo de 100 chaves por requisicao. Voce enviou {len(chaves)}."
        }), 400

    try:
        cliente = criar_cliente()
    except (RuntimeError, ValueError) as e:
        logger.error(f"Erro ao criar cliente: {e}")
        return jsonify({"erro": str(e)}), 500

    resultados = []
    xmls_para_zip = []
    bloqueado = False

    for i, chave in enumerate(chaves):
        logger.info(f"[{i+1}/{len(chaves)}] Consultando chave: {chave}")

        try:
            resultado = cliente.consultar_por_chave(chave)

            if resultado.get("erro"):
                resultados.append({
                    "chave": chave,
                    "status": "ERRO",
                    "cStat": "",
                    "xMotivo": resultado["erro"],
                    "documentos": 0,
                })

            elif resultado["sucesso"]:
                docs = resultado["documentos"]
                for doc in docs:
                    if "procNFe" in doc["schema"]:
                        nome = f"{chave}.xml"
                    elif "resNFe" in doc["schema"]:
                        nome = f"resumo_{chave}.xml"
                    else:
                        nome = f"evento_{doc['nsu']}.xml"

                    xmls_para_zip.append({
                        "nome": nome,
                        "conteudo": doc["xml"],
                    })

                resultados.append({
                    "chave": chave,
                    "status": "OK",
                    "cStat": resultado["cStat"],
                    "xMotivo": resultado["xMotivo"],
                    "documentos": len(docs),
                })

            else:
                if resultado["cStat"] == "656":
                    resultados.append({
                        "chave": chave,
                        "status": "BLOQUEIO",
                        "cStat": "656",
                        "xMotivo": "Consumo indevido - aguarde 1 hora completa",
                        "documentos": 0,
                    })
                    bloqueado = True
                    break
                else:
                    resultados.append({
                        "chave": chave,
                        "status": "FALHA",
                        "cStat": resultado["cStat"],
                        "xMotivo": resultado["xMotivo"],
                        "documentos": 0,
                    })

        except Exception as e:
            logger.error(f"Erro ao consultar chave {chave}: {e}", exc_info=True)
            resultados.append({
                "chave": chave,
                "status": "ERRO",
                "cStat": "",
                "xMotivo": str(e),
                "documentos": 0,
            })

        if i < len(chaves) - 1 and not bloqueado:
            time.sleep(3)

    if not xmls_para_zip:
        return jsonify({
            "resultados": resultados,
            "total_xmls": 0,
            "total_chaves": len(chaves),
            "bloqueado": bloqueado,
            "mensagem": "Nenhum XML foi baixado. Verifique os resultados abaixo."
        })

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in xmls_para_zip:
            zf.writestr(item["nome"], item["conteudo"])

        log_lines = [
            "=" * 60,
            "  LOG DE DOWNLOAD - NFeDistribuicaoDFe",
            "=" * 60,
            f"  Data:           {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
            f"  Total de chaves: {len(chaves)}",
            f"  XMLs baixados:   {len(xmls_para_zip)}",
            f"  Bloqueado:       {'SIM' if bloqueado else 'NAO'}",
            "",
            "-" * 60,
            "  DETALHAMENTO POR CHAVE",
            "-" * 60,
            "",
        ]
        for r in resultados:
            log_lines.append(
                f"  [{r['status']:8s}] {r['chave']} | "
                f"cStat={r.get('cStat', ''):4s} | "
                f"{r['xMotivo']} | "
                f"{r['documentos']} doc(s)"
            )

        log_lines.extend(["", "=" * 60])
        zf.writestr("log.txt", "\n".join(log_lines))

    zip_buffer.seek(0)

    nome_zip = f"nfe_xmls_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

    logger.info(f"Download concluido: {len(xmls_para_zip)} XMLs em {nome_zip}")

    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=nome_zip,
    )

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
    }), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)