from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import time

API_KEY = "dev-key"
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
def stats(modelo: str, ano: int | None = None, cidade: str | None = None, x_api_key: str | None = Header(default=None)):
    _check_api_key(x_api_key)
    base = 55000 if ano is None else max(35000, 60000 - (2025 - (ano or 2020)) * 2000)
    return StatsResponse(n=62, media=base, mediana=base*0.98, p25=base*0.93, p75=base*1.05, updated_at=time.time())

@app.get("/search", response_model=SearchResponse)
def search(modelo: str, ano: int | None = None, cidade: str | None = None, max_price: float | None = None, page: int = 1, x_api_key: str | None = Header(default=None)):
    _check_api_key(x_api_key)
    base_price = 55000 if ano is None else max(35000, 60000 - (2025 - (ano or 2020)) * 2000)
    def mk(i, delta):
        price = base_price + delta
        if max_price: price = min(price, max_price)
        return Listing(
            id=f"olx-{modelo}-{ano or 0}-{cidade or 'NA'}-{page}-{i}",
            title=f"{modelo} {ano or 0} - Oportunidade {i}",
            url="https://www.olx.com.br/anuncio-exemplo",
            modelo=modelo, ano=ano, cidade=cidade, preco=round(price, 2),
            km=50000 + i*3500, cambio="Manual" if i%2 else "Automático", combustivel="Flex", data_coleta=time.time()
        )
    items = [mk(1,-4000), mk(2,-2500), mk(3,-1000), mk(4,500), mk(5,1500), mk(6,-6000), mk(7,2500), mk(8,-2000)]
    return SearchResponse(items=items, count=64, next_page=page+1 if page<8 else None)
