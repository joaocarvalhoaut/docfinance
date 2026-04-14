"""
OCR Processor - Motor de extração de documentos financeiros.

Usa Tesseract OCR + heurísticas inteligentes para identificar e extrair
dados de cheques, notas fiscais, comprovantes e boletos.
"""

import re
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from datetime import datetime

logger = logging.getLogger("docfinance.ocr")

# ── Utilitários de validação ────────────────────────────────────────────────

def validate_cpf(cpf: str) -> bool:
    digits = re.sub(r'\D', '', cpf)
    if len(digits) != 11 or digits == digits[0] * 11:
        return False
    for i in range(9, 11):
        s = sum(int(digits[j]) * (i + 1 - j) for j in range(i))
        if int(digits[i]) != (s * 10 % 11) % 10:
            return False
    return True


def validate_cnpj(cnpj: str) -> bool:
    digits = re.sub(r'\D', '', cnpj)
    if len(digits) != 14:
        return False
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = sum(int(digits[i]) * weights1[i] for i in range(12))
    d1 = 0 if d1 % 11 < 2 else 11 - d1 % 11
    d2 = sum(int(digits[i]) * weights2[i] for i in range(13))
    d2 = 0 if d2 % 11 < 2 else 11 - d2 % 11
    return int(digits[12]) == d1 and int(digits[13]) == d2


def clean_value(text: str) -> Optional[float]:
    """Extrai valor numérico de string como 'R$ 1.250,75'."""
    text = re.sub(r'[^\d.,]', '', text)
    text = text.replace('.', '').replace(',', '.')
    try:
        return float(text)
    except ValueError:
        return None


