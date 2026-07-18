from __future__ import annotations

import base64
import io
import math
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, Image as RLImage
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image, ImageDraw, ImageFont

DATA_DIR = Path(__file__).parent / "data"
ASSETS_DIR = Path(__file__).parent / "assets"

VW_BLUE = "#001E50"
VW_LIGHT_BLUE = "#00A3E0"
VW_GRAY = "#F3F5F7"


def asset_data_uri(filename: str) -> str:
    """Retorna arquivo de imagem dos assets em base64 para uso no HTML do Streamlit."""
    path = ASSETS_DIR / filename
    if not path.exists():
        return ""
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("utf-8")

GROUP_ORDER = {
    "Rodoviário": 1,
    "Misto": 2,
    "Severo": 3,
    "Severo ou Especial": 4,
    "Especial": 5,
    "Não enquadrar": 0,
    "Transição": 0,
    "": 0,
}

GROUP_BY_SCORE = [
    (90, "Especial"),
    (75, "Severo ou Especial"),
    (50, "Severo"),
    (25, "Misto"),
    (0, "Rodoviário"),
]

PT_MONTHS = {
    "jan": 1,
    "janeiro": 1,
    "fev": 2,
    "fevereiro": 2,
    "mar": 3,
    "marco": 3,
    "março": 3,
    "abr": 4,
    "abril": 4,
    "mai": 5,
    "maio": 5,
    "jun": 6,
    "junho": 6,
    "jul": 7,
    "julho": 7,
    "ago": 8,
    "agosto": 8,
    "set": 9,
    "setembro": 9,
    "out": 10,
    "outubro": 10,
    "nov": 11,
    "novembro": 11,
    "dez": 12,
    "dezembro": 12,
}

MONTH_OPTIONS = [
    (1, "Janeiro"),
    (2, "Fevereiro"),
    (3, "Março"),
    (4, "Abril"),
    (5, "Maio"),
    (6, "Junho"),
    (7, "Julho"),
    (8, "Agosto"),
    (9, "Setembro"),
    (10, "Outubro"),
    (11, "Novembro"),
    (12, "Dezembro"),
]


def clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def fmt_br_int(value: Any, suffix: str = "") -> str:
    """Formata números inteiros no padrão brasileiro: 1.000.000."""
    try:
        v = float(value)
    except (ValueError, TypeError):
        return "—"
    if math.isnan(v):
        return "—"
    txt = f"{round(v):,}".replace(",", ".")
    return f"{txt}{suffix}"


def fmt_br_optional(value: Any, suffix: str = "") -> str:
    try:
        v = float(value)
    except (ValueError, TypeError):
        return ""
    if math.isnan(v) or v == 0:
        return ""
    return fmt_br_int(v, suffix)


def fmt_intervalo_meses(value: str) -> str:
    if not value or value in {"Definir grupo", "Avaliar após início da operação"}:
        return value or "—"
    try:
        return fmt_br_int(math.ceil(float(value)), " mês(es)")
    except (ValueError, TypeError):
        return value


def digits_only(value: str) -> str:
    return re.sub(r"\D", "", clean_text(value))


