import re
import logging
import pytesseract
from pathlib import Path
from PIL import Image, ImageFilter, ImageEnhance
from config import settings

if settings.TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

logger = logging.getLogger(__name__)

def _ocr_image(img):
    try:
        img = img.convert("L")
        img = img.filter(ImageFilter.SHARPEN)
        img = ImageEnhance.Contrast(img).enhance(2.0)
        text = pytesseract.image_to_string(img, lang="por", config="--psm 6 --oem 1")
        data = pytesseract.image_to_data(img, lang="por", output_type=pytesseract.Output.DICT, config="--psm 6 --oem 1")
        confs = [int(c) for c in data["conf"] if str(c).lstrip("-").isdigit() and int(c) > 0]
        confidence = (sum(confs) / len(confs) / 100) if confs else 0.5
        return text, confidence
    except Exception as e:
        logger.error(f"Erro OCR: {e}")
        return "", 0.0

def extract_text_from_file(file_path):
    path = Path(file_path)
    if path.suffix.lower() == ".pdf":
        try:
            from pdf2image import convert_from_path
            pages = convert_from_path(str(file_path), dpi=150)
            texts, confs = [], []
            for page in pages:
                t, c = _ocr_image(page)
                texts.append(t)
                confs.append(c)
            return "\n".join(texts), (sum(confs)/len(confs) if confs else 0.0)
        except Exception as e:
            logger.error(f"Erro PDF: {e}")
            return "", 0.0
    else:
        try:
            return _ocr_image(Image.open(str(file_path)))
        except Exception as e:
            logger.error(f"Erro imagem: {e}")
            return "", 0.0

def _cnpjs(text):
    found = re.findall(r'\d{2}[\.\s]?\d{3}[\.\s]?\d{3}[/\s]?\d{4}[-\s]?\d{2}', text)
    return list(set([re.sub(r'\D','',c) for c in found if len(re.sub(r'\D','',c)) == 14]))

def _valores(text):
    found = re.findall(r'R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})', text)
    result = []
    for v in found:
        try:
            result.append(float(v.replace('.','').replace(',','.')))
        except:
            pass
    return sorted(list(set(result)), reverse=True)

def _datas(text):
    result = []
    for m in re.finditer(r'(\d{2})[/\-](\d{2})[/\-](\d{2,4})', text):
        d, mes, ano = m.group(1), m.group(2), m.group(3)
        if len(ano) == 2:
            ano = "20" + ano
        try:
            if 1 <= int(mes) <= 12 and 1 <= int(d) <= 31:
                result.append(f"{ano}-{mes}-{d}")
        except:
            pass
    return list(dict.fromkeys(result))

def _telefones(text):
    return list(set(re.findall(r'\(?\d{2}\)?\s?\d{4,5}[-\s]?\d{4}', text)))

def _emails(text):
    return list(set(re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)))

def _limpar(texto, tamanho=80):
    return re.sub(r'\s+', ' ', texto).strip()[:tamanho]

def classify_document(text):
    t = text.upper()
    if re.search(r'DANFE|NOTA FISCAL ELETR|DOCUMENTO AUXILIAR DA NOTA', t):
        return "nota_fiscal"
    if re.search(r'\d{5}\.\d{5}\s+\d{5}\.\d{6}', text):
        return "boleto"
    if re.search(r'VENCIMENTO|LINHA DIGIT', t) and re.search(r'PAGADOR|BENEFICI', t):
        return "boleto"
    if re.search(r'\bPIX\b|CHAVE PIX|TRANSACAO PIX', t):
        return "comprovante_pix"
    if re.search(r'\bTED\b|TRANSFER.*ELETR', t):
        return "comprovante_ted"
    if re.search(r'RECIBO|RECEBEMOS|ASSINATURA DO RECEBEDOR', t):
        return "recibo"
    if re.search(r'COMPROVANTE', t):
        return "comprovante"
    if re.search(r'CHEQUE|PAGUE|AO PORTADOR', t):
        return "cheque"
    return "desconhecido"