def clean_date(text: str) -> Optional[str]:
    """Normaliza data para YYYY-MM-DD."""
    patterns = [
        r'(\d{2})[\/\-\.](\d{2})[\/\-\.](\d{4})',  # DD/MM/YYYY
        r'(\d{4})[\/\-\.](\d{2})[\/\-\.](\d{2})',  # YYYY-MM-DD
        r'(\d{2})[\/\-\.](\d{2})[\/\-\.](\d{2})',  # DD/MM/YY
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            g = m.groups()
            if len(g[0]) == 4:  # YYYY-MM-DD
                return f"{g[0]}-{g[1]}-{g[2]}"
            elif len(g[2]) == 4:  # DD/MM/YYYY
                return f"{g[2]}-{g[1]}-{g[0]}"
            else:  # DD/MM/YY → 20YY
                return f"20{g[2]}-{g[1]}-{g[0]}"
    return None


def clean_cnpj_cpf(text: str) -> str:
    """Remove formatação de CNPJ/CPF."""
    return re.sub(r'\D', '', text)


# ── Classificação de documentos ─────────────────────────────────────────────

def classify_document(text: str) -> Tuple[str, float]:
    """
    Classifica o tipo de documento usando heurísticas.
    Retorna (tipo, confiança).
    """
    text_lower = text.lower()
    scores = {
        "boleto": 0.0,
        "nota_fiscal": 0.0,
        "comprovante": 0.0,
        "cheque": 0.0,
    }
    
    # Boleto
    if re.search(r'\d{5}\.\d{5}\s\d{5}\.\d{6}\s\d{5}\.\d{6}\s\d\s\d{14}', text):
        scores["boleto"] += 0.9
    if any(k in text_lower for k in ["boleto", "linha digitável", "nosso número", "cedente", "sacado"]):
        scores["boleto"] += 0.3
    if re.search(r'\d{47,48}', text.replace(' ', '')):
        scores["boleto"] += 0.4
    
    # Nota Fiscal
    if any(k in text_lower for k in ["nota fiscal", "nf-e", "nfse", "danfe", "chave de acesso"]):
        scores["nota_fiscal"] += 0.7
    if re.search(r'cnpj[\s:]*\d{2}[\.\d]{14}', text_lower):
        scores["nota_fiscal"] += 0.2
    if any(k in text_lower for k in ["icms", "iss", "pis", "cofins", "cfop"]):
        scores["nota_fiscal"] += 0.3
    
    # Comprovante
    if any(k in text_lower for k in ["comprovante", "pix", "ted", "doc", "transferência"]):
        scores["comprovante"] += 0.6
    if any(k in text_lower for k in ["autenticação", "protocolo", "código de autenticação"]):
        scores["comprovante"] += 0.3
    if re.search(r'\d{2}[:/]\d{2}[:/]\d{2}', text):  # HH:MM:SS
        scores["comprovante"] += 0.15
    
    # Cheque
    if any(k in text_lower for k in ["cheque", "banco do brasil", "bradesco", "itaú", "caixa econômica"]):
        scores["cheque"] += 0.2
    if re.search(r'n[°o]?\s*cheque[\s:]*\d+', text_lower):
        scores["cheque"] += 0.5
    if re.search(r'pague por este cheque', text_lower):
        scores["cheque"] += 0.8
    if re.search(r'à\s+ordem\s+de', text_lower):
        scores["cheque"] += 0.4
    
    best = max(scores, key=scores.get)
    confidence = min(scores[best], 1.0)
    
    if confidence < 0.2:
        return "desconhecido", 0.1
    return best, confidence


# ── Extratores por tipo ─────────────────────────────────────────────────────

def extract_boleto(text: str) -> Dict[str, Any]:
    fields = {}
    low = text.lower()
    
    # Linha digitável
    ld = re.search(r'(\d{5}\.\d{5}\s?\d{5}\.\d{6}\s?\d{5}\.\d{6}\s?\d\s?\d{14})', text)
    fields["linha_digitavel"] = ld.group(1).strip() if ld else "N/A"
    
    # Valor
    val = re.search(r'valor\s*[:\-]?\s*(R\$\s*[\d\.]+,\d{2})', low)
    if not val:
        val = re.search(r'(R\$\s*[\d\.]+,\d{2})', text, re.IGNORECASE)
    if val:
        fields["valor"] = clean_value(val.group(1)) or "REVISAR"
    else:
        fields["valor"] = "N/A"
    
    # Data de vencimento
    venc = re.search(r'vencimento\s*[:\-]?\s*(\d{2}[\/\-\.]\d{2}[\/\-\.]\d{4})', low)
    fields["data_vencimento"] = clean_date(venc.group(1)) if venc else "N/A"
    
    # Beneficiário/Cedente
    benef = re.search(r'(?:beneficiário|cedente)\s*[:\-]?\s*(.+?)(?:\n|cnpj|$)', low)
    fields["beneficiario"] = benef.group(1).strip().title() if benef else "N/A"
    
    # Pagador/Sacado
    pag = re.search(r'(?:pagador|sacado)\s*[:\-]?\s*(.+?)(?:\n|cpf|cnpj|$)', low)
    fields["pagador"] = pag.group(1).strip().title() if pag else "N/A"
    
    # CNPJ/CPF
    cnpj = re.search(r'(?:cnpj|cpf)[:\s]*(\d{2}\.?\d{3}\.?\d{3}[\/\-]?\d{4}[\/\-]?\d{2}|\d{3}\.?\d{3}\.?\d{3}[\/\-]?\d{2})', low)
    if cnpj:
        raw = clean_cnpj_cpf(cnpj.group(1))
        fields["cnpj_cpf"] = raw if (validate_cnpj(raw) or validate_cpf(raw)) else "REVISAR"
    else:
        fields["cnpj_cpf"] = "N/A"
    
    # Banco
    bancos = {
        "001": "Banco do Brasil", "033": "Santander", "104": "Caixa Econômica",
        "237": "Bradesco", "341": "Itaú", "356": "Real", "399": "HSBC",
        "422": "Safra", "745": "Citibank", "077": "Banco Inter", "260": "Nu Pagamentos"
    }
    banco_found = "N/A"
    for cod, nome in bancos.items():
        if nome.lower() in low or cod in text[:20]:
            banco_found = nome
            break
    fields["banco"] = banco_found
    
    # Nosso número
    nn = re.search(r'nosso\s*n[°o]?\s*[:\-]?\s*([\d\/\-]+)', low)
    fields["nosso_numero"] = nn.group(1).strip() if nn else "N/A"
    
    return fields


def extract_nota_fiscal(text: str) -> Dict[str, Any]:
    fields = {}
    low = text.lower()
    
    # Número da nota
    nf = re.search(r'n[°oa]?\s*(?:da\s+nota|nota\s+fiscal)?[:\s]*(\d+)', low)
    fields["numero_nota"] = nf.group(1) if nf else "N/A"
    
    # CNPJ emissor
    cnpj = re.search(r'cnpj[:\s]*(\d{2}\.?\d{3}\.?\d{3}\/\d{4}-\d{2})', low)
    if cnpj:
        raw = clean_cnpj_cpf(cnpj.group(1))
        fields["cnpj_emissor"] = raw if validate_cnpj(raw) else "REVISAR"
    else:
        fields["cnpj_emissor"] = "N/A"
    
    # Nome empresa
    empresa = re.search(r'(?:razão social|empresa|emitente)\s*[:\-]?\s*(.+?)(?:\n|cnpj|$)', low)
    fields["nome_empresa"] = empresa.group(1).strip().title() if empresa else "N/A"
    
    # Data emissão
    data = re.search(r'(?:data\s+(?:de\s+)?emiss[aã]o|emiss[aã]o)\s*[:\-]?\s*(\d{2}[\/\-\.]\d{2}[\/\-\.]\d{4})', low)
    fields["data_emissao"] = clean_date(data.group(1)) if data else "N/A"
    
    # Valor total
    total = re.search(r'(?:valor\s+total|total\s+nota|total\s+geral)\s*[:\-]?\s*(R\$\s*[\d\.]+,\d{2})', low)
    if not total:
        total = re.search(r'total\s*[:\-]?\s*(R\$\s*[\d\.]+,\d{2})', low)
    fields["valor_total"] = clean_value(total.group(1)) if total else "N/A"
    
    # Impostos
    icms = re.search(r'icms\s*[:\-]?\s*(R\$\s*[\d\.]+,\d{2}|\d+[,\.]\d{2})', low)
    fields["icms"] = clean_value(icms.group(1)) if icms else "N/A"
    
    iss = re.search(r'iss\s*[:\-]?\s*(R\$\s*[\d\.]+,\d{2}|\d+[,\.]\d{2})', low)
    fields["iss"] = clean_value(iss.group(1)) if iss else "N/A"
    
    return fields


def extract_comprovante(text: str) -> Dict[str, Any]:
    fields = {}
    low = text.lower()
    
    # Tipo
    for t in ["pix", "ted", "doc", "transferência", "depósito", "pagamento"]:
        if t in low:
            fields["tipo"] = t.upper()
            break
    else:
        fields["tipo"] = "N/A"
    
    # Valor
    val = re.search(r'valor\s*[:\-]?\s*(R\$\s*[\d\.]+,\d{2})', low)
    if not val:
        val = re.search(r'(R\$\s*[\d\.]+,\d{2})', text, re.IGNORECASE)
    fields["valor"] = clean_value(val.group(1)) if val else "N/A"
    
    # Data e hora
    dt = re.search(r'(\d{2}[\/\-\.]\d{2}[\/\-\.]\d{4})\s+(?:às?\s+)?(\d{2}[:\-]\d{2})', text)
    if dt:
        fields["data"] = clean_date(dt.group(1)) or "N/A"
        fields["hora"] = dt.group(2)
    else:
        d = re.search(r'\d{2}[\/\-\.]\d{2}[\/\-\.]\d{4}', text)
        fields["data"] = clean_date(d.group(0)) if d else "N/A"
        fields["hora"] = "N/A"
    
    # Pagador
    pag = re.search(r'(?:pagador|origem|de|remetente)\s*[:\-]?\s*(.+?)(?:\n|cpf|cnpj|$)', low)
    fields["pagador"] = pag.group(1).strip().title() if pag else "N/A"
    
    # Recebedor
    rec = re.search(r'(?:recebedor|destino|para|beneficiário)\s*[:\-]?\s*(.+?)(?:\n|cpf|cnpj|$)', low)
    fields["recebedor"] = rec.group(1).strip().title() if rec else "N/A"
    
    # Banco
    banco = re.search(r'(?:banco|instituição)\s*[:\-]?\s*(.+?)(?:\n|agência|$)', low)
    fields["banco"] = banco.group(1).strip().title() if banco else "N/A"
    
    # Código de autenticação
    auth = re.search(r'(?:autenticação|protocolo|código)\s*[:\-]?\s*([A-Z0-9\-\.]+)', text, re.IGNORECASE)
    fields["codigo_autenticacao"] = auth.group(1) if auth else "N/A"
    
    return fields


def extract_cheque(text: str) -> Dict[str, Any]:
    fields = {}
    low = text.lower()
    
    # Beneficiário (após "pague a" ou "à ordem de")
    benef = re.search(r'(?:pague a|à ordem de|ao portador de)[:\s]*(.+?)(?:\n|a quantia|r\$|$)', low)
    fields["beneficiario"] = benef.group(1).strip().title() if benef else "N/A"
    
    # Valor numérico
    val = re.search(r'(R\$\s*[\d\.]+,\d{2})', text, re.IGNORECASE)
    fields["valor"] = clean_value(val.group(1)) if val else "N/A"
    
    # Valor por extenso
    ext = re.search(r'(?:a quantia de|importância de)[:\s]*(.+?)(?:\n|reais|r\$|$)', low)
    fields["valor_extenso"] = ext.group(1).strip().title() if ext else "N/A"
    
    # Data
    d = re.search(r'(\d{2}[\/\-\.]\d{2}[\/\-\.]\d{4})', text)
    fields["data"] = clean_date(d.group(1)) if d else "N/A"
    
    # Banco
    bancos_list = ["Banco do Brasil", "Bradesco", "Itaú", "Caixa Econômica", "Santander", "Safra"]
    banco_found = "N/A"
    for b in bancos_list:
        if b.lower() in low:
            banco_found = b
            break
    fields["banco"] = banco_found
    
    # Número do cheque
    num = re.search(r'(?:n[°o]?\s*cheque|cheque\s*n[°o]?)\s*[:\-]?\s*(\d+)', low)
    fields["numero_cheque"] = num.group(1) if num else "N/A"
    
    # Cidade
    cidade = re.search(r'([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú]?[a-zà-ú]+)*)\s*,\s*\d{2}', text)
    fields["cidade"] = cidade.group(1) if cidade else "N/A"
    
    return fields


# ── OCR Principal ────────────────────────────────────────────────────────────

async def run_tesseract(filepath: str) -> Tuple[str, float]:
    """
    Executa OCR com Tesseract.
    Retorna (texto, confiança média).
    """
    try:
        import pytesseract
        from PIL import Image
        import pdf2image
        
        path = Path(filepath)
        
        if path.suffix.lower() == ".pdf":
            # Converter PDF para imagens
            pages = pdf2image.convert_from_path(str(path), dpi=300)
            texts = []
            for page in pages:
                data = pytesseract.image_to_data(
                    page, lang="por", output_type=pytesseract.Output.DICT
                )
                page_text = " ".join(w for w in data["text"] if w.strip())
                texts.append(page_text)
            full_text = "\n".join(texts)
            
            # Calcular confiança média
            all_conf = pytesseract.image_to_data(
                pages[0], lang="por", output_type=pytesseract.Output.DICT
            )
            confs = [c for c in all_conf["conf"] if c != -1]
            confidence = sum(confs) / len(confs) / 100 if confs else 0.5
            
        else:
            img = Image.open(filepath)
            data = pytesseract.image_to_data(img, lang="por", output_type=pytesseract.Output.DICT)
            full_text = " ".join(w for w in data["text"] if w.strip())
            
            confs = [c for c in data["conf"] if c != -1]
            confidence = sum(confs) / len(confs) / 100 if confs else 0.5
        
        return full_text, confidence
    
    except ImportError:
        logger.warning("Tesseract não disponível. Usando modo demonstração.")
        return _demo_text(filepath), 0.75
    
    except Exception as e:
        logger.error(f"Erro no OCR: {e}")
        return "", 0.0


def _demo_text(filepath: str) -> str:
    """Texto de demonstração quando Tesseract não está disponível."""
    filename = Path(filepath).name.lower()
    if "boleto" in filename:
        return """
        BOLETO BANCÁRIO - Banco do Brasil S.A.
        Linha digitável: 00190.50000 01200.069301 51600.700002 1 89770000102500
        Beneficiário: Empresa Demo Ltda
        CNPJ: 12.345.678/0001-95
        Sacado: João da Silva
        CPF: 123.456.789-09
        Valor: R$ 1.025,00
        Vencimento: 15/08/2024
        Nosso Número: 123456789
        """
    elif "nota" in filename or "nf" in filename:
        return """
        NOTA FISCAL ELETRÔNICA
        Número: 000123
        Data de Emissão: 10/07/2024
        Razão Social: Comercial Demo S.A.
        CNPJ: 12.345.678/0001-95
        Valor Total: R$ 2.500,00
        ICMS: R$ 450,00
        """
    elif "pix" in filename or "comprovante" in filename:
        return """
        COMPROVANTE DE TRANSFERÊNCIA PIX
        Tipo: PIX
        Valor: R$ 350,00
        Data: 12/07/2024 às 14:32
        Pagador: Maria Oliveira
        CPF: 987.654.321-00
        Recebedor: Pedro Santos
        Banco: Nu Pagamentos S.A.
        Código de Autenticação: PIX-2024071214325001
        """
    else:
        return """
        CHEQUE Nº 000456
        Banco do Brasil S.A. - Agência 1234-5
        Pague por este cheque a João Carlos Silva
        A quantia de: Mil e Quinhentos Reais
        R$ 1.500,00
        São Paulo, 08/07/2024
        """


async def process_document(filepath: str) -> Dict[str, Any]:
    """
    Pipeline completo de processamento de um documento.
    """
    logger.info(f"Iniciando OCR: {Path(filepath).name}")
    
    # 1. OCR
    loop = asyncio.get_event_loop()
    raw_text, ocr_confidence = await loop.run_in_executor(None, lambda: asyncio.run(run_tesseract(filepath)))
    
    # Se run_in_executor com coroutine não funcionar, fallback
    if not raw_text:
        raw_text, ocr_confidence = await run_tesseract(filepath)
    
    # 2. Classificar
    doc_type, classification_confidence = classify_document(raw_text)
    overall_confidence = (ocr_confidence + classification_confidence) / 2
    
    logger.info(f"Tipo identificado: {doc_type} (confiança: {overall_confidence:.2f})")
    
    # 3. Extrair campos
    extractors = {
        "boleto": extract_boleto,
        "nota_fiscal": extract_nota_fiscal,
        "comprovante": extract_comprovante,
        "cheque": extract_cheque,
        "desconhecido": lambda t: {"texto_bruto": t[:500]}
    }
    
    campos = extractors[doc_type](raw_text)
    
    # 4. Marcar campos com baixa confiança para revisão
    campos_revisao = []
    if overall_confidence < 0.6:
        campos_revisao = [k for k, v in campos.items() if v not in ("N/A", None) and v != "REVISAR"]
    
    # Marcar campos com "REVISAR" que já estão assim
    campos_revisao += [k for k, v in campos.items() if v == "REVISAR"]
    
    # 5. Padronizar
    campos["arquivo"] = Path(filepath).name
    campos["tipo_documento"] = doc_type
    campos["data_processamento"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    campos["confianca_ocr"] = f"{overall_confidence:.0%}"
    
    return {
        "tipo_documento": doc_type,
        "confianca": overall_confidence,
        "campos": campos,
        "campos_revisao": campos_revisao,
        "raw_text_preview": raw_text[:300] if raw_text else ""
    }