def validar_cpf(cpf: str) -> bool:
    cpf = digits_only(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    dig1 = (soma * 10) % 11
    dig1 = 0 if dig1 == 10 else dig1
    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    dig2 = (soma * 10) % 11
    dig2 = 0 if dig2 == 10 else dig2
    return cpf[-2:] == f"{dig1}{dig2}"


def validar_cnpj(cnpj: str) -> bool:
    cnpj = digits_only(cnpj)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    soma = sum(int(cnpj[i]) * pesos1[i] for i in range(12))
    resto = soma % 11
    dig1 = 0 if resto < 2 else 11 - resto
    soma = sum(int(cnpj[i]) * pesos2[i] for i in range(13))
    resto = soma % 11
    dig2 = 0 if resto < 2 else 11 - resto
    return cnpj[-2:] == f"{dig1}{dig2}"


def normalizar_chassi(chassi: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", clean_text(chassi)).upper()


def validar_chassi(chassi: str) -> bool:
    chassi = normalizar_chassi(chassi)
    return bool(re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", chassi))


def normalizar_placa(placa: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", clean_text(placa)).upper()


def validar_placa(placa: str) -> tuple[bool, str]:
    placa_norm = normalizar_placa(placa)
    if re.fullmatch(r"[A-Z]{3}[0-9]{4}", placa_norm):
        return True, "Antiga"
    if re.fullmatch(r"[A-Z]{3}[0-9][A-Z][0-9]{2}", placa_norm):
        return True, "Mercosul"
    return False, ""


def validar_formulario_cliente(dados: dict[str, Any]) -> list[str]:
    erros: list[str] = []
    informar_cliente = dados.get("informar_cliente") == "SIM"
    tipo_cliente = dados.get("tipo_cliente", "")
    documento = dados.get("documento", "")
    chassi = dados.get("chassi", "")
    placa = dados.get("placa", "")
    cenario = dados.get("cenario", "")
    modelo = dados.get("modelo", "")

    if not modelo or modelo == "Selecione o modelo":
        erros.append("Selecione o modelo do veículo.")

    # Operação: todos os campos de seleção devem ser explicitamente respondidos.
    if dados.get("aplicacao") in ("", "Selecione aplicação"):
        erros.append("Selecione a aplicação.")
    if dados.get("implemento") in ("", "Selecione implemento"):
        erros.append("Selecione o implemento.")
    for campo, rotulo in [
        ("aplicacao_conhecida", "Aplicação conhecida?"),
        ("pavimento_100", "Pavimento 100% asfaltado?"),
        ("fora_estrada", "Fora de estrada?"),
        ("regiao_serrana", "Região serrana/montanhosa?"),
        ("paradas", "Paradas constantes?"),
        ("marcha_lenta", "Marcha lenta elevada?"),
        ("rota_curta", "Rota curta?"),
        ("poeira", "Poeira/lama/terra?"),
    ]:
        if dados.get(campo) not in ("SIM", "NÃO"):
            erros.append(f"Responda o campo: {rotulo}")
    if dados.get("fora_estrada") == "SIM" and to_float(dados.get("fora_estrada_pct")) <= 0:
        erros.append("Informe o percentual de fora de estrada.")

    if informar_cliente:
        if not clean_text(dados.get("cliente", "")):
            erros.append("Informe o nome do cliente/razão social.")

        if tipo_cliente == "Pessoa Jurídica":
            if not validar_cnpj(documento):
                erros.append("CNPJ inválido. Informe 14 dígitos válidos.")
        elif tipo_cliente == "Pessoa Física":
            if not validar_cpf(documento):
                erros.append("CPF inválido. Informe 11 dígitos válidos.")
        else:
            erros.append("Selecione o tipo de cliente.")

        if not validar_chassi(chassi):
            erros.append("Chassi inválido. O chassi deve conter exatamente 17 caracteres alfanuméricos válidos.")

        placa_ok, _ = validar_placa(placa)
        if not placa_ok:
            erros.append("Placa inválida. Use padrão antigo ABC1234/ABC-1234 ou Mercosul ABC1D23.")
    else:
        # Para simulação sem dados do cliente, placa e chassi são opcionais.
        # Se preenchidos, devem ser coerentes.
        if chassi and not validar_chassi(chassi):
            erros.append("Chassi inválido. Informe 17 caracteres ou deixe em branco para simulação simples.")
        if placa:
            placa_ok, _ = validar_placa(placa)
            if not placa_ok:
                erros.append("Placa inválida. Use padrão antigo ABC1234/ABC-1234 ou Mercosul ABC1D23.")

    if cenario == "Usado":
        if not parse_mes_ano(dados.get("data_venda", "")):
            erros.append("Para veículo usado, informe a data de venda no formato Abr/2024, 04/24 ou 04/2024.")
        if to_float(dados.get("odometro")) <= 0:
            erros.append("Para veículo usado, informe o odômetro atual.")
        if to_float(dados.get("horimetro")) <= 0:
            erros.append("Para veículo usado, informe o horímetro atual.")
    elif cenario == "Novo":
        if to_float(dados.get("km_mensal_estimado")) <= 0:
            erros.append("Para veículo novo, informe a quilometragem mensal estimada.")
    else:
        erros.append("Selecione o tipo de veículo.")

    return erros

@st.cache_data(show_spinner=False)
def load_data() -> dict[str, pd.DataFrame]:
    """Carrega somente bases técnicas.

    Modo LGPD-safe: não carrega bases reais de clientes ou veículos.
    Dados de cliente/veículo devem ser digitados manualmente para geração do PDF.
    """
    data = {}
    for name in ["base_modelos", "aplicacoes", "implementos", "intervalos", "plano_contratos"]:
        df = pd.read_csv(DATA_DIR / f"{name}.csv", dtype=str).fillna("")
        data[name] = df
    return data


def buscar_cliente_base(base_clientes: pd.DataFrame, documento_digits: str, tipo_cliente: str = "") -> dict[str, Any]:
    """Busca cliente nas bases internas, respeitando a ordem Base_clientes_1, Base_clientes_2, Base_clientes_3."""
    documento_digits = digits_only(documento_digits)
    if not documento_digits or base_clientes.empty or "Documento" not in base_clientes.columns:
        return {}
    df = base_clientes.copy()
    df["Documento_limpo"] = df["Documento"].astype(str).map(digits_only)
    row = df[df["Documento_limpo"] == documento_digits]
    if row.empty:
        return {}
    fonte_ordem = {"Base_clientes_1": 1, "Base_clientes_2": 2, "Base_clientes_3": 3}
    if "Fonte" in row.columns:
        row = row.assign(_ordem=row["Fonte"].map(fonte_ordem).fillna(99)).sort_values("_ordem")
    r = row.iloc[0]
    nome = clean_text(r.get("Nome", ""))
    tipo = clean_text(r.get("Tipo Pessoa", ""))
    return {
        "fonte": clean_text(r.get("Fonte", "Base interna")),
        "nome": nome,
        "razao_social": nome,
        "tipo_pessoa": tipo,
        "documento": documento_digits,
        "email": clean_text(r.get("Email", "")),
    }


def consultar_cnpj_com_bases(cnpj_digits: str, base_clientes: pd.DataFrame) -> dict[str, Any]:
    interno = buscar_cliente_base(base_clientes, cnpj_digits, "Pessoa Jurídica")
    if interno.get("razao_social"):
        return interno
    return consultar_cnpj_publica(cnpj_digits)


def consultar_cpf_com_bases(cpf_digits: str, base_clientes: pd.DataFrame) -> dict[str, Any]:
    interno = buscar_cliente_base(base_clientes, cpf_digits, "Pessoa Física")
    if interno.get("nome"):
        return interno
    return consultar_cpf_cpfhub(cpf_digits)


@st.cache_data(show_spinner=False, ttl=24 * 60 * 60)
def consultar_cnpj_publica(cnpj_digits: str) -> dict[str, Any]:
    """Consulta CNPJ em APIs públicas e retorna dados cadastrais básicos.

    Ordem de consulta:
    1. BrasilAPI
    2. ReceitaWS como contingência

    A função retorna dicionário com erro quando nenhuma fonte retorna razão social.
    """
    cnpj_digits = digits_only(cnpj_digits)
    if len(cnpj_digits) != 14:
        return {"erro": "CNPJ deve conter 14 dígitos."}

    erros: list[str] = []

    # 1) BrasilAPI
    try:
        resp = requests.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_digits}", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            razao = clean_text(data.get("razao_social") or data.get("nome") or "")
            if razao:
                return {
                    "fonte": "BrasilAPI",
                    "razao_social": razao,
                    "nome_fantasia": clean_text(data.get("nome_fantasia") or ""),
                    "situacao": clean_text(data.get("descricao_situacao_cadastral") or data.get("situacao_cadastral") or ""),
                    "municipio": clean_text(data.get("municipio") or ""),
                    "uf": clean_text(data.get("uf") or ""),
                }
        else:
            erros.append(f"BrasilAPI status {resp.status_code}")
    except Exception as exc:
        erros.append(f"BrasilAPI indisponível: {exc}")

    # 2) ReceitaWS - contingência
    try:
        resp = requests.get(f"https://www.receitaws.com.br/v1/cnpj/{cnpj_digits}", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if clean_text(data.get("status")) == "ERROR":
                erros.append(clean_text(data.get("message")) or "ReceitaWS não retornou dados")
            else:
                razao = clean_text(data.get("nome") or data.get("razao_social") or "")
                if razao:
                    return {
                        "fonte": "ReceitaWS",
                        "razao_social": razao,
                        "nome_fantasia": clean_text(data.get("fantasia") or ""),
                        "situacao": clean_text(data.get("situacao") or ""),
                        "municipio": clean_text(data.get("municipio") or ""),
                        "uf": clean_text(data.get("uf") or ""),
                    }
        else:
            erros.append(f"ReceitaWS status {resp.status_code}")
    except Exception as exc:
        erros.append(f"ReceitaWS indisponível: {exc}")

    detalhe = " | ".join(erros) if erros else "sem retorno das APIs públicas"
    return {"erro": f"Razão social não localizada para este CNPJ. Detalhe: {detalhe}"}



@st.cache_data(show_spinner=False, ttl=24 * 60 * 60)
def consultar_cpf_cpfhub(cpf_digits: str) -> dict[str, Any]:
    """Consulta CPF na CPFHub.io usando chave somente no servidor.

    Configure a variável de ambiente ou secret do Streamlit:
    CPFHUB_API_KEY

    A API pode retornar ``error`` como objeto, texto simples ou até payload não JSON.
    Por isso o tratamento abaixo é defensivo para não quebrar a tela do simulador.
    """
    cpf_digits = digits_only(cpf_digits)
    if len(cpf_digits) != 11:
        return {"erro": "CPF deve conter 11 dígitos."}
    if not validar_cpf(cpf_digits):
        return {"erro": "CPF inválido."}

    api_key = os.getenv("CPFHUB_API_KEY", "")
    if not api_key:
        try:
            secrets_obj = st.secrets
            if hasattr(secrets_obj, "get"):
                api_key = secrets_obj.get("CPFHUB_API_KEY", "")
        except Exception:
            api_key = ""
    if not api_key:
        return {"erro": "Chave CPFHUB_API_KEY não configurada no servidor. Preencha o nome manualmente."}

    try:
        resp = requests.get(
            f"https://api.cpfhub.io/cpf/{cpf_digits}",
            headers={"x-api-key": api_key},
            timeout=10,
        )

        try:
            payload = resp.json()
        except Exception:
            payload = {"raw": resp.text}

        if not isinstance(payload, dict):
            payload = {"raw": str(payload)}

        if resp.status_code == 200 and payload.get("success") is True:
            data = payload.get("data") or {}
            if not isinstance(data, dict):
                data = {}
            nome = clean_text(data.get("nameUpper") or data.get("name") or "")
            if nome:
                return {
                    "fonte": "CPFHub.io",
                    "nome": nome,
                    "genero": clean_text(data.get("gender") or ""),
                    "nascimento": clean_text(data.get("birthDate") or ""),
                }

        erro_api = payload.get("error")
        if isinstance(erro_api, dict):
            mensagem = clean_text(erro_api.get("message") or "")
        elif isinstance(erro_api, str):
            mensagem = clean_text(erro_api)
        else:
            mensagem = clean_text(payload.get("message") or payload.get("raw") or "")

        if resp.status_code == 400:
            mensagem = mensagem or "CPFHub: formato de CPF inválido."
        elif resp.status_code == 401:
            mensagem = "CPFHub: chave de API inválida ou ausente."
        elif resp.status_code == 404:
            mensagem = mensagem or "CPF não encontrado."
        elif resp.status_code == 429:
            mensagem = "CPFHub: limite de consultas excedido."
        elif resp.status_code in (500, 503):
            mensagem = "CPFHub temporariamente indisponível. Tente novamente mais tarde."
        elif not mensagem:
            mensagem = f"CPFHub status {resp.status_code}."

        return {"erro": mensagem}
    except Exception as exc:
        return {"erro": f"CPFHub indisponível: {exc}"}

def modelo_sistema_por_descricao(modelo_original: str, modelos_validos: list[str]) -> str:
    """Mapeia a descrição da base de veículos para o modelo do simulador.

    Regra definida pelo usuário:
    - avaliar os 6 primeiros caracteres da descrição do modelo da base;
    - exceção: 11.180 4x4 preserva a indicação 4x4;
    - se houver sufixo 6x2 em 13.180/14.180, preservar o modelo específico.
    """
    texto = clean_text(modelo_original).upper().replace("×", "X")
    texto = re.sub(r"\s+", " ", texto)
    if not texto:
        return ""

    if "11.180" in texto and "4X4" in texto and "11.180 4x4" in modelos_validos:
        return "11.180 4x4"
    if "13.180" in texto and "6X2" in texto and "13.180 6x2" in modelos_validos:
        return "13.180 6x2"
    if "14.180" in texto and "6X2" in texto and "14.180 6x2" in modelos_validos:
        return "14.180 6x2"
    if "EXPRESS" in texto and "Express" in modelos_validos:
        return "Express"

    # Regra principal: os 6 primeiros caracteres da descrição da base.
    prefixo = texto[:6]
    prefixo_match = re.match(r"\d{1,2}\.\d{3}", prefixo)
    if prefixo_match:
        modelo = prefixo_match.group(0)
        if modelo in modelos_validos:
            return modelo

    # Contingência para descrições que comecem com texto antes do modelo.
    match = re.search(r"(\d{1,2}\.\d{3})", texto)
    if match:
        modelo = match.group(1)
        if modelo in modelos_validos:
            return modelo

    return ""

def buscar_veiculo_por_placa(veiculos: pd.DataFrame, placa: str) -> dict[str, str]:
    placa_norm = normalizar_placa(placa)
    if not placa_norm or veiculos.empty or "Placa" not in veiculos.columns:
        return {}
    row = veiculos[veiculos["Placa"].astype(str).str.upper() == placa_norm]
    if row.empty:
        return {}
    r = row.iloc[0]
    return {
        "placa": placa_norm,
        "chassi": clean_text(r.get("Chassi", "")),
        "modelo_original": clean_text(r.get("Modelo Original", "")),
        "modelo_sistema": clean_text(r.get("Modelo Sistema", "")),
        "proprietario": clean_text(r.get("Proprietário", "")),
    }



def buscar_veiculo_por_chassi(veiculos: pd.DataFrame, chassi_input: str) -> dict[str, str]:
    chassi_norm = normalizar_chassi(chassi_input)
    if not chassi_norm or veiculos.empty or "Chassi" not in veiculos.columns:
        return {}
    serie = veiculos["Chassi"].astype(str).str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
    if len(chassi_norm) == 17:
        mask = serie == chassi_norm
    elif len(chassi_norm) == 8:
        mask = serie.str.endswith(chassi_norm)
    else:
        return {}
    row = veiculos[mask]
    if row.empty:
        return {}
    r = row.iloc[0]
    return {
        "placa": clean_text(r.get("Placa", "")),
        "chassi": clean_text(r.get("Chassi", "")),
        "modelo_original": clean_text(r.get("Modelo Original", "")),
        "modelo_sistema": clean_text(r.get("Modelo Sistema", "")),
        "proprietario": clean_text(r.get("Proprietário", "")),
    }


def parse_mes_ano(texto: Any) -> date | None:
    """Aceita formatos como Abr/2024, 04/24, 04/2024, 01/04/2024 ou objeto date."""
    if isinstance(texto, datetime):
        return date(texto.year, texto.month, 1)
    if isinstance(texto, date):
        return date(texto.year, texto.month, 1)
    t = clean_text(texto).lower()
    if not t:
        return None

    # tenta data completa primeiro
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%m/%Y", "%m/%y"):
        try:
            parsed = datetime.strptime(t, fmt).date()
            return date(parsed.year, parsed.month, 1)
        except ValueError:
            pass

    # mes textual / ano
    match = re.match(r"([a-zç]{3,9})\s*/\s*(\d{2,4})", t)
    if match:
        mes_txt, ano_txt = match.groups()
        mes = PT_MONTHS.get(mes_txt) or PT_MONTHS.get(mes_txt[:3])
        if mes:
            ano = int(ano_txt)
            if ano < 100:
                ano += 2000
            return date(ano, mes, 1)

    return None


def meses_entre(data_venda: date, data_atual: date | None = None) -> int:
    data_atual = data_atual or date.today()
    meses = (data_atual.year - data_venda.year) * 12 + (data_atual.month - data_venda.month) + 1
    return max(1, meses)


def score_km_anual(familia: str, km_anual: float) -> int:
    if km_anual <= 0:
        return 0
    if familia == "Delivery":
        if km_anual > 80000:
            return 0
        if km_anual >= 40000:
            return 7
        if km_anual >= 15000:
            return 15
        return 20
    # Constellation/Meteor
    if km_anual > 120000:
        return 0
    if km_anual >= 80000:
        return 6
    if km_anual >= 40000:
        return 14
    return 20


def grupo_plano_por_km(familia: str, km_mensal: float) -> str:
    if km_mensal <= 0:
        return ""
    if familia == "Delivery":
        if km_mensal <= 3250:
            return "Severo"
        if 3500 <= km_mensal <= 6500:
            return "Misto"
        if km_mensal >= 6750:
            return "Rodoviário"
        return "Transição"
    if km_mensal <= 6500:
        return "Severo"
    if 6750 <= km_mensal <= 10000:
        return "Misto"
    if km_mensal >= 10250:
        return "Rodoviário"
    return "Transição"


def score_via(pavimento_100: str, fora_estrada_pct: float) -> int:
    score = 0
    if pavimento_100 == "NÃO":
        score += 5
    if fora_estrada_pct > 0:
        if fora_estrada_pct <= 20:
            score += 5
        elif fora_estrada_pct <= 50:
            score += 10
        else:
            score += 15
    return min(15, score)


def score_operacional(regiao_serrana: str, paradas: str, marcha_lenta: str, rota_curta: str, poeira: str) -> int:
    score = 0
    score += 5 if regiao_serrana == "SIM" else 0
    score += 5 if paradas == "SIM" else 0
    score += 7 if marcha_lenta == "SIM" else 0
    score += 5 if rota_curta == "SIM" else 0
    score += 5 if poeira == "SIM" else 0
    return min(25, score)


def grupo_por_score(score: float) -> str:
    for limite, grupo in GROUP_BY_SCORE:
        if score >= limite:
            return grupo
    return "Rodoviário"


def max_grupo(grupo_a: str, grupo_b: str) -> str:
    if GROUP_ORDER.get(grupo_b, 0) > GROUP_ORDER.get(grupo_a, 0):
        return grupo_b
    return grupo_a


def garantir_minimo_grupo(grupo: str, minimo: str) -> str:
    if GROUP_ORDER.get(grupo, 0) < GROUP_ORDER.get(minimo, 0):
        return minimo
    return grupo


def modelo_33480(modelo: str) -> bool:
    return clean_text(modelo).upper().startswith("33.480")


def operacao_coleta_lixo(aplicacao: str, implemento: str) -> bool:
    texto = f"{clean_text(aplicacao)} {clean_text(implemento)}".upper()
    termos = [
        "COLETA DE LIXO",
        "COLETOR DE LIXO",
        "COMPACTADOR DE LIXO",
        "COMPACTADOR",
    ]
    return any(t in texto for t in termos)


def lookup_intervalo(intervalos: pd.DataFrame, modelo: str, grupo: str) -> dict[str, Any]:
    chave = f"{modelo}|{grupo}"
    row = intervalos[intervalos["Chave"] == chave]
    if row.empty:
        return {"km": 0, "horas": 0, "tolerancia": "", "observacao": ""}
    r = row.iloc[0]
    return {
        "km": to_float(r.get("Intervalo km", 0)),
        "horas": to_float(r.get("Intervalo horas", 0)),
        "tolerancia": clean_text(r.get("Tolerância km", "")),
        "observacao": clean_text(r.get("Observação", "")),
    }


MOTOR_OPTIONS = ["D08", "ISF", "ISL", "D26", "D26OFF", "FPT", "elet."]

SPEED_BANDS = [
    (60, "Acima de 55", 1),
    (55, "51 a 55", 1),
    (50, "45 a 50", 1),
    (45, "41 a 45", 1),
    (40, "36 a 40", 2),
    (35, "31 a 35", 2),
    (30, "26 a 30", 3),
    (25, "21 a 25", 3),
    (20, "16 a 20", 3),
    (15, "11 a 15", 3),
    (10, "Até 10", 3),
    (20, "Off Road", 3),
    (10, "Estacionário", 3),
]

INTERVALOS_MONTADORA = {
    ("D08", 1): (50000, 600), ("D08", 2): (40000, 600), ("D08", 3): (20000, 600), ("D08", 4): (600, 600),
    ("elet.", 1): (0, 0), ("elet.", 2): (30000, 0), ("elet.", 3): (20000, 0), ("elet.", 4): (0, 0),
    ("ISL", 1): (40000, 500), ("ISL", 2): (30000, 500), ("ISL", 3): (20000, 500), ("ISL", 4): (500, 500),
    ("ISF", 1): (40000, 500), ("ISF", 2): (30000, 500), ("ISF", 3): (20000, 500), ("ISF", 4): (500, 500),
    ("D26", 1): (50000, 600), ("D26", 2): (40000, 600), ("D26", 3): (20000, 600), ("D26", 4): (600, 600),
    ("D26OFF", 3): (20000, 600), ("D26OFF", 4): (600, 600),
    ("FPT", 1): (30000, 500), ("FPT", 2): (20000, 500), ("FPT", 3): (20000, 500), ("FPT", 4): (500, 500),
}

GROUP_NUM_LABEL = {1: "Rodoviário", 2: "Misto", 3: "Severo", 4: "Especial"}


def motor_montadora_padrao(motorizacao: str, modelo: str = "") -> str:
    """Converte a motorização interna para a régua base usada pela montadora.

    Regra definida no projeto:
    - Cummins ISF 3.8 -> ISF
    - MAN D08 4/6 cilindros -> D08
    - Cummins L9 -> ISL
    - MAN D2676 -> D26
    - F1C 3.0 -> FPT
    - MAN D2676 no modelo 33.480 -> D26OFF
    """
    modelo = clean_text(modelo)
    texto = clean_text(motorizacao).upper()
    if modelo_33480(modelo):
        return "D26OFF"
    if "ISF" in texto:
        return "ISF"
    if "D08" in texto:
        return "D08"
    if "L9" in texto or "ISL" in texto:
        return "ISL"
    if "D2676" in texto or "D26" in texto:
        return "D26"
    if "F1C" in texto or "FPT" in texto:
        return "FPT"
    if "ELE" in texto:
        return "elet."
    return ""

def faixa_por_velocidade(velocidade: float | None, faixa_manual: str = "45 a 50") -> tuple[int, str, int]:
    if velocidade is None or velocidade <= 0:
        return next((h, f, p) for h, f, p in SPEED_BANDS if f == faixa_manual)
    if velocidade > 55:
        return 60, "Acima de 55", 1
    if velocidade >= 51:
        return 55, "51 a 55", 1
    if velocidade >= 45:
        return 50, "45 a 50", 1
    if velocidade >= 41:
        return 45, "41 a 45", 1
    if velocidade >= 36:
        return 40, "36 a 40", 2
    if velocidade >= 31:
        return 35, "31 a 35", 2
    if velocidade >= 26:
        return 30, "26 a 30", 3
    if velocidade >= 21:
        return 25, "21 a 25", 3
    if velocidade >= 16:
        return 20, "16 a 20", 3
    if velocidade >= 11:
        return 15, "11 a 15", 3
    return 10, "Até 10", 3


def calcular_regra_montadora(motor: str, km_mensal: float, pavimento_100: str, velocidade_media: float | None, faixa_manual: str = "") -> dict[str, Any]:
    if km_mensal <= 0 or not motor:
        return {"grupo": "", "grupo_num": 0, "intervalo": 0, "intervalo_tipo": "", "meses": "", "horas": "", "faixa": "", "horas_mes": 0, "alerta": "Dados insuficientes para calcular a régua da montadora."}

    if (velocidade_media is None or velocidade_media <= 0) and not faixa_manual:
        return {"grupo": "", "grupo_num": 0, "intervalo": 0, "intervalo_tipo": "", "meses": "", "horas": "", "faixa": "", "horas_mes": 0, "alerta": "Régua montadora não calculada para veículo novo sem histórico de horímetro. Avaliar após início da operação."}

    h_ref, faixa, ponto_vel = faixa_por_velocidade(velocidade_media, faixa_manual or "45 a 50")
    if faixa_manual in {"Off Road", "Estacionário"} and (velocidade_media is None or velocidade_media <= 0):
        h_ref, faixa, ponto_vel = faixa_por_velocidade(None, faixa_manual)
    if motor == "D26OFF":
        ponto_vel = 3

    horas_mes = km_mensal / h_ref if h_ref else 0
    if horas_mes > 720:
        return {"grupo": "", "grupo_num": 0, "intervalo": 0, "intervalo_tipo": "", "meses": "", "horas": "", "faixa": faixa, "horas_mes": horas_mes, "alerta": "Regra montadora: revisar quilometragem mensal/velocidade média, pois as horas mensais superam 720 h."}

    intervalo_base = INTERVALOS_MONTADORA.get((motor, ponto_vel), (0, 0))[0]
    meses_base = intervalo_base / km_mensal if intervalo_base and km_mensal else 999
    if meses_base <= 12:
        ponto_meses = 0
    elif meses_base <= 24:
        ponto_meses = 1
    elif meses_base <= 36:
        ponto_meses = 2
    else:
        ponto_meses = 2

    horas_motor = next((v[1] for (m, _g), v in INTERVALOS_MONTADORA.items() if m == motor and v[1]), 0)
    ponto_horas = 1 if horas_mes and horas_motor and (horas_motor / horas_mes) < (10000 / km_mensal) else 0
    total_ini = ponto_vel + ponto_meses + ponto_horas
    grupo_ini = total_ini if total_ini <= 4 else 4
    if faixa == "Estacionário" and total_ini >= 3:
        grupo_ini += 1
    grupo_ini = min(4, max(1, int(grupo_ini)))

    intervalo_ini = INTERVALOS_MONTADORA.get((motor, grupo_ini), (0, 0))[0]
    meses_ini = intervalo_ini / (horas_mes if grupo_ini == 4 else km_mensal) if intervalo_ini else 999
    horas_por_revisao = meses_ini * horas_mes if horas_mes else 0
    ajuste_horas = 1 if ((grupo_ini == 1 and horas_por_revisao >= 1250) or (grupo_ini > 1 and horas_por_revisao > 1000)) else 0

    meses_km = intervalo_ini / km_mensal if intervalo_ini and km_mensal else 999
    if meses_km <= 12:
        ajuste_meses = 0
    elif meses_km <= 24:
        ajuste_meses = 1
    elif meses_km <= 36:
        ajuste_meses = 2
    else:
        ajuste_meses = 3

    grupo_num = min(4, grupo_ini + ajuste_horas + ajuste_meses)
    if pavimento_100 == "NÃO" and grupo_num == 1:
        grupo_num = 2

    grupo = GROUP_NUM_LABEL.get(grupo_num, "")
    intervalo, intervalo_horas = INTERVALOS_MONTADORA.get((motor, grupo_num), (0, 0))
    if grupo_num == 4:
        intervalo_tipo = "horas"
        meses_final = intervalo / horas_mes if horas_mes else 0
        horas_final = intervalo
    else:
        intervalo_tipo = "km"
        meses_final = intervalo / km_mensal if km_mensal else 0
        horas_final = meses_final * horas_mes if horas_mes else 0

    return {
        "grupo": grupo,
        "grupo_num": grupo_num,
        "intervalo": intervalo,
        "intervalo_tipo": intervalo_tipo,
        "meses": str(math.ceil(meses_final * 10) / 10) if meses_final else "",
        "horas": str(round(horas_final)) if horas_final else "",
        "faixa": faixa,
        "horas_mes": horas_mes,
        "alerta": "Régua montadora calculada por motorização, km mensal, velocidade média/faixa, pavimento e horas."
    }


@dataclass
class Resultado:
    grupo_sugerido: str
    grupo_aplicado: str
    grupo_plano: str
    score_total: float
    score_aplicacao: float
    score_km: float
    score_via: float
    score_operacional: float
    score_implemento: float
    grupo_montadora: str
    motor_montadora: str
    faixa_montadora: str
    horas_mes_montadora: float
    intervalo_montadora: float
    intervalo_tipo_montadora: str
    meses_montadora: str
    horas_montadora: str
    alerta_montadora: str
    grupo_final_recomendado: str
    km_mensal: float
    km_anual: float
    velocidade_media: float | None
    meses_operacao: int
    intervalo_km: float
    intervalo_horas: float
    intervalo_meses: str
    tolerancia: str
    alerta: str
    justificativa: str


def calcular_resultado(
    dados: dict[str, Any],
    base_modelos: pd.DataFrame,
    aplicacoes: pd.DataFrame,
    implementos: pd.DataFrame,
    intervalos: pd.DataFrame,
) -> Resultado:
    modelo = dados["modelo"]
    modelo_row = base_modelos[base_modelos["Modelo"] == modelo]
    familia = clean_text(modelo_row.iloc[0]["Família"]) if not modelo_row.empty else ""

    app_row = aplicacoes[aplicacoes["Aplicação"] == dados["aplicacao"]]
    score_app = to_float(app_row.iloc[0]["Score"]) if not app_row.empty else 0

    imp_row = implementos[implementos["Implemento"] == dados["implemento"]]
    score_imp = to_float(imp_row.iloc[0]["Score"]) if not imp_row.empty else 0

    cenario = dados["cenario"]
    data_atual = date.today()
    km_mensal = 0.0
    velocidade_media = None
    horas_media_mes = 0.0
    meses_operacao = 0

    if cenario == "Novo":
        km_mensal = to_float(dados.get("km_mensal_estimado"))
    else:
        data_venda = parse_mes_ano(dados.get("data_venda", ""))
        odometro = to_float(dados.get("odometro"))
        horimetro = to_float(dados.get("horimetro"))
        if data_venda and odometro > 0:
            meses = meses_entre(data_venda, data_atual)
            meses_operacao = meses
            km_mensal = odometro / meses
            if horimetro > 0:
                velocidade_media = odometro / horimetro
                horas_media_mes = horimetro / meses

    regra_montadora = calcular_regra_montadora(
        dados.get("motor_montadora", ""),
        km_mensal,
        dados.get("pavimento_100", "SIM"),
        velocidade_media,
        dados.get("faixa_velocidade_estimativa", "45 a 50"),
    )

    km_anual = km_mensal * 12 if km_mensal else 0
    score_km_val = score_km_anual(familia, km_anual)
    score_via_val = score_via(dados["pavimento_100"], to_float(dados["fora_estrada_pct"]))
    score_oper = score_operacional(
        dados["regiao_serrana"],
        dados["paradas"],
        dados["marcha_lenta"],
        dados["rota_curta"],
        dados["poeira"],
    )
    score_total = min(100, score_app + score_km_val + score_via_val + score_oper + score_imp)
    grupo_score = grupo_por_score(score_total)
    grupo_plano = grupo_plano_por_km(familia, km_mensal)

    coleta_lixo = operacao_coleta_lixo(dados.get("aplicacao", ""), dados.get("implemento", ""))

    if dados.get("aplicacao_conhecida") == "NÃO":
        grupo_sugerido = grupo_plano if grupo_plano and grupo_plano != "Transição" else "Não enquadrar"
    elif dados["aplicacao"] in ["DIVERSOS", "LOCACAO DE VEICULOS"] or not dados["aplicacao"]:
        grupo_sugerido = "Não enquadrar"
    elif coleta_lixo:
        # Regra validada em teste real: coleta de lixo / compactador não deve gerar revisão por km.
        grupo_sugerido = "Especial"
    else:
        grupo_sugerido = max_grupo(grupo_score, grupo_plano)
        if modelo_33480(modelo):
            grupo_sugerido = garantir_minimo_grupo(grupo_sugerido, "Severo")
        if modelo == "11.180 4x4":
            grupo_sugerido = garantir_minimo_grupo(grupo_sugerido, "Severo")

    grupo_aplicado = dados.get("grupo_manual") or grupo_sugerido
    if coleta_lixo:
        grupo_aplicado = "Especial"
    if modelo_33480(modelo):
        grupo_aplicado = garantir_minimo_grupo(grupo_aplicado, "Severo")
    intervalo = lookup_intervalo(intervalos, modelo, grupo_aplicado)

    intervalo_km = intervalo["km"]
    intervalo_horas = intervalo["horas"]
    tolerancia = intervalo["tolerancia"]

    if grupo_aplicado in ["Não enquadrar", "Severo ou Especial"]:
        intervalo_meses = "Definir grupo"
    elif intervalo_horas > 0 and cenario == "Usado" and horas_media_mes > 0:
        intervalo_meses = str(math.ceil((intervalo_horas / horas_media_mes) * 10) / 10)
    elif intervalo_horas > 0 and cenario == "Novo":
        intervalo_meses = "Avaliar após início da operação"
    elif intervalo_km > 0 and km_mensal > 0:
        intervalo_meses = str(math.ceil((intervalo_km / km_mensal) * 10) / 10)
    else:
        intervalo_meses = "Definir grupo"

    alerta = "Validar informações com cliente na entrega técnica."
    if dados.get("aplicacao_conhecida") == "NÃO":
        alerta = "Aplicação não conhecida: não é possível sugerir o grupo correto sem informações de operação. Resultado limitado à quilometragem mensal pela tabela do plano de manutenção."
    elif grupo_sugerido == "Não enquadrar":
        alerta = "Operação não identificada: não sugerir grupo. Levantar aplicação real com o cliente."
    elif coleta_lixo:
        alerta = "Operação de coleta de lixo/compactador: revisão deve ser tratada por horas. Não aplicar revisão por quilometragem para essa operação."
    elif modelo_33480(modelo) and grupo_aplicado == "Severo":
        alerta = "Modelo 33.480: restringir enquadramento aos grupos Severo ou Especial, conforme documentação e validação técnica da operação."
    elif grupo_plano == "Transição":
        alerta = "Km mensal está em faixa de transição do plano de manutenção. Definir grupo em conjunto com o cliente."
    elif GROUP_ORDER.get(grupo_plano, 0) > GROUP_ORDER.get(grupo_score, 0):
        alerta = f"Plano de manutenção por km mensal sugere {grupo_plano}, mais severo que a aplicação/implemento. Definir em conjunto com o cliente."
    elif intervalo_horas > 0 and cenario == "Novo":
        alerta = "Grupo com controle por horas: para veículo novo, avaliar após início da operação comparando horímetro e km rodado."
    elif grupo_sugerido == "Severo ou Especial":
        alerta = "Resultado intermediário por pontuação: validar horas, marcha lenta, PTO/hidráulico, carga e fora de estrada."

    justificativas = []
    if dados.get("aplicacao_conhecida") == "NÃO":
        justificativas.append("Aplicação não conhecida: avaliação limitada à quilometragem mensal")
    if coleta_lixo:
        justificativas.append("Coleta de lixo/compactador: controle de revisão por horas")
    if modelo_33480(modelo):
        justificativas.append("Modelo 33.480: grupos permitidos Severo ou Especial")
    if grupo_plano:
        justificativas.append(f"Plano km mensal: {grupo_plano}")
    if to_float(dados["fora_estrada_pct"]) > 0:
        justificativas.append("Fora de estrada informado")
    if dados["regiao_serrana"] == "SIM":
        justificativas.append("Região serrana/montanhosa")
    if dados["paradas"] == "SIM":
        justificativas.append("Paradas constantes")
    if dados["marcha_lenta"] == "SIM":
        justificativas.append("Marcha lenta elevada")
    if dados["rota_curta"] == "SIM":
        justificativas.append("Rota curta")
    if dados["poeira"] == "SIM":
        justificativas.append("Poeira/lama/terra")
    if dados["implemento"]:
        justificativas.append(f"Implemento: {dados['implemento']}")

    grupo_final_recomendado = grupo_aplicado
    if dados.get("aplicacao_conhecida") != "NÃO":
        if regra_montadora.get("grupo") and grupo_final_recomendado not in ["Não enquadrar", "Severo ou Especial"]:
            if GROUP_ORDER.get(regra_montadora["grupo"], 0) > GROUP_ORDER.get(grupo_final_recomendado, 0):
                grupo_final_recomendado = regra_montadora["grupo"]
        if coleta_lixo:
            grupo_final_recomendado = "Especial"
        if modelo_33480(modelo):
            grupo_final_recomendado = garantir_minimo_grupo(grupo_final_recomendado, "Severo")
        if grupo_aplicado != regra_montadora.get("grupo") and regra_montadora.get("grupo"):
            alerta = alerta + " Divergência entre régua da montadora e análise operacional/plano: revisar justificativa técnica."

    # REGRA DE CONSISTÊNCIA FINAL:
    # O intervalo e o tipo de controle SEMPRE acompanham o grupo final recomendado.
    # Nunca manter intervalo de Severo/Misto/Rodoviário quando a regra final recomendar Especial.
    intervalo_final = lookup_intervalo(intervalos, modelo, grupo_final_recomendado)
    intervalo_km_final = intervalo_final["km"]
    intervalo_horas_final = intervalo_final["horas"]
    tolerancia_final = intervalo_final["tolerancia"]

    if grupo_final_recomendado == "Especial":
        intervalo_km_final = 0
        if intervalo_horas_final <= 0:
            familia_norm = clean_text(familia).lower()
            intervalo_horas_final = 500 if "delivery" in familia_norm else 600
        tolerancia_final = ""

    if grupo_final_recomendado in ["Não enquadrar", "Severo ou Especial"]:
        intervalo_meses_final = "Definir grupo"
    elif grupo_final_recomendado == "Especial":
        if cenario == "Usado" and horas_media_mes > 0:
            intervalo_meses_final = str(math.ceil((intervalo_horas_final / horas_media_mes) * 10) / 10)
        elif cenario == "Novo":
            intervalo_meses_final = "Avaliar após início da operação"
        else:
            intervalo_meses_final = "Controlar por horímetro"
    elif intervalo_km_final > 0 and km_mensal > 0:
        intervalo_meses_final = str(math.ceil((intervalo_km_final / km_mensal) * 10) / 10)
    else:
        intervalo_meses_final = "Definir grupo"

    if grupo_final_recomendado == "Especial" and "controle por horas" not in alerta.lower():
        alerta = alerta + " Grupo final Especial: controle de revisão por horímetro; não utilizar intervalo por quilometragem."

    return Resultado(
        grupo_sugerido=grupo_sugerido,
        grupo_aplicado=grupo_aplicado,
        grupo_plano=grupo_plano,
        score_total=score_total,
        score_aplicacao=score_app,
        score_km=score_km_val,
        score_via=score_via_val,
        score_operacional=score_oper,
        score_implemento=score_imp,
        grupo_montadora=regra_montadora.get("grupo", ""),
        motor_montadora=dados.get("motor_montadora", ""),
        faixa_montadora=regra_montadora.get("faixa", ""),
        horas_mes_montadora=regra_montadora.get("horas_mes", 0),
        intervalo_montadora=regra_montadora.get("intervalo", 0),
        intervalo_tipo_montadora=regra_montadora.get("intervalo_tipo", ""),
        meses_montadora=regra_montadora.get("meses", ""),
        horas_montadora=regra_montadora.get("horas", ""),
        alerta_montadora=regra_montadora.get("alerta", ""),
        grupo_final_recomendado=grupo_final_recomendado,
        km_mensal=km_mensal,
        km_anual=km_anual,
        velocidade_media=velocidade_media,
        meses_operacao=meses_operacao,
        intervalo_km=intervalo_km_final,
        intervalo_horas=intervalo_horas_final,
        intervalo_meses=intervalo_meses_final,
        tolerancia=tolerancia_final,
        alerta=alerta,
        justificativa=" | ".join(justificativas),
    )


def gerar_pdf(dados: dict[str, Any], resultado: Resultado) -> bytes:
    """Gera PDF final em uma página.

    v24:
    - usa renderização por imagem quando encontra VW Headline Book OTF/TTF;
    - compatível com OTF com PostScript/CFF outlines, que o ReportLab não incorpora diretamente;
    - busca a fonte em assets/ e assets/fonts/;
    - mantém uma única página e registra km mensal informado quando veículo for novo.
    """

    def localizar_fonte_vw() -> Path | None:
        candidatos = [
            ASSETS_DIR / "vw-headline-book-587ebb6c67e7e.otf",
            ASSETS_DIR / "VWHeadlineBook.otf",
            ASSETS_DIR / "VWHeadline-Book.otf",
            ASSETS_DIR / "VWHeadlineBook.ttf",
            ASSETS_DIR / "VWHeadline-Book.ttf",
            ASSETS_DIR / "fonts" / "vw-headline-book-587ebb6c67e7e.otf",
            ASSETS_DIR / "fonts" / "VWHeadlineBook.otf",
            ASSETS_DIR / "fonts" / "VWHeadline-Book.otf",
            ASSETS_DIR / "fonts" / "VWHeadlineBook.ttf",
            ASSETS_DIR / "fonts" / "VWHeadline-Book.ttf",
        ]
        for c in candidatos:
            if c.exists():
                return c
        return None

    font_file = localizar_fonte_vw()
    if font_file:
        return gerar_pdf_imagem_vw(dados, resultado, font_file)

    # Fallback vetorial com Helvetica caso a fonte não esteja disponível.
    buffer = io.BytesIO()
    page_w, page_h = A4
    left_margin = right_margin = 18
    top_margin = bottom_margin = 14
    content_w = page_w - left_margin - right_margin

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=right_margin,
        leftMargin=left_margin,
        topMargin=top_margin,
        bottomMargin=bottom_margin,
    )
    styles = getSampleStyleSheet()

    def clone_style(base: str, name: str, **kwargs):
        s = styles[base].clone(name)
        for k, v in kwargs.items():
            setattr(s, k, v)
        return s

    pdf_font = "Helvetica"
    pdf_font_bold = "Helvetica-Bold"

    title_style = clone_style("Title", "pdf_title_v24", fontName=pdf_font_bold, fontSize=15.2, leading=16.5, textColor=colors.white, alignment=0, spaceAfter=0, spaceBefore=0)
    subtitle_style = clone_style("Normal", "pdf_subtitle_v24", fontName=pdf_font, fontSize=7.8, leading=9, textColor=colors.white, alignment=0, spaceAfter=0, spaceBefore=0)
    section_style = clone_style("Heading2", "pdf_section_v24", fontName=pdf_font_bold, fontSize=10.8, leading=12.2, textColor=colors.HexColor(VW_BLUE), spaceBefore=2, spaceAfter=3)
    body_style = clone_style("Normal", "pdf_body_v24", fontName=pdf_font, fontSize=7.15, leading=8.45, textColor=colors.HexColor("#1F2937"))
    label_inline_style = clone_style("Normal", "pdf_inline_v24", fontName=pdf_font, fontSize=7.15, leading=8.45, textColor=colors.HexColor("#1F2937"))
    small_style = clone_style("Normal", "pdf_small_v24", fontName=pdf_font, fontSize=6.2, leading=7, textColor=colors.HexColor("#6B7280"))
    group_style = clone_style("Normal", "pdf_group_v24", fontName=pdf_font_bold, fontSize=13.2, leading=14.5, textColor=colors.HexColor(VW_BLUE))
    pill_style = clone_style("Normal", "pdf_pill_v24", fontName=pdf_font_bold, fontSize=6.9, leading=7.8, textColor=colors.HexColor("#667085"), alignment=1)
    pill_style_selected = clone_style("Normal", "pdf_pill_sel_v24", fontName=pdf_font_bold, fontSize=6.9, leading=7.8, textColor=colors.white, alignment=1)
    sign_style = clone_style("Normal", "pdf_sign_v24", fontName=pdf_font_bold, fontSize=6.7, leading=7.5, textColor=colors.HexColor("#6B7280"), alignment=1)
    sign_label_style = clone_style("Normal", "pdf_sign_label_v24", fontName=pdf_font, fontSize=6.3, leading=7.2, textColor=colors.HexColor("#6B7280"), alignment=1)

    story = []

    def safe(value: Any) -> str:
        return str(value if value not in (None, "") else "—")

    def pair(label: str, value: Any) -> Paragraph:
        return Paragraph(f'<font color="{VW_BLUE}"><b>{label}</b></font>&nbsp;&nbsp;{safe(value)}', label_inline_style)

    def row_box(cells: list[Any], widths: list[float], top=3.1, bottom=3.1) -> Table:
        t = Table([cells], colWidths=widths, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#C9D3DF")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), top),
            ("BOTTOMPADDING", (0, 0), (-1, -1), bottom),
        ]))
        return t

    cliente_nome = dados.get("cliente", "") or dados.get("razao_social", "") or dados.get("nome_completo", "") or ""
    documento = dados.get("documento", "")
    placa = dados.get("placa", "")
    chassi = dados.get("chassi", "")
    modelo = dados.get("modelo", "")
    cenario = dados.get("cenario", "")
    odometro = fmt_br_optional(dados.get("odometro"), " km")
    horimetro = fmt_br_optional(dados.get("horimetro"), " h")
    km_mensal_estimado = fmt_br_optional(dados.get("km_mensal_estimado"), " km/mês")

    logo_path = ASSETS_DIR / "futura_vwco_white.png"
    logo_cell = Paragraph("<font color='white'><b>Futura Caminhões | VWCO</b></font>", subtitle_style)
    if logo_path.exists():
        logo_cell = RLImage(str(logo_path), width=108, height=28)

    header = Table([[logo_cell, Paragraph("Classificação do Grupo de Manutenção", title_style)], ["", Paragraph("Definição conforme a aplicação e operação do veículo", subtitle_style)]], colWidths=[125, content_w - 125], rowHeights=[25, 14.5], hAlign="CENTER")
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(VW_BLUE)),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("SPAN", (0, 0), (0, 1)),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
    ]))
    story.append(header)
    story.append(Spacer(1, 11))

    story.append(Paragraph("1. Cliente e veículo", section_style))
    story.append(row_box([pair("CLIENTE", cliente_nome), pair("CPF/CNPJ", documento)], [content_w * 0.61, content_w * 0.39]))
    story.append(Spacer(1, 4))
    story.append(row_box([pair("Modelo", modelo), pair("Placa", placa), pair("Chassi", chassi)], [content_w * 0.26, content_w * 0.24, content_w * 0.50]))
    story.append(Spacer(1, 4))
    if str(cenario).strip().lower() == "novo":
        story.append(row_box([pair("Veículo", cenario), pair("Km mensal informado", km_mensal_estimado), pair("Odômetro", odometro), pair("Horímetro", horimetro)], [content_w * 0.20, content_w * 0.36, content_w * 0.22, content_w * 0.22]))
    else:
        story.append(row_box([pair("Veículo", cenario), pair("Odômetro", odometro), pair("Horímetro", horimetro)], [content_w / 3, content_w / 3, content_w / 3]))
    story.append(Spacer(1, 12))

    condicoes = []
    if dados.get("regiao_serrana") == "SIM": condicoes.append("Região serrana/montanhosa")
    if dados.get("paradas") == "SIM": condicoes.append("Paradas constantes")
    if dados.get("marcha_lenta") == "SIM": condicoes.append("Marcha lenta elevada")
    if dados.get("rota_curta") == "SIM": condicoes.append("Rota curta")
    if dados.get("poeira") == "SIM": condicoes.append("Poeira/lama/terra")
    condicoes_txt = "; ".join(condicoes) if condicoes else "Sem condição adicional declarada"
    fora_estrada_resp = dados.get("fora_estrada", "") or "NÃO"
    percentual_fora = "Não aplicável"
    pct = to_float(dados.get("fora_estrada_pct"))
    if pct > 0:
        percentual_fora = fmt_br_int(pct, "%")

    story.append(Paragraph("2. Operação declarada", section_style))
    story.append(row_box([pair("Aplicação", dados.get("aplicacao", "")), pair("Implemento", dados.get("implemento", ""))], [content_w * 0.58, content_w * 0.42]))
    story.append(Spacer(1, 4))
    story.append(row_box([pair("Aplicação conhecida", dados.get("aplicacao_conhecida", "")), pair("Fora de estrada", fora_estrada_resp), pair("Percentual fora de estrada", percentual_fora)], [content_w * 0.27, content_w * 0.24, content_w * 0.49]))
    story.append(Spacer(1, 4))
    story.append(row_box([pair("Condições adicionais", condicoes_txt)], [content_w], top=4, bottom=4))
    story.append(Spacer(1, 12))

    story.append(Paragraph("3. Resultado da classificação", section_style))
    grupo = resultado.grupo_final_recomendado or "—"
    controle_revisao = "POR HORAS" if grupo == "Especial" else "POR QUILOMETRAGEM"
    intervalo_base = fmt_br_optional(resultado.intervalo_horas, " h") if controle_revisao == "POR HORAS" else fmt_br_optional(resultado.intervalo_km, " km")
    result_top = Table([[Paragraph(f'<font color="{VW_BLUE}"><b>Grupo definido</b></font>', label_inline_style), Paragraph(f"<b>{grupo.upper()}</b>", group_style)]], colWidths=[100, content_w - 100])
    result_top.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    groups = ["Rodoviário", "Misto", "Severo", "Especial"]
    pill_row = []
    pill_style_cmds = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    for idx, g in enumerate(groups):
        selected = grupo == g or (grupo == "Severo ou Especial" and g in ("Severo", "Especial"))
        pill_row.append(Paragraph(f"<b>{g}</b>", pill_style_selected if selected else pill_style))
        pill_style_cmds += [("BACKGROUND", (idx, 0), (idx, 0), colors.HexColor(VW_BLUE) if selected else colors.HexColor("#EEF2F6")), ("BOX", (idx, 0), (idx, 0), 0.45, colors.HexColor("#D6DEE8") if not selected else colors.HexColor(VW_BLUE))]
    pills = Table([pill_row], colWidths=[content_w / 4] * 4)
    pills.setStyle(TableStyle(pill_style_cmds))
    result_bottom = Table([[pair("Controle de revisão", controle_revisao), pair("Intervalo base", intervalo_base)]], colWidths=[content_w * 0.55, content_w * 0.45])
    result_bottom.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, -1), 0.45, colors.HexColor("#D6DEE8")), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    result_box = Table([[result_top], [pills], [result_bottom]], colWidths=[content_w])
    result_box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#C9D3DF")), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.append(result_box)
    story.append(Spacer(1, 12))

    story.append(Paragraph("4. Declaração", section_style))
    declaracao = "Declaro que as informações prestadas, para a definição do grupo de aplicação, são verdadeiras e estou ciente de que qualquer mudança no tipo de trabalho em que o veículo for submetido que altere o grupo de aplicação, deve ser comunicada à Volkswagen Caminhões e Ônibus, através da sua rede de concessionárias, a fim de adequar os intervalos das revisões do veículo.<br/><br/>O não cumprimento das ações acima citadas isenta a Volkswagen Caminhões e Ônibus de quaisquer danos que porventura possam ocorrer devido à manutenção inadequada do veículo."
    declaracao_box = Table([[Paragraph(declaracao, body_style)]], colWidths=[content_w])
    declaracao_box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF9EA")), ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#F2B542")), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.append(declaracao_box)
    story.append(Spacer(1, 10))
    cidade_data = Table([[Paragraph("Anápolis/GO, ____ / ____ / ______.", body_style)]], colWidths=[content_w])
    cidade_data.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "RIGHT"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    story.append(cidade_data)
    story.append(Spacer(1, 20))
    assinatura_nome = cliente_nome or "Cliente / Responsável"
    assinatura = Table([["________________________________________"], [Paragraph(assinatura_nome, sign_style)], [Paragraph("Cliente / Responsável", sign_label_style)]], colWidths=[285], hAlign="CENTER")
    assinatura.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("FONTSIZE", (0, 0), (0, 0), 8), ("TEXTCOLOR", (0, 0), (0, 0), colors.HexColor(VW_BLUE)), ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    story.append(assinatura)
    story.append(Spacer(1, 13))
    footer_line = Table([[""]], colWidths=[content_w])
    footer_line.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, -1), 0.45, colors.HexColor("#D6DEE8"))]))
    story.append(footer_line)
    story.append(Spacer(1, 2))
    story.append(Paragraph("Documento gerado pelo Simulador de Classificação do Grupo de Manutenção", small_style))
    doc.build(story)
    return buffer.getvalue()


