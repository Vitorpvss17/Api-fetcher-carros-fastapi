from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from olx_client import search_olx, OlxListing
from pydantic import BaseModel
from typing import List, Optional
import time
import math
import os
import statistics

API_KEY = os.getenv("API_KEY", "dev-key")  # <-- lê da env

app = FastAPI(title="Fetcher API (mock)", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Listing(BaseModel):
    id: str
    title: str
    url: str
    modelo: Optional[str] = None
    ano: Optional[int] = None
    cidade: Optional[str] = None
    preco: Optional[float] = None
    km: Optional[int] = None
    cambio: Optional[str] = None
    combustivel: Optional[str] = None
    data_coleta: Optional[float] = None
    fonte: str = "olx"

class SearchResponse(BaseModel):
    items: List[Listing]
    count: int
    next_page: Optional[int] = None

class StatsResponse(BaseModel):
    n: int
    media: Optional[float] = None
    mediana: Optional[float] = None
    p25: Optional[float] = None
    p75: Optional[float] = None
    updated_at: float

def _check_api_key(x_api_key: str | None):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

@app.get("/health")
def health():
    return {"status": "ok", "ts": time.time()}

@app.get("/stats", response_model=StatsResponse)
def stats(
    modelo: str,
    ano: int | None = None,
    cidade: str | None = None,
    x_api_key: str | None = Header(default=None),
):
    _check_api_key(x_api_key)
    base = 55000 if ano is None else max(35000, 60000 - (2025 - (ano or 2020)) * 2000)
    return StatsResponse(
        n=62,
        media=base,
        mediana=base * 0.98,
        p25=base * 0.93,
        p75=base * 1.05,
        updated_at=time.time(),
    )

@app.get("/search", response_model=SearchResponse)
def search(
    modelo: str,
    ano: int | None = None,
    cidade: str | None = None,
    max_price: float | None = None,
    page: int = 1,
    x_api_key: str | None = Header(default=None),
):
    _check_api_key(x_api_key)

    # Por enquanto, trazemos max 80 itens da primeira página
    raw_listings: List[OlxListing] = search_olx(
        modelo=modelo,
        ano=ano,
        cidade=cidade,
        max_price=max_price,
        max_items=80,
    )

    # Se quiser fazer paginação "fake" do lado do servidor:
    page_size = 20
    start = (page - 1) * page_size
    end = start + page_size
    page_items = raw_listings[start:end]

    # Converte OlxListing -> seu modelo Listing (Pydantic)
    items = [
        Listing(
            id=l.id,
            title=l.title,
            url=l.url,
            modelo=l.modelo,
            ano=l.ano,
            cidade=l.cidade,
            preco=l.preco,
            km=l.km,
            cambio=l.cambio,
            combustivel=l.combustivel,
            data_coleta=l.data_coleta,
            fonte=l.fonte,
        )
        for l in page_items
    ]

    next_page: Optional[int] = None
    if end < len(raw_listings):
        next_page = page + 1

    return SearchResponse(
        items=items,
        count=len(raw_listings),
        next_page=next_page,
    )

@app.get("/stats", response_model=StatsResponse)
def stats(
    modelo: str,
    ano: int | None = None,
    cidade: str | None = None,
    x_api_key: str | None = Header(default=None),
):
    _check_api_key(x_api_key)

    listings: List[OlxListing] = search_olx(
        modelo=modelo,
        ano=ano,
        cidade=cidade,
        max_price=None,
        max_items=80,
    )

    prices = [l.preco for l in listings if l.preco is not None]

    if not prices:
        return StatsResponse(
            n=0,
            media=None,
            mediana=None,
            p25=None,
            p75=None,
            updated_at=time.time(),
        )

    prices_sorted = sorted(prices)
    n = len(prices_sorted)
    media = float(statistics.mean(prices_sorted))
    mediana = float(statistics.median(prices_sorted))

    def percentile(p: float) -> float:
        # p de 0 a 1
        k = (len(prices_sorted) - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return float(prices_sorted[int(k)])
        d0 = prices_sorted[int(f)] * (c - k)
        d1 = prices_sorted[int(c)] * (k - f)
        return float(d0 + d1)

    p25 = percentile(0.25)
    p75 = percentile(0.75)

    return StatsResponse(
        n=n,
        media=media,
        mediana=mediana,
        p25=p25,
        p75=p75,
        updated_at=time.time(),
    )