def _split_blocos(text, doc_type):
    import re, unicodedata

    if doc_type == "nota_fiscal":
        posicoes = [m.start() for m in re.finditer(r"DANFE", text, re.IGNORECASE)]
        if len(posicoes) <= 1:
            return [text]
        blocos = []
        if posicoes[0] > 100:
            capa = text[:posicoes[0]].strip()
            if len(capa) > 50:
                blocos.append(capa)
        for i, pos in enumerate(posicoes):
            fim = posicoes[i+1] if i+1 < len(posicoes) else len(text)
            bloco = text[pos:fim].strip()
            # Truncar no inicio da proxima NF
            for marcador in ["DATA DE RECEBIMENTO", "NF?"]:
                idx_marc = bloco.find(marcador)
                if idx_marc > 300:
                    bloco = bloco[:idx_marc].strip()
                    break
            if len(bloco) > 100:
                blocos.append(bloco)
        return blocos if blocos else [text]
    elif doc_type == "recibo":
        partes = re.split(r"(?=Recibo\s+\d+)", text, flags=re.IGNORECASE)
    elif doc_type == "boleto":
        partes = re.split(r"(?=\d{5}\.\d{5}\s+\d{5}\.\d{6})", text)
    elif doc_type in ("comprovante_pix","comprovante_ted","comprovante"):
        partes = re.split(r"(?=Comprovante|COMPROVANTE)", text, flags=re.IGNORECASE)
    elif doc_type == "cheque":
        partes = re.split(r"(?=PAGUE|CHEQUE N)", text, flags=re.IGNORECASE)
    else:
        return [text]

    partes = [p.strip() for p in partes if len(p.strip()) > 80]
    return partes if len(partes) > 1 else [text]


def extract_nota(bloco, conf):
    import re
    data = {}

    # CHAVE DE ACESSO
    texto_sem_esp = re.sub(r"\s", "", bloco)
    m_chave = re.search(r"\d{44}", texto_sem_esp)
    if m_chave:
        data["chave_acesso"] = m_chave.group(0)

    # NUMERO DA NOTA via chave
    if data.get("chave_acesso"):
        num_raw = data["chave_acesso"][28:34].lstrip("0")
        if num_raw and num_raw.isdigit() and len(num_raw) >= 3:
            data["numero_nota"] = num_raw

    # SERIE
    m = re.search(r"S[EE]RIE[:\s]*(\d+)", bloco, re.IGNORECASE)
    if m:
        data["serie"] = m.group(1)

    # CNPJs reais
    chave = data.get("chave_acesso", "")
    cnpjs_fmt = re.findall(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", bloco)
    cnpjs_validos = []
    for c in cnpjs_fmt:
        n = re.sub(r"\D", "", c)
        if len(n) == 14 and n not in chave:
            cnpjs_validos.append(n)
    if cnpjs_validos:
        data["cnpj_emissor"] = cnpjs_validos[0]
    if len(cnpjs_validos) > 1:
        data["cnpj_destinatario"] = cnpjs_validos[1]

    # NOME EMPRESA
    for linha in bloco.split("\n"):
        lu = linha.upper().strip()
        if any(x in lu for x in ["TELEFONE","SERIE","WWW","HTTP","@","CONSULTA","CNPJ","ENDERE","FOLHA","BATEIAS"]):
            continue
        if any(x in lu for x in ["MENDES","DESTINAT","RECEBEDOR","NOME/RAZ","ANTONIETA"]):
            continue
        if any(x in lu for x in ["ORTHOMAX","INDUSTRIA","COMERCIO","COLCHOES"]):
            nome = re.sub(r"DANFE|DOCUMENTO|AUXILIAR|ELETRONICA|FOLHA", "", linha.strip(), flags=re.IGNORECASE)
            nome = re.sub(r"\s+", " ", nome).strip()
            if len(nome) > 3:
                data["nome_empresa"] = nome[:60]
                break
    if "nome_empresa" not in data and "ORTHOMAX" in bloco.upper():
        data["nome_empresa"] = "ORTHOMAX INDUSTRIA E COMERCIO DE COLCHOES"

        # DATA DE EMISSAO
    def parse_data(d_str):
        partes = d_str.split("/")
        try:
            dia, mes = int(partes[0]), int(partes[1])
            ano = partes[2] if len(partes[2])==4 else "20"+partes[2]
            if 1 <= mes <= 12 and 1 <= dia <= 31 and 2020 <= int(ano) <= 2030:
                return ano + "-" + str(mes).zfill(2) + "-" + str(dia).zfill(2)
        except: pass
        return None
    for linha in bloco.split("\n"):
        lu = linha.upper()
        if "NOME/RAZ" in lu or "RAZAO SOCIAL" in lu:
            continue
        datas = re.findall(r"\b(\d{2}/\d{2}/\d{2,4})\b", linha)
        for d_str in datas:
            dt = parse_data(d_str)
            if dt:
                data["data_emissao"] = dt
                break
        if data.get("data_emissao"):
            break

# VALOR TOTAL
    vals_raw = re.findall(r"\d{1,3}(?:\.\d{3})*,\d{2}", bloco)
    floats = []
    for v in vals_raw:
        try: floats.append(float(v.replace(".","").replace(",",".")))
        except: pass
    if floats:
        ultimo_isolado = None
        skip = False
        for linha in bloco.split("\n"):
            if "NF?" in linha:
                skip = True
            if not skip and re.fullmatch(r"\d{1,3}(?:\.\d{3})*,\d{2}", linha.strip()):
                try: ultimo_isolado = str(float(linha.strip().replace(".","").replace(",",".")))
                except: pass
        if ultimo_isolado:
            data["valor_total"] = ultimo_isolado
        if "valor_total" not in data:
            m_vt = re.search(r"VALOR TOTAL DA NOTA[^\n]*\n([^\n]+)", bloco, re.IGNORECASE)
            if m_vt:
                vs = [v for v in re.findall(r"\d{1,3}(?:\.\d{3})*,\d{2}", m_vt.group(1)) if v != "0,00"]
                if vs:
                    try: data["valor_total"] = str(float(vs[-1].replace(".","").replace(",",".")))
                    except: pass
        if "valor_total" not in data:
            data["valor_total"] = str(max(floats))

    # DESTINATARIO
    linhas_bloco = bloco.split("\n")
    for j, linha in enumerate(linhas_bloco):
        if "DESTINAT" in linha.upper() and "REMETENTE" in linha.upper():
            for k in range(j+1, min(j+4, len(linhas_bloco))):
                prox = linhas_bloco[k].strip()
                if len(prox) > 5 and "NOME" not in prox[:4].upper() and "CNPJ" not in prox[:4].upper():
                    dest = re.sub(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", "", prox)
                    dest = re.sub(r"\d{3}\.\d{3}\.\d{3}-\d{2}", "", dest)
                    dest = re.sub(r"\b\d{11}\b", "", dest)
                    dest = re.sub(r"\b\d{2}/\d{2}/\d{2,4}\b", "", dest)
                    dest = re.sub(r"\b\d{5,}\b", "", dest)
                    dest = re.sub(r"^[^A-Za-zÀ-ú]+", "", dest)
                    dest = re.sub(r"\s+", " ", dest).strip()
                    if len(dest) > 3:
                        data["destinatario"] = dest[:60]
                        break
            break
    # NATUREZA
    m = re.search(r"NATUREZA DA OPERA[CO][AO]O\s*\n?([^\n]+)", bloco, re.IGNORECASE)
    if m:
        nat = m.group(1).strip()
        if "PROTOCOLO" not in nat.upper() and len(nat) > 3:
            data["natureza_operacao"] = nat[:50]

    # TELEFONE
    ts = re.findall(r"\(?\d{2}\)?\s?\d{4,5}[-\s]?\d{4}", bloco)
    if ts:
        data["telefone"] = ts[0]

    # LOG
    num = data.get("numero_nota","?")
    cli = data.get("destinatario","?")
    emp = data.get("nome_empresa","?")
    cnpj = data.get("cnpj_emissor","?")
    dt = data.get("data_emissao","?")
    val = data.get("valor_total","?")
    print("NF", num, "| cli:", str(cli)[:20], "| emp:", str(emp)[:15], "| cnpj:", cnpj, "| data:", dt, "| valor:", val)

    # ITENS DE PRODUTO
    data["itens"] = extract_itens(bloco)
    if data["itens"]:
        print("  itens encontrados:", len(data["itens"]))

    return {k: v for k, v in data.items() if v not in ("", "N/A", None)}

def extract_itens(bloco):
    import re
    itens = []

    idx_dados = bloco.upper().find("DADOS DO PRODUTO")
    if idx_dados < 0:
        return itens

    secao = bloco[idx_dados:]
    linhas = secao.split("\n")

    pat = re.compile(
        r"(\d+)[\]|\s]\s*(.+?)\|\s*UN\s*\|\s*[—\-\s]*(\d{1,4})\d{3}\s+([\d,]+)\s+([\d.,]+)",
        re.IGNORECASE
    )

    for linha in linhas:
        l = linha.strip()
        if not l or len(l) < 15:
            continue
        if any(x in l.upper() for x in ["DESCRI","PRODUTO/SERV","NCM","UNITARIO","DADOS DO","COP.","PROD. SH","B.CALC"]):
            continue

        m = pat.search(l)
        if not m:
            continue

        cod = m.group(1).strip()
        desc_raw = m.group(2).strip()
        qtd_str = m.group(3).strip()
        vunit_str = m.group(4).strip()
        vtot_str = m.group(5).strip()

        # Limpar descricao
        desc = re.sub(r"san\w{3,}", "", desc_raw, flags=re.IGNORECASE)
        desc = re.sub(r"s4n\w{3,}", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"sa0\w{3,}", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"lo\s+co.*", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"jo\s+oo.*", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\d{6,}", "", desc)
        desc = re.sub(r"\|.*$", "", desc)
        desc = re.sub(r"\s+", " ", desc).strip()
        desc = re.sub(r"[^\w\s\-/,.]", " ", desc).strip()
        desc = re.sub(r"\s+", " ", desc).strip()

        if len(desc) < 3:
            continue

        def pnum(s):
            s = s.strip()
            if "," in s and "." in s:
                return float(s.replace(".","").replace(",","."))
            if "," in s:
                return float(s.replace(",","."))
            if "." in s:
                pts = s.split(".")
                if len(pts[-1]) <= 2:
                    return float(s)
                return float(s.replace(".",""))
            return float(s)

        try:
            qtd = float(qtd_str)  # quantidade real (sem os 3 zeros)
            vunit = pnum(vunit_str)
            vtot = pnum(vtot_str)

            if qtd <= 0 or qtd > 9999:
                continue
            if vunit <= 0 or vunit > 99999:
                continue
            if vtot <= 0:
                continue

            itens.append({
                "codigo": cod,
                "descricao": desc[:80],
                "quantidade": int(qtd),
                "valor_unitario": round(vunit, 2),
                "valor_total_item": round(vtot, 2)
            })
        except:
            continue

    return itens


def extract_recibo(bloco, conf):
    data = {}
    m = re.search(r'Recibo\s*[:\s#]*(\d+)', bloco, re.IGNORECASE)
    data["numero_recibo"] = m.group(1) if m else "N/A"
    m = re.search(r'(?:Pedido)[:\s]*(\d+)', bloco, re.IGNORECASE)
    data["numero_pedido"] = m.group(1) if m else "N/A"
    m = re.search(r'(?:Cliente|DESTINATARIO)[:\s]*(.+?)(?:CNPJ|CPF|\n)', bloco, re.IGNORECASE)
    data["cliente"] = _limpar(m.group(1), 60) if m else "N/A"
    m = re.search(r'(?:Empresa)[:\s]*(.+?)(?:\n|CNPJ)', bloco, re.IGNORECASE)
    data["empresa"] = _limpar(m.group(1), 60) if m else "N/A"
    vs = _valores(bloco)
    data["valor_total"] = str(vs[0]) if vs else "N/A"
    ds = _datas(bloco)
    data["data"] = ds[0] if ds else "N/A"
    cs = _cnpjs(bloco)
    data["cnpj_cliente"] = cs[0] if cs else "N/A"
    if len(cs) > 1:
        data["cnpj_empresa"] = cs[1]
    ts = _telefones(bloco)
    data["telefone"] = ts[0] if ts else "N/A"
    return {k: v for k, v in data.items() if v not in ("N/A","",None)}

def extract_boleto(bloco, conf):
    data = {}
    m = re.search(r'(\d{5}\.\d{5}\s+\d{5}\.\d{6}\s+\d{5}\.\d{6}\s+\d\s+\d{14})', bloco)
    data["linha_digitavel"] = m.group(1) if m else "N/A"
    m = re.search(r'(\d{44})', re.sub(r'\s','',bloco))
    data["codigo_barras"] = m.group(1) if m else "N/A"
    m = re.search(r'(?:Benefici|BENEFICI)[^\:]*[:\s]*(.+?)(?:\n|CNPJ|CPF)', bloco, re.IGNORECASE)
    data["beneficiario"] = _limpar(m.group(1), 60) if m else "N/A"
    m = re.search(r'(?:Pagador|PAGADOR)[^\:]*[:\s]*(.+?)(?:\n|CNPJ|CPF)', bloco, re.IGNORECASE)
    data["pagador"] = _limpar(m.group(1), 60) if m else "N/A"
    cs = _cnpjs(bloco)
    data["cnpj_beneficiario"] = cs[0] if cs else "N/A"
    vs = _valores(bloco)
    data["valor"] = str(vs[0]) if vs else "N/A"
    ds = _datas(bloco)
    data["vencimento"] = ds[0] if ds else "N/A"
    bancos = ["BRADESCO","ITAU","SANTANDER","BANCO DO BRASIL","CAIXA","NUBANK","SICREDI","SICOOB","INTER"]
    data["banco"] = next((b for b in bancos if b in bloco.upper()), "N/A")
    m = re.search(r'Nosso N[uú]mero[:\s]*(\S+)', bloco, re.IGNORECASE)
    data["nosso_numero"] = m.group(1) if m else "N/A"
    return {k: v for k, v in data.items() if v not in ("N/A","",None)}

def extract_comprovante(bloco, conf, tipo="comprovante"):
    data = {"tipo": tipo.upper()}
    vs = _valores(bloco)
    data["valor"] = str(vs[0]) if vs else "N/A"
    ds = _datas(bloco)
    data["data"] = ds[0] if ds else "N/A"
    m = re.search(r'(\d{2}:\d{2}(?::\d{2})?)', bloco)
    data["hora"] = m.group(0) if m else "N/A"
    m = re.search(r'(?:Pagador|Pagante|De|Origem)[:\s]*(.+?)(?:\n|CPF|CNPJ)', bloco, re.IGNORECASE)
    data["pagador"] = _limpar(m.group(1), 60) if m else "N/A"
    m = re.search(r'(?:Recebedor|Favorecido|Para|Destino)[:\s]*(.+?)(?:\n|CPF|CNPJ)', bloco, re.IGNORECASE)
    data["recebedor"] = _limpar(m.group(1), 60) if m else "N/A"
    cs = _cnpjs(bloco)
    if cs:
        data["cnpj"] = cs[0]
    bancos = ["BRADESCO","ITAU","SANTANDER","BANCO DO BRASIL","CAIXA","NUBANK","INTER","C6","ORIGINAL"]
    data["banco"] = next((b for b in bancos if b in bloco.upper()), "N/A")
    m = re.search(r'(?:Autenticacao|Codigo|E2EId)[:\s]*([A-Za-z0-9]{10,})', bloco, re.IGNORECASE)
    data["autenticacao"] = m.group(1) if m else "N/A"
    if "pix" in tipo.lower():
        m = re.search(r'(?:Chave PIX|Chave)[:\s]*(\S+)', bloco, re.IGNORECASE)
        data["chave_pix"] = m.group(1) if m else "N/A"
    return {k: v for k, v in data.items() if v not in ("N/A","",None)}

def extract_cheque(bloco, conf):
    data = {}
    vs = _valores(bloco)
    data["valor"] = str(vs[0]) if vs else "N/A"
    ds = _datas(bloco)
    data["data"] = ds[0] if ds else "N/A"
    m = re.search(r'(?:A|AO SR\.?)\s+([A-Za-z\s\.]+?)(?:\n|,|CPF|CNPJ)', bloco, re.IGNORECASE)
    data["beneficiario"] = _limpar(m.group(1), 60) if m else "N/A"
    m = re.search(r'(?:NUMERO|CHQ)[:\s]*(\d{6,})', bloco, re.IGNORECASE)
    data["numero_cheque"] = m.group(1) if m else "N/A"
    bancos = ["BRADESCO","ITAU","SANTANDER","BANCO DO BRASIL","CAIXA","NUBANK"]
    data["banco"] = next((b for b in bancos if b in bloco.upper()), "N/A")
    cs = _cnpjs(bloco)
    data["cnpj_cpf"] = cs[0] if cs else "N/A"
    return {k: v for k, v in data.items() if v not in ("N/A","",None)}

def extract_generico(bloco, conf):
    data = {}
    cs = _cnpjs(bloco)
    if cs:
        data["cnpjs"] = ", ".join(cs)
    vs = _valores(bloco)
    if vs:
        data["valores"] = ", ".join([str(v) for v in vs[:5]])
    ds = _datas(bloco)
    if ds:
        data["datas"] = ", ".join(ds[:3])
    ts = _telefones(bloco)
    if ts:
        data["telefones"] = ", ".join(ts)
    es = _emails(bloco)
    if es:
        data["emails"] = ", ".join(es)
    linhas = [l.strip() for l in bloco.split('\n') if l.strip()][:3]
    data["primeiras_linhas"] = " | ".join(linhas)
    data["texto_completo"] = bloco[:500]
    return data

def process_document(file_path):
    text, confidence = extract_text_from_file(file_path)
    if not text.strip():
        return {"doc_type": "erro", "confidence": 0.0,
                "error": "Nao foi possivel extrair texto", "fields": {}, "documentos": []}
    doc_type = classify_document(text)
    blocos = _split_blocos(text, doc_type)
    extratores = {
        "nota_fiscal": extract_nota,
        "boleto": extract_boleto,
        "comprovante_pix": lambda b, c: extract_comprovante(b, c, "pix"),
        "comprovante_ted": lambda b, c: extract_comprovante(b, c, "ted"),
        "comprovante": extract_comprovante,
        "cheque": extract_cheque,
        "recibo": extract_recibo,
        "desconhecido": extract_generico,
    }
    documentos = []
    for i, bloco in enumerate(blocos):
        tipo_bloco = classify_document(bloco) if len(blocos) > 1 else doc_type
        ext = extratores.get(tipo_bloco, extract_generico)
        campos = ext(bloco, confidence)
        documentos.append({"indice": i+1, "doc_type": tipo_bloco, "fields": campos})
    fields_principal = documentos[0]["fields"] if documentos else {}
    return {
        "doc_type": doc_type,
        "confidence": round(confidence, 3),
        "total_documentos": len(documentos),
        "fields": fields_principal,
        "documentos": documentos,
        "raw_text_preview": text[:300]
    }