def gerar_pdf_imagem_vw(dados: dict[str, Any], resultado: Resultado, font_file: Path) -> bytes:
    """Renderiza o formulário como imagem A4 usando a fonte local.

    Necessário para fontes OTF/CFF, que não são incorporadas pelo ReportLab como TTFont.
    """
    W, H = 1240, 1754  # A4 em ~150 dpi
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    navy = (0, 30, 80)
    border = (201, 211, 223)
    text = (31, 41, 55)
    gray = (107, 114, 128)
    light = (238, 242, 246)
    yellow_bg = (255, 249, 234)
    yellow = (242, 181, 66)

    def ft(size: int):
        try:
            return ImageFont.truetype(str(font_file), size)
        except Exception:
            return ImageFont.load_default()

    f_title = ft(33)
    f_sub = ft(16)
    f_sec = ft(24)
    f_label = ft(15)
    f_body = ft(16)
    f_body_sm = ft(15)
    f_group = ft(34)
    f_foot = ft(12)

    def rounded(xy, r, fill, outline=None, width=1):
        draw.rounded_rectangle(xy, r, fill=fill, outline=outline, width=width)

    def text_len(s, font):
        return draw.textlength(str(s), font=font)

    def write(x, y, s, font, fill=text):
        draw.text((x, y), str(s), font=font, fill=fill)

    def wrap(s, font, max_w):
        words = str(s).split()
        lines = []
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            if text_len(test, font) <= max_w:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def write_wrapped(x, y, s, font, fill=text, max_w=1000, line_h=None):
        line_h = line_h or int(font.size * 1.22)
        for line in wrap(s, font, max_w):
            write(x, y, line, font, fill)
            y += line_h
        return y

    def pair_inline(x, y, label, value, max_w=None):
        write(x, y, label, f_label, navy)
        lw = text_len(label, f_label)
        return write_wrapped(x + lw + 14, y, str(value if value not in (None, "") else "—"), f_body, text, max_w=max_w or 260, line_h=19)

    def row_box(x, y, w, h, pairs):
        rounded((x, y, x+w, y+h), 8, "white", border, 1)
        cur_x = x + 18
        total = sum(p[2] for p in pairs)
        for label, value, rel in pairs:
            seg = (w - 36) * rel / total
            pair_inline(cur_x, y + (h - 18)//2, label, value, max_w=max(90, seg - 110))
            cur_x += seg
        return y + h

    cliente_nome = dados.get("cliente", "") or dados.get("razao_social", "") or dados.get("nome_completo", "") or ""
    documento = dados.get("documento", "")
    placa = dados.get("placa", "")
    chassi = dados.get("chassi", "")
    modelo = dados.get("modelo", "")
    cenario = dados.get("cenario", "")
    odometro = fmt_br_optional(dados.get("odometro"), " km")
    horimetro = fmt_br_optional(dados.get("horimetro"), " h")
    km_mensal_estimado = fmt_br_optional(dados.get("km_mensal_estimado"), " km/mês")

    # Header
    margin = 36
    rounded((margin, 26, W-margin, 110), 0, navy)
    logo_path = ASSETS_DIR / "futura_vwco_white.png"
    if logo_path.exists():
        try:
            logo = Image.open(logo_path).convert("RGBA")
            ratio = min(210/logo.width, 54/logo.height)
            logo = logo.resize((int(logo.width*ratio), int(logo.height*ratio)), Image.LANCZOS)
            img.paste(logo, (56, 42), logo)
        except Exception:
            write(56, 54, "Futura Caminhões | VWCO", f_sub, "white")
    else:
        write(56, 54, "Futura Caminhões | VWCO", f_sub, "white")
    write(315, 39, "Classificação do Grupo de Manutenção", f_title, "white")
    write(315, 78, "Definição conforme a aplicação e operação do veículo", f_sub, "white")

    x = margin
    w = W - 2*margin
    y = 138

    write(x, y, "1. Cliente e veículo", f_sec, navy); y += 35
    y = row_box(x, y, w, 38, [("CLIENTE", cliente_nome, 2.2), ("CPF/CNPJ", documento, 1.2)]) + 9
    y = row_box(x, y, w, 38, [("Modelo", modelo, 1), ("Placa", placa, 1), ("Chassi", chassi, 1.7)]) + 9
    if str(cenario).strip().lower() == "novo":
        y = row_box(x, y, w, 38, [("Veículo", cenario, 0.9), ("Km mensal informado", km_mensal_estimado, 1.8), ("Odômetro", odometro, 1.1), ("Horímetro", horimetro, 1.1)]) + 36
    else:
        y = row_box(x, y, w, 38, [("Veículo", cenario, 1), ("Odômetro", odometro, 1), ("Horímetro", horimetro, 1)]) + 36

    condicoes = []
    if dados.get("regiao_serrana") == "SIM": condicoes.append("Região serrana/montanhosa")
    if dados.get("paradas") == "SIM": condicoes.append("Paradas constantes")
    if dados.get("marcha_lenta") == "SIM": condicoes.append("Marcha lenta elevada")
    if dados.get("rota_curta") == "SIM": condicoes.append("Rota curta")
    if dados.get("poeira") == "SIM": condicoes.append("Poeira/lama/terra")
    condicoes_txt = "; ".join(condicoes) if condicoes else "Sem condição adicional declarada"
    fora_estrada_resp = dados.get("fora_estrada", "") or "NÃO"
    pct = to_float(dados.get("fora_estrada_pct"))
    percentual_fora = fmt_br_int(pct, "%") if pct > 0 else "Não aplicável"

    write(x, y, "2. Operação declarada", f_sec, navy); y += 35
    y = row_box(x, y, w, 38, [("Aplicação", dados.get("aplicacao", ""), 1.7), ("Implemento", dados.get("implemento", ""), 1.3)]) + 9
    y = row_box(x, y, w, 38, [("Aplicação conhecida", dados.get("aplicacao_conhecida", ""), 1.1), ("Fora de estrada", fora_estrada_resp, 1), ("Percentual fora de estrada", percentual_fora, 1.7)]) + 9
    y = row_box(x, y, w, 48, [("Condições adicionais", condicoes_txt, 1)]) + 36

    grupo = resultado.grupo_final_recomendado or "—"
    controle_revisao = "POR HORAS" if grupo == "Especial" else "POR QUILOMETRAGEM"
    intervalo_base = fmt_br_optional(resultado.intervalo_horas, " h") if controle_revisao == "POR HORAS" else fmt_br_optional(resultado.intervalo_km, " km")

    write(x, y, "3. Resultado da classificação", f_sec, navy); y += 35
    box_y = y
    rounded((x, y, x+w, y+130), 8, "white", border, 1)
    pair_inline(x+20, y+18, "Grupo definido", "")
    write(x+235, y+12, grupo.upper(), f_group, navy)

    pills_y = y + 59
    names = ["Rodoviário", "Misto", "Severo", "Especial"]
    pill_w = (w - 60) / 4
    px = x + 30
    for name in names:
        selected = grupo == name or (grupo == "Severo ou Especial" and name in ("Severo", "Especial"))
        fill = navy if selected else light
        txtc = "white" if selected else gray
        draw.rectangle((px, pills_y, px+pill_w, pills_y+30), fill=fill, outline=border)
        tw = text_len(name, f_label)
        write(px + (pill_w-tw)/2, pills_y+7, name, f_label, txtc)
        px += pill_w
    draw.line((x+30, y+99, x+w-30, y+99), fill=border, width=1)
    pair_inline(x+30, y+109, "Controle de revisão", controle_revisao, 320)
    pair_inline(x+670, y+109, "Intervalo base", intervalo_base, 200)
    y += 166

    write(x, y, "4. Declaração", f_sec, navy); y += 35
    decl = (
        "Declaro que as informações prestadas, para a definição do grupo de aplicação, são verdadeiras e estou ciente de que qualquer mudança no tipo de trabalho em que o veículo for submetido que altere o grupo de aplicação, deve ser comunicada à Volkswagen Caminhões e Ônibus, através da sua rede de concessionárias, a fim de adequar os intervalos das revisões do veículo.\n\n"
        "O não cumprimento das ações acima citadas isenta a Volkswagen Caminhões e Ônibus de quaisquer danos que porventura possam ocorrer devido à manutenção inadequada do veículo."
    )
    rounded((x, y, x+w, y+126), 0, yellow_bg, yellow, 2)
    yy = y + 16
    for paragraph in decl.split("\n\n"):
        yy = write_wrapped(x+18, yy, paragraph, f_body_sm, text, max_w=w-36, line_h=18)
        yy += 11
    y += 151


    date_txt = "Anápolis/GO, ____ / ____ / ______."
    write(x+w-text_len(date_txt, f_body), y, date_txt, f_body, text); y += 70

    line_w = 380
    line_x = x + (w-line_w)/2
    draw.line((line_x, y, line_x+line_w, y), fill=navy, width=2)
    sig_name = cliente_nome or "Cliente / Responsável"
    tw = text_len(sig_name, f_body_sm)
    write(line_x+(line_w-tw)/2, y+16, sig_name, f_body_sm, gray)
    tw = text_len("Cliente / Responsável", f_foot)
    write(line_x+(line_w-tw)/2, y+39, "Cliente / Responsável", f_foot, gray)

    footer_y = H - 78
    draw.line((x, footer_y, x+w, footer_y), fill=border, width=1)
    write(x, footer_y+30, "Documento gerado pelo Simulador de Classificação do Grupo de Manutenção", f_foot, gray)

    out = io.BytesIO()
    img.save(out, format="PDF", resolution=150.0)
    return out.getvalue()




# Autenticação simples — v27
def _get_auth_users() -> dict[str, str]:
    """Lê usuários autorizados do Streamlit Secrets.

    Formato recomendado em App settings > Secrets:
    [auth.users]
    lazaro = "senha_forte"
    consultor1 = "outra_senha"

    Formato alternativo:
    [auth]
    usuario = "lazaro"
    senha = "senha_forte"
    """
    users: dict[str, str] = {}
    try:
        auth_cfg = st.secrets.get("auth", {})
        if hasattr(auth_cfg, "get"):
            users_cfg = auth_cfg.get("users", {})
            if hasattr(users_cfg, "items"):
                users.update({str(k): str(v) for k, v in users_cfg.items()})
            usuario = auth_cfg.get("usuario", "")
            senha = auth_cfg.get("senha", "")
            if usuario and senha:
                users[str(usuario)] = str(senha)
    except Exception:
        users = {}

    return users


def tela_login() -> bool:
    """Bloqueia o simulador até o usuário autenticar."""
    if "auth_ok" not in st.session_state:
        st.session_state["auth_ok"] = False
    if "auth_user" not in st.session_state:
        st.session_state["auth_user"] = ""

    if st.session_state.get("auth_ok"):
        col_user, col_logout = st.columns([4, 1])
        with col_user:
            st.caption(f"Acesso autenticado: **{st.session_state.get('auth_user', '')}**")
        with col_logout:
            if st.button("Sair", type="secondary"):
                st.session_state["auth_ok"] = False
                st.session_state["auth_user"] = ""
                st.rerun()
        return True

    logo_uri = asset_data_uri("futura_vwco_white.png")
    logo_html = f'<img src="{logo_uri}" class="login-logo" />' if logo_uri else '<div class="login-logo-text">Futura / VWCO</div>'

    st.markdown(
        f"""
        <div class="login-shell">
            <div class="login-brand-card">
                {logo_html}
                <div class="login-title">Login</div>
                <div class="login-subtitle">Acesso ao Simulador de Classificação de Grupo de Manutenção</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("login_form"):
        usuario = st.text_input("E-mail ou usuário")
        senha = st.text_input("Senha", type="password")
        entrar = st.form_submit_button("Entrar", type="primary")

    if entrar:
        users = _get_auth_users()
        if usuario in users and senha == users[usuario]:
            st.session_state["auth_ok"] = True
            st.session_state["auth_user"] = usuario
            st.rerun()
        else:
            st.error("Usuário ou senha inválidos.")

    if not _get_auth_users():
        st.error("Nenhum usuário autorizado foi encontrado. Configure [auth.users] no Streamlit Secrets.")
    return False


# UI
st.set_page_config(page_title="Simulador Grupo de Manutenção", page_icon="🚚", layout="wide")

if not tela_login():
    st.stop()

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1.25rem;
            padding-bottom: 2.5rem;
            max-width: 1180px;
        }
        .main-header {
            background: linear-gradient(90deg, #001E50 0%, #003B73 100%);
            padding: 18px 22px;
            border-radius: 14px;
            margin-bottom: 18px;
            display: flex;
            align-items: center;
            gap: 20px;
            box-shadow: 0 6px 18px rgba(0, 30, 80, 0.14);
        }
        .main-header-logo {
            width: 188px;
            max-height: 64px;
            object-fit: contain;
        }
        .main-header h1 {
            color: #FFFFFF;
            font-size: 1.95rem;
            margin: 0;
            line-height: 1.15;
            font-weight: 700;
        }
        .login-shell {
            display: flex;
            justify-content: center;
            margin-top: 3.5rem;
            margin-bottom: 1.2rem;
        }
        .login-brand-card {
            width: 460px;
            background: #FFFFFF;
            border-radius: 18px;
            box-shadow: 0 10px 30px rgba(0, 30, 80, 0.16);
            padding: 26px 32px 30px 32px;
            border: 1px solid #E5E7EB;
            text-align: center;
        }
        .login-logo {
            max-width: 280px;
            max-height: 86px;
            background: #001E50;
            border-radius: 12px;
            padding: 14px 18px;
            object-fit: contain;
            margin-bottom: 18px;
        }
        .login-logo-text {
            color: #001E50;
            font-size: 1.35rem;
            font-weight: 700;
            margin-bottom: 18px;
        }
        .login-title {
            background: #2F86C7;
            color: #FFFFFF;
            font-size: 1.65rem;
            font-weight: 700;
            border-radius: 8px;
            padding: 14px;
            margin: 0 auto 18px auto;
        }
        .login-subtitle {
            color: #4B5563;
            font-size: 0.92rem;
            margin-bottom: 2px;
        }
        .stButton > button[kind="primary"],
        .stFormSubmitButton > button[kind="primary"] {
            background-color: #001E50;
            border-color: #001E50;
            color: #FFFFFF;
            border-radius: 10px;
            font-weight: 700;
        }
        .stButton > button[kind="primary"]:hover,
        .stFormSubmitButton > button[kind="primary"]:hover {
            background-color: #003B73;
            border-color: #003B73;
            color: #FFFFFF;
        }
        .stButton > button {
            border-radius: 10px;
            font-weight: 600;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.55rem;
        }
        div[data-testid="stExpander"] {
            border-radius: 12px;
        }
        hr {
            margin: 1.2rem 0;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


logo_uri = asset_data_uri("futura_vwco_white.png")
logo_html = f'<img src="{logo_uri}" class="main-header-logo" />' if logo_uri else '<div style="color:white;font-weight:700;">Futura / VWCO</div>'
st.markdown(
    f"""
    <div class="main-header">
        {logo_html}
        <h1>Classificação de grupo de manutenção</h1>
    </div>
    """,
    unsafe_allow_html=True,
)

data = load_data()
base_modelos = data["base_modelos"]
aplicacoes = data["aplicacoes"]
implementos = data["implementos"]
intervalos = data["intervalos"]

for col in ["Score"]:
    aplicacoes[col] = pd.to_numeric(aplicacoes[col], errors="coerce").fillna(0)
    implementos[col] = pd.to_numeric(implementos[col], errors="coerce").fillna(0)

modelos = sorted(base_modelos["Modelo"].dropna().astype(str).tolist())
apps = sorted(aplicacoes["Aplicação"].dropna().astype(str).tolist())
imps = sorted(implementos["Implemento"].dropna().astype(str).tolist())

with st.sidebar:
    st.header("Base de regras")
    st.caption("As regras vêm dos arquivos CSV gerados a partir do simulador Excel.")
    show_rules = st.toggle("Exibir bases de regras", value=False)


st.subheader("1. Dados do cliente e veículo")

RESET_DEFAULTS = {
    # Cliente e veículo
    "informar_cliente": "NÃO",
    "tipo_cliente": "Pessoa Jurídica",
    "cnpj_input": "",
    "cpf_input": "",
    "cliente_input": "",
    "razao_social_auto": "",
    "nome_pf_auto": "",
    "cnpj_consultado": "",
    "cnpj_info": {},
    "cpf_consultado": "",
    "cpf_info": {},
    "placa_input": "",
    "chassi_input": "",
    "modelo_select": "Selecione o modelo",
    "cenario_select": "Selecione tipo de veículo",
    # Dados de rodagem
    "km_mensal_estimado": 0,
    "mes_venda_label": MONTH_OPTIONS[0][1],
    "ano_venda": max(2000, date.today().year - 1),
    "odometro_input": 0,
    "horimetro_input": 0,
    # Operação
    "aplicacao_select": "Selecione aplicação",
    "implemento_select": "Selecione implemento",
    "aplicacao_conhecida": None,
    "pavimento_100": None,
    "fora_estrada": None,
    "fora_estrada_pct": 0.0,
    "regiao_serrana": None,
    "paradas": None,
    "marcha_lenta": None,
    "rota_curta": None,
    "poeira": None,
    # Resultado/validação manual
    "grupo_manual": "",
}

def resetar_simulador():
    """Restaura explicitamente todos os widgets ao estado inicial.

    Não usamos apenas st.session_state.clear(), porque o Streamlit pode preservar
    valores de widgets no navegador quando as chaves permanecem iguais.
    """
    for chave in list(st.session_state.keys()):
        if chave not in RESET_DEFAULTS:
            del st.session_state[chave]
    for chave, valor in RESET_DEFAULTS.items():
        st.session_state[chave] = valor

limpar_col1, limpar_col2 = st.columns([4, 1])
with limpar_col2:
    if st.button("Limpar dados", type="primary", use_container_width=True):
        resetar_simulador()
        st.rerun()


informar_cliente = st.radio(
    "Deseja informar os dados do cliente?",
    ["SIM", "NÃO"],
    horizontal=True,
    key="informar_cliente",
)

if informar_cliente == "NÃO":
    st.info(
        "Simulação sem dados do cliente: os campos de cliente, CPF/CNPJ, placa e chassi podem ficar em branco. "
        "Nesta condição, será possível simular pelo modelo, mas não será possível gerar PDF por falta de dados cadastrais."
    )
    tipo_cliente = ""
    documento = ""
    cliente = ""
else:
    c1, c2 = st.columns([1, 2])
    with c1:
        tipo_cliente = st.radio("Tipo de cliente", ["Pessoa Jurídica", "Pessoa Física"], horizontal=True, key="tipo_cliente")
    with c2:
        if tipo_cliente == "Pessoa Jurídica":
            documento = st.text_input("CNPJ", placeholder="00.000.000/0000-00", max_chars=18, key="cnpj_input")
            cnpj_digits = digits_only(documento)
            if cnpj_digits and len(cnpj_digits) >= 14 and not validar_cnpj(cnpj_digits):
                st.warning("CNPJ inválido. Corrija o número ou revise o cadastro digitado.")
            cliente = st.text_input("Razão social", key="cliente_input")
        else:
            documento = st.text_input("CPF", placeholder="000.000.000-00", max_chars=14, key="cpf_input")
            cpf_digits = digits_only(documento)
            if cpf_digits and len(cpf_digits) >= 11 and not validar_cpf(cpf_digits):
                st.warning("CPF inválido. Corrija o número ou revise o cadastro digitado.")
            cliente = st.text_input("Nome completo", key="cliente_input")

# Veículo — preenchimento manual
c1, c2 = st.columns(2)
with c1:
    placa_digitada = st.text_input("Placa", placeholder="ABC1D23 ou ABC-1234", max_chars=8, key="placa_input").upper()
with c2:
    chassi_digitado = st.text_input(
        "Chassi",
        placeholder="17 caracteres",
        max_chars=17,
        key="chassi_input",
    ).upper()

placa_final = normalizar_placa(placa_digitada)
chassi_final = normalizar_chassi(chassi_digitado)

c1, c2 = st.columns(2)
with c1:
    modelo_options = ["Selecione o modelo"] + modelos
    modelo = st.selectbox("Modelo", modelo_options, key="modelo_select")
with c2:
    cenario = st.selectbox("Veículo", ["Selecione tipo de veículo", "Novo", "Usado"], key="cenario_select")

if modelo != "Selecione o modelo":
    modelo_row = base_modelos[base_modelos["Modelo"] == modelo].iloc[0]
    familia = modelo_row["Família"]
    motorizacao = modelo_row["Motorização/Referência"]
    segmento = modelo_row["Segmento"]
    st.info(f"Família: **{familia}** | Motorização: **{motorizacao}** | Segmento: **{segmento}**")
    motor_montadora = motor_montadora_padrao(motorizacao, modelo)
else:
    familia = ""
    motorizacao = ""
    segmento = ""
    motor_montadora = ""
    st.warning("Selecione o modelo para liberar a simulação de enquadramento.")

st.subheader("2. Dados de rodagem")
if cenario == "Selecione tipo de veículo":
    st.info("Selecione o tipo de veículo para liberar os dados de rodagem.")
    km_mensal_estimado = 0
    faixa_velocidade_estimativa = ""
    data_venda = ""
    odometro = 0
    horimetro = 0
elif cenario == "Novo":
    st.caption("Para veículo novo, o cálculo utiliza a quilometragem mensal estimada. O controle por horas e a faixa de velocidade da régua da montadora serão avaliados após início da operação.")
    km_mensal_estimado = st.number_input("Quilometragem mensal estimada", min_value=0, step=500, value=0, format="%d", key="km_mensal_estimado")
    faixa_velocidade_estimativa = ""
    data_venda = ""
    odometro = 0
    horimetro = 0
else:
    st.caption("Para veículo usado, a média mensal e a relação km/h são calculadas com data de venda, odômetro e horímetro atuais. A faixa de velocidade da régua da montadora é definida automaticamente.")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        mes_venda_label = st.selectbox("Mês da venda", [label for _, label in MONTH_OPTIONS], index=0, key="mes_venda_label")
    with c2:
        ano_venda = st.number_input("Ano da venda", min_value=2000, max_value=date.today().year, step=1, value=max(2000, date.today().year - 1), format="%d", key="ano_venda")
    with c3:
        odometro = st.number_input("Odômetro atual (km)", min_value=0, step=1000, value=0, format="%d", key="odometro_input")
    with c4:
        horimetro = st.number_input("Horímetro atual (h)", min_value=0, step=100, value=0, format="%d", key="horimetro_input")
    if odometro > 0 and horimetro > 0:
        velocidade_previa = odometro / horimetro
        _, faixa_previa, _ = faixa_por_velocidade(velocidade_previa, "")
        st.info(
            f"Faixa de velocidade da régua da montadora calculada automaticamente: "
            f"**{faixa_previa}** | Relação: **{fmt_br_int(velocidade_previa, ' km/h')}**"
        )
    else:
        st.caption("A faixa de velocidade da régua da montadora será calculada automaticamente após informar odômetro e horímetro.")
    mes_venda_num = dict((label, number) for number, label in MONTH_OPTIONS)[mes_venda_label]
    data_venda = f"{mes_venda_num:02d}/{int(ano_venda)}"
    km_mensal_estimado = 0
    faixa_velocidade_estimativa = ""

st.subheader("3. Condições de operação")
c1, c2 = st.columns(2)
with c1:
    aplicacao = st.selectbox("Aplicação", ["Selecione aplicação"] + apps, key="aplicacao_select")
    implemento = st.selectbox("Implemento", ["Selecione implemento"] + imps, key="implemento_select")
    aplicacao_conhecida = st.radio("Aplicação conhecida?", ["SIM", "NÃO"], horizontal=True, index=None, key="aplicacao_conhecida")
    pavimento_100 = st.radio("Pavimento 100% asfaltado?", ["SIM", "NÃO"], horizontal=True, index=None, key="pavimento_100")
    fora_estrada = st.radio("Fora de estrada?", ["SIM", "NÃO"], horizontal=True, index=None, key="fora_estrada")
    if fora_estrada == "SIM":
        fora_estrada_pct = st.number_input("Fora de estrada (%)", min_value=0.0, max_value=100.0, step=5.0, value=0.0, key="fora_estrada_pct")
    else:
        fora_estrada_pct = 0.0
with c2:
    regiao_serrana = st.radio("Região serrana/montanhosa?", ["SIM", "NÃO"], horizontal=True, index=None, key="regiao_serrana")
    paradas = st.radio("Paradas constantes?", ["SIM", "NÃO"], horizontal=True, index=None, key="paradas")
    marcha_lenta = st.radio("Marcha lenta elevada?", ["SIM", "NÃO"], horizontal=True, index=None, key="marcha_lenta")
    rota_curta = st.radio("Rota curta?", ["SIM", "NÃO"], horizontal=True, index=None, key="rota_curta")
    poeira = st.radio("Poeira/lama/terra?", ["SIM", "NÃO"], horizontal=True, index=None, key="poeira")

grupo_manual = st.selectbox(
    "Grupo validado manualmente (opcional)",
    ["", "Rodoviário", "Misto", "Severo", "Severo ou Especial", "Especial", "Não enquadrar"],
    key="grupo_manual",
)

submitted = st.button("Calcular enquadramento", type="primary")

if submitted:
    documento_formatado = digits_only(documento)
    chassi_formatado = normalizar_chassi(chassi_final)
    placa_formatada = normalizar_placa(placa_final)
    dados = {
        "informar_cliente": informar_cliente,
        "tipo_cliente": tipo_cliente,
        "cliente": cliente,
        "documento": documento_formatado,
        "chassi": chassi_formatado,
        "placa": placa_formatada,
        "modelo": modelo,
        "cenario": cenario,
        "motor_montadora": motor_montadora,
        "faixa_velocidade_estimativa": faixa_velocidade_estimativa,
        "km_mensal_estimado": km_mensal_estimado,
        "data_venda": data_venda,
        "odometro": odometro,
        "horimetro": horimetro,
        "aplicacao": aplicacao,
        "implemento": implemento,
        "aplicacao_conhecida": aplicacao_conhecida,
        "pavimento_100": pavimento_100,
        "fora_estrada": fora_estrada,
        "fora_estrada_pct": fora_estrada_pct,
        "regiao_serrana": regiao_serrana,
        "paradas": paradas,
        "marcha_lenta": marcha_lenta,
        "rota_curta": rota_curta,
        "poeira": poeira,
        "grupo_manual": grupo_manual,
    }

    erros = validar_formulario_cliente(dados)
    if erros:
        st.error("Corrija os campos obrigatórios antes de calcular:")
        for erro in erros:
            st.write(f"- {erro}")
        st.stop()

    resultado = calcular_resultado(dados, base_modelos, aplicacoes, implementos, intervalos)

    st.subheader("Resultado")
    st.metric("Grupo sugerido", resultado.grupo_final_recomendado or "—")

    observacoes_resultado = []
    if resultado.grupo_plano and resultado.grupo_plano not in {"Transição", resultado.grupo_final_recomendado}:
        observacoes_resultado.append(
            f"Pela tabela do plano de manutenção, considerando apenas a quilometragem mensal, a orientação seria **{resultado.grupo_plano}**. "
            f"O grupo sugerido ficou **{resultado.grupo_final_recomendado}** pela análise operacional/montadora."
        )
    if dados.get("aplicacao_conhecida") == "NÃO":
        observacoes_resultado.append(
            "Não é possível sugerir o grupo correto sem informações reais da operação. "
            f"A indicação apresentada considera apenas a quilometragem mensal pela tabela do plano de manutenção: **{resultado.grupo_plano or 'não definido'}**."
        )
    if resultado.grupo_montadora and resultado.grupo_montadora != resultado.grupo_final_recomendado:
        observacoes_resultado.append(
            f"A régua da montadora indicou **{resultado.grupo_montadora}**. Essa divergência deve ser analisada na validação técnica."
        )

    if observacoes_resultado:
        for obs in observacoes_resultado:
            st.info(obs)
    else:
        st.caption("O grupo sugerido consolida a régua da montadora, a tabela do plano de manutenção e a análise operacional Futura.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Média mensal calculada", fmt_br_int(resultado.km_mensal, " km/mês"))
    c2.metric("Km anual estimada", fmt_br_int(resultado.km_anual, " km/ano"))
    c3.metric("Relação km/h", "—" if resultado.velocidade_media is None else fmt_br_int(resultado.velocidade_media, " km/h"))
    c4.metric("Intervalo estimado", fmt_intervalo_meses(resultado.intervalo_meses))

    with st.expander("Detalhamento técnico — régua da montadora, rodagem e score", expanded=False):
        d1, d2, d3 = st.columns(3)
        d1.metric("Faixa velocidade", resultado.faixa_montadora or "—")
        d2.metric("Horas mês estimadas", fmt_br_int(resultado.horas_mes_montadora, " h/mês") if resultado.horas_mes_montadora else "—")
        d3.metric("Score operacional", fmt_br_int(resultado.score_total, "/100"))

        st.subheader("Régua da montadora")
        st.table(pd.DataFrame([
        {"Campo": "Grupo pela montadora", "Valor": resultado.grupo_montadora or ""},
        {"Campo": "Faixa de velocidade", "Valor": resultado.faixa_montadora or ""},
        {"Campo": "Horas mensais estimadas", "Valor": fmt_br_optional(resultado.horas_mes_montadora, " h/mês")},
        {"Campo": "Intervalo montadora", "Valor": fmt_br_optional(resultado.intervalo_montadora, " " + resultado.intervalo_tipo_montadora)},
        {"Campo": "Intervalo estimado montadora", "Valor": fmt_intervalo_meses(resultado.meses_montadora) if resultado.meses_montadora else ""},
        {"Campo": "Horas entre revisões", "Valor": resultado.horas_montadora or ""},
        {"Campo": "Alerta", "Valor": resultado.alerta_montadora or ""},
    ]))

    if dados["cenario"] == "Usado":
        st.subheader("Dados calculados do veículo usado")
        st.table(pd.DataFrame([
            {"Campo": "Data de venda considerada", "Valor": dados.get("data_venda", "")},
            {"Campo": "Meses em operação", "Valor": resultado.meses_operacao},
            {"Campo": "Odômetro atual", "Valor": fmt_br_int(to_float(dados.get('odometro')), " km")},
            {"Campo": "Horímetro atual", "Valor": fmt_br_int(to_float(dados.get('horimetro')), " h")},
            {"Campo": "Média mensal", "Valor": fmt_br_int(resultado.km_mensal, " km/mês")},
            {"Campo": "Relação km/h", "Valor": "—" if resultado.velocidade_media is None else fmt_br_int(resultado.velocidade_media, " km/h")},
        ]))

    st.warning(resultado.alerta)
    st.write("**Justificativa:**", resultado.justificativa or "—")

    st.subheader("Intervalos")
    st.table(pd.DataFrame([
        {"Campo": "Intervalo de revisão (km)", "Valor": fmt_br_optional(resultado.intervalo_km, " km")},
        {"Campo": "Intervalo de revisão (horas)", "Valor": fmt_br_optional(resultado.intervalo_horas, " h")},
        {"Campo": "Tolerância de revisão (km)", "Valor": resultado.tolerancia or ""},
    ]))

    st.subheader("Composição do score")
    st.dataframe(pd.DataFrame([
        {"Critério": "Aplicação", "Score": round(resultado.score_aplicacao), "Peso máximo": 20},
        {"Critério": "Quilometragem anual/mensal", "Score": round(resultado.score_km), "Peso máximo": 20},
        {"Critério": "Via / fora de estrada", "Score": round(resultado.score_via), "Peso máximo": 15},
        {"Critério": "Condição operacional", "Score": round(resultado.score_operacional), "Peso máximo": 25},
        {"Critério": "Implemento", "Score": round(resultado.score_implemento), "Peso máximo": 20},
    ]), hide_index=True, use_container_width=True)

    if informar_cliente == "SIM":
        pdf_bytes = gerar_pdf(dados, resultado)
        st.download_button(
            "Baixar formulário em PDF",
            data=pdf_bytes,
            file_name="formulario_enquadramento_manutencao.pdf",
            mime="application/pdf",
        )
    else:
        st.info("PDF não disponível nesta simulação, pois os dados do cliente/veículo não foram informados.")
else:
    st.info("Preencha o formulário e clique em **Calcular enquadramento**.")

if show_rules:
    st.divider()
    st.subheader("Bases de regras")
    tabs = st.tabs(["Modelos", "Aplicações", "Implementos", "Intervalos", "Plano", "Clientes"] )
    with tabs[0]:
        st.dataframe(base_modelos, use_container_width=True)
    with tabs[1]:
        st.dataframe(aplicacoes, use_container_width=True)
    with tabs[2]:
        st.dataframe(implementos, use_container_width=True)
    with tabs[3]:
        st.dataframe(intervalos, use_container_width=True)
    with tabs[4]:
        st.dataframe(data["plano_contratos"], use_container_width=True)
    with tabs[5]:
        st.dataframe(base_clientes, use_container_width=True)
