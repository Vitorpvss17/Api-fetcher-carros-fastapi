from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
import re
import logging
import time
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup 

log = logging.getLogger(__name__)

BASE_URL = "https://www.olx.com.br/autos-e-pecas/carros-vans-e-utilitarios/"

@dataclass
class OlxListing:
    id: str
    title: str
    url: str
    modelo: Optional[str]
    ano: Optional[int]
    cidade: Optional[str]
    preco: Optional[float]
    km: Optional[int]
    cambio: Optional[str]
    combustivel: Optional[str]
    fonte: str = "olx"
    data_coleta: float = time.time()


def _slugify_city(cidade: str | None) -> str | None:
    if not cidade:
        return None
    return (
        cidade.lower()
        .strip()
        .replace(" ", "-")
        .replace("á", "a")
        .replace("ã", "a")
        .replace("â", "a")
        .replace("é", "e")
        .replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ô", "o")
        .replace("õ", "o")
        .replace("ú", "u")
        .replace("ç", "c")
    )


def _build_search_url(modelo: str, ano: Optional[int] = None, cidade: Optional[str] = None) -> str:
    """
    Monta uma URL de busca da OLX para carros.
    Aqui usamos uma URL genérica com o parâmetro q (texto livre).
    Se quiser ficar mais específico por estado/região, pode adaptar depois.
    """
    query_parts = [modelo]
    if ano:
        query_parts.append(str(ano))

    q = quote_plus(" ".join(query_parts))

    # caminho genérico para carros
    path = "/autos-e-pecas/carros-vans-e-utilitarios"

    # cidade ainda não está sendo usada no path; você pode refinar isso depois
    city_slug = _slugify_city(cidade)
    if city_slug:
        # Exemplo futuro:
        # path = f"/al/maceio-e-regiao/autos-e-pecas/carros-vans-e-utilitarios"
        # mas isso varia de estado pra estado; começamos simples
        pass

    url = f"{BASE_URL}{path}?q={q}"
    return url


def _parse_price(text: str | None) -> Optional[float]:
    if not text:
        return None
    txt = text.replace("R$", "").replace(".", "").replace(" ", "").strip()
    txt = txt.replace(",", ".")
    m = re.search(r"(\d+(\.\d+)?)", txt)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _parse_km(text: str | None) -> Optional[int]:
    if not text:
        return None
    # algo tipo "73.000 km"
    m = re.search(r"(\d[\d\.]*)\s*km", text.lower())
    if not m:
        return None
    val = m.group(1).replace(".", "")
    try:
        return int(val)
    except ValueError:
        return None


def _parse_year_from_title(title: str | None) -> Optional[int]:
    if not title:
        return None
    m = re.search(r"\b(19|20)\d{2}\b", title)
    if not m:
        return None
    try:
        return int(m.group(0))
    except ValueError:
        return None


def search_olx(
    modelo: str,
    ano: Optional[int] = None,
    cidade: Optional[str] = None,
    max_price: Optional[float] = None,
    max_items: int = 50,
) -> List[OlxListing]:
    """
    Busca simples na página de resultados da OLX.
    - Faz 1 requisição HTTP à página de busca.
    - Lê os cards de anúncio (section.olx-adcard).
    - Extrai título, preço, localização, km, etc.
    - Filtra por max_price se fornecido.
    - Limita a max_items resultados.
    """
    url = _build_search_url(modelo, ano=ano, cidade=cidade)
    log.info("Buscando OLX: %s", url)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15)
    except Exception as e:
        log.exception("Erro de rede acessando OLX: %s", e)
        return []

    if resp.status_code != 200:
        log.warning("OLX respondeu %s para %s", resp.status_code, url)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Cards de anúncio
    cards = soup.select("section.olx-adcard")
    results: List[OlxListing] = []

    for card in cards:
        try:
            # Título
            title_el = card.select_one("h2.olx-adcard__title")
            title = (title_el.get_text(strip=True) if title_el else "").strip()

            # Link
            link_el = card.select_one("a.olx-adcard__link")
            url_rel = (
                link_el["href"]
                if link_el is not None and link_el.has_attr("href")
                else ""
            )
            if url_rel.startswith("/"):
                url_full = BASE_URL + url_rel
            else:
                url_full = url_rel

            # ID (se a OLX expor data-id em outro nível, você pode usar; aqui usamos a URL)
            ad_id = card.get("data-id") or url_full

            # Preço
            price_el = card.select_one("h3.olx-adcard__price")
            preco = _parse_price(price_el.get_text(strip=True) if price_el else None)

            # Localização / cidade
            loc_el = card.select_one("p.olx-adcard__location")
            cidade_txt: Optional[str] = None
            if loc_el:
                raw_loc = loc_el.get_text(" ", strip=True)  # "Aracaju, São Conrado"
                cidade_txt = raw_loc.split(",")[0].strip() if raw_loc else None

            # Ano (se não veio por parâmetro já filtrando, tenta inferir do título)
            year = ano or _parse_year_from_title(title)

            # Detalhes (km, câmbio, combustível, etc.)
            detail_elems = card.select("div.olx-adcard__detail")
            chips = [d.get_text(" ", strip=True).lower() for d in detail_elems]

            km_val: Optional[int] = None
            cambio: Optional[str] = None
            combustivel: Optional[str] = None

            for chip in chips:
                if "km" in chip:
                    km_val = _parse_km(chip)
                elif "manual" in chip or "automático" in chip or "automatica" in chip:
                    cambio = chip
                elif any(
                    x in chip
                    for x in ["flex", "gasolina", "diesel", "álcool", "alcool", "etanol"]
                ):
                    combustivel = chip

            listing = OlxListing(
                id=str(ad_id),
                title=title or f"{modelo} {year or ''}",
                url=url_full,
                modelo=modelo.upper(),
                ano=year,
                cidade=cidade_txt or cidade,
                preco=preco,
                km=km_val,
                cambio=cambio,
                combustivel=combustivel,
            )

            if max_price is not None and listing.preco is not None:
                if listing.preco > max_price:
                    # descarta acima do teto
                    continue

            results.append(listing)
            if len(results) >= max_items:
                break

        except Exception as e:
            log.exception("Erro parseando card OLX: %s", e)
            continue

    return results

    
