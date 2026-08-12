"""
Cliente NFeDistribuicaoDFe - Web Service da SEFAZ
Regulamentado pela Nota Tecnica 2014.002
"""

import os
import base64
import gzip
import tempfile
import logging
from lxml import etree
import requests

logger = logging.getLogger(__name__)

class NFeDistribuicaoDFe:
    """Cliente para o Web Service NFeDistribuicaoDFe da SEFAZ"""

    NS_SOAP = "http://www.w3.org/2003/05/soap-envelope"
    NS_NFE = "http://www.portalfiscal.inf.br/nfe"
    NS_WSDL = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe"

    STATUS_OK = "138"
    STATUS_SEM_DOCUMENTOS = "137"
    STATUS_BLOQUEIO = "656"

    ENDPOINTS = {
        1: "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
        2: "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
    }

    MENSAGENS_STATUS = {
        "138": "Documento(s) localizado(s)",
        "137": "Nenhum documento localizado",
        "656": "Consumo Indevido (bloqueado por 1 hora)",
        "589": "NSU informado superior ao maior NSU disponivel",
        "217": "NF-e inexistente para a chave informada",
        "632": "Solicitacao fora do prazo (90 dias)",
        "640": "CNPJ/CPF sem permissao para consultar a NF-e",
        "641": "NF-e indisponivel para o emitente",
        "252": "Ambiente divergente",
        "214": "Erro de validacao: tamanho do XML excede 10KB",
    }

    def __init__(self, tp_amb, cuf_autor, cnpj, cert_pem_b64, key_pem_b64):
        self.tp_amb = int(tp_amb)
        self.cuf_autor = int(cuf_autor)
        self.cnpj = cnpj.strip()
        self.endpoint = self.ENDPOINTS[self.tp_amb]

        if len(self.cnpj) != 14:
            raise ValueError(f"CNPJ invalido (precisa 14 digitos): {self.cnpj}")

        if not cert_pem_b64 or not key_pem_b64:
            raise ValueError("Certificado ou chave privada nao fornecidos (base64)")

        cert_pem_content = base64.b64decode(cert_pem_b64).decode("utf-8")
        key_pem_content = base64.b64decode(key_pem_b64).decode("utf-8")

        self._cert_file = tempfile.NamedTemporaryFile(
            suffix=".pem", delete=False, mode="w"
        )
        self._cert_file.write(cert_pem_content)
        self._cert_file.close()

        self._key_file = tempfile.NamedTemporaryFile(
            suffix=".pem", delete=False, mode="w"
        )
        self._key_file.write(key_pem_content)
        self._key_file.close()

        self.session = requests.Session()
        self.session.cert = (self._cert_file.name, self._key_file.name)
        self.session.headers.update({
            "Content-Type": "application/soap+xml; charset=utf-8",
        })

    def __del__(self):
        for attr in ["_cert_file", "_key_file"]:
            f = getattr(self, attr, None)
            if f and os.path.exists(f.name):
                try:
                    os.unlink(f.name)
                except Exception:
                    pass

    def _montar_xml_chave(self, chave_acesso: str) -> str:
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<soap:Envelope xmlns:soap="{self.NS_SOAP}"\n'
            f'               xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
            f'               xmlns:xsd="http://www.w3.org/2001/XMLSchema">\n'
            f'  <soap:Body>\n'
            f'    <nfeDistDFeInteresse xmlns="{self.NS_WSDL}">\n'
            f'      <nfeDadosMsg>\n'
            f'        <distDFeInt versao="1.01" xmlns="{self.NS_NFE}">\n'
            f'          <tpAmb>{self.tp_amb}</tpAmb>\n'
            f'          <cUFAutor>{self.cuf_autor}</cUFAutor>\n'
            f'          <CNPJ>{self.cnpj}</CNPJ>\n'
            f'          <consChNFe>\n'
            f'            <chNFe>{chave_acesso}</chNFe>\n'
            f'          </consChNFe>\n'
            f'        </distDFeInt>\n'
            f'      </nfeDadosMsg>\n'
            f'    </nfeDistDFeInteresse>\n'
            f'  </soap:Body>\n'
            f'</soap:Envelope>'
        )

    def _enviar(self, xml_soap: str) -> etree._Element:
        try:
            resp = self.session.post(
                self.endpoint,
                data=xml_soap.encode("utf-8"),
                timeout=90,
            )
            resp.raise_for_status()
            return etree.fromstring(resp.content)
        except requests.exceptions.SSLError as e:
            raise Exception(f"Erro SSL/Certificado digital: {e}")
        except requests.exceptions.Timeout:
            raise Exception("Timeout: SEFAZ nao respondeu em 90 segundos")
        except requests.exceptions.ConnectionError as e:
            raise Exception(f"Erro de conexao com a SEFAZ: {e}")
        except requests.exceptions.HTTPError as e:
            raise Exception(f"Erro HTTP {resp.status_code}: {e}")
        except etree.XMLSyntaxError as e:
            raise Exception(f"Erro ao parsear XML de resposta: {e}")

    def _extrair(self, tree: etree._Element) -> tuple:
        nsmap = {"soap": self.NS_SOAP, "nfe": self.NS_NFE}

        cStat_el = tree.find(".//nfe:cStat", nsmap)
        xMot_el = tree.find(".//nfe:xMotivo", nsmap)

        cStat = cStat_el.text if cStat_el is not None else "???"
        xMotivo = xMot_el.text if xMot_el is not None else ""

        documentos = []
        for doc in tree.findall(".//nfe:docZip", nsmap):
            nsu = doc.get("NSU", "")
            schema = doc.get("schema", "")
            try:
                conteudo_gzip = base64.b64decode(doc.text)
                xml_descompactado = gzip.decompress(conteudo_gzip).decode("utf-8")
                documentos.append({
                    "nsu": nsu,
                    "schema": schema,
                    "xml": xml_descompactado,
                })
            except Exception as e:
                logger.warning(f"Erro ao descompactar NSU {nsu}: {e}")

        return cStat, xMotivo, documentos

    def consultar_por_chave(self, chave: str) -> dict:
        chave = chave.strip()

        if len(chave) != 44 or not chave.isdigit():
            return {
                "sucesso": False,
                "chave": chave,
                "cStat": "",
                "xMotivo": "Chave invalida (precisa ter 44 digitos numericos)",
                "documentos": [],
                "erro": "Chave invalida",
            }

        xml_soap = self._montar_xml_chave(chave)
        tree = self._enviar(xml_soap)
        cStat, xMotivo, documentos = self._extrair(tree)

        return {
            "sucesso": cStat == self.STATUS_OK,
            "chave": chave,
            "cStat": cStat,
            "xMotivo": xMotivo,
            "documentos": documentos,
            "erro": None,
        }