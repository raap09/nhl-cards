"""
NHL - Jogos de Hoje (Story 1080x1920)
Romulo P | Esportes - @romulop.esportes

Uso:
  python nhl_jogos_hoje.py                      # jogos de hoje
  python nhl_jogos_hoje.py --data 2026-10-21    # outra data
  python nhl_jogos_hoje.py --destaque TOR       # força o "jogo da noite" (sigla de um dos times)
  python nhl_jogos_hoje.py --sample sample.json # usa JSON local (teste offline)

Saída: jogos-hoje-AAAA-MM-DD.png na pasta atual (ou --saida).
Requisitos: pip install playwright requests && playwright install chromium
Telegram (opcional): defina TELEGRAM_TOKEN e TELEGRAM_CHAT_ID no ambiente.
"""
import argparse
import asyncio
import html
import json
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright

TZ_BR = ZoneInfo("America/Sao_Paulo")
API = "https://api-web.nhle.com/v1"

DIAS = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"]
MESES = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def carregar_jogos(dia, sample=None):
    data = json.loads(Path(sample).read_text(encoding="utf-8")) if sample else get_json(f"{API}/schedule/{dia}")
    for semana in data.get("gameWeek", []):
        if semana.get("date") == dia:
            return semana.get("games", [])
    return []


def carregar_pontos(sample=None):
    """Pontos na tabela por sigla, para escolher o jogo da noite. Falha silenciosa."""
    if sample:
        return {}
    try:
        st = get_json(f"{API}/standings/now")
        return {t["teamAbbrev"]["default"]: t.get("points", 0) for t in st.get("standings", [])}
    except Exception:
        return {}


def nome(time):
    place = time.get("placeName", {}).get("default", "")
    common = time.get("commonName", {}).get("default", "")
    return f"{place} {common}".strip() or time.get("abbrev", "")


def montar(jogos, pontos, destaque):
    linhas = []
    for g in jogos:
        if g.get("gameScheduleState", "OK") != "OK":
            continue
        inicio = datetime.fromisoformat(g["startTimeUTC"].replace("Z", "+00:00")).astimezone(TZ_BR)
        a, h = g["awayTeam"], g["homeTeam"]
        linhas.append({
            "hora": inicio.strftime("%Hh%M").replace("h00", "h"),
            "ordem": inicio,
            "fora": {"sigla": a["abbrev"], "nome": nome(a), "logo": a.get("logo", "")},
            "casa": {"sigla": h["abbrev"], "nome": nome(h), "logo": h.get("logo", "")},
            "forca": pontos.get(a["abbrev"], 0) + pontos.get(h["abbrev"], 0),
        })
    linhas.sort(key=lambda x: x["ordem"])
    if not linhas:
        return linhas
    if destaque:
        alvo = next((l for l in linhas if destaque.upper() in (l["fora"]["sigla"], l["casa"]["sigla"])), None)
    else:
        alvo = max(linhas, key=lambda l: l["forca"]) if any(l["forca"] for l in linhas) else None
    for l in linhas:
        l["destaque"] = l is alvo
    return linhas


def logo_html(t):
    sigla = html.escape(t["sigla"])
    if t["logo"]:
        return (f'<div class="logo"><img src="{html.escape(t["logo"])}" '
                f'onerror="this.parentNode.innerHTML=\'<span>{sigla}</span>\'"></div>')
    return f'<div class="logo"><span>{sigla}</span></div>'


# Cores vivas por time (versão "de tela", clareada quando a original some no navy)
CORES = {
    "ANA": "#F47A38", "BOS": "#FFB81C", "BUF": "#2463C9", "CGY": "#E4202E", "CAR": "#E4202E",
    "CHI": "#E3263A", "COL": "#8C2C4F", "CBJ": "#D8263A", "DAL": "#00A651", "DET": "#E4202E",
    "EDM": "#FF4C00", "FLA": "#E4202E", "LAK": "#A2AAAD", "MIN": "#1F8A4C", "MTL": "#C8233A",
    "NSH": "#FFB81C", "NJD": "#E4202E", "NYI": "#F47D30", "NYR": "#1F5BD8", "OTT": "#E4202E",
    "PHI": "#F74902", "PIT": "#FCB514", "SJS": "#00A3AD", "SEA": "#68D2DF", "STL": "#2E64D0",
    "TBL": "#2F5BD3", "TOR": "#2B5BD7", "UTA": "#6CACE4", "VAN": "#00843D", "VGK": "#B4975A",
    "WSH": "#E4202E", "WPG": "#5B8FD6",
}


def cor(sigla):
    return CORES.get(sigla, "#FF6B1A")


def render_html(linhas, dia):
    d = date.fromisoformat(dia)
    data_txt = f"{DIAS[d.weekday()]} · {d.day:02d} {MESES[d.month - 1]}"
    n = len(linhas)
    hero = next((l for l in linhas if l.get("destaque")), None)
    resto = [l for l in linhas if l is not hero]

    # área da lista se adapta ao número de jogos (com ou sem card de destaque)
    duas = len(resto) > 7          # muitos jogos: lista em 2 colunas
    area = 530 if hero else 1000
    linhas_vis = -(-len(resto) // 2) if duas else len(resto)
    row = max(44, min(128, area // max(linhas_vis, 1) - 10))
    s = min(row / 128, 0.62) if duas else min(row / 128, 0.85)

    def bolha(t, tam):
        # logo solto, fundo transparente; versão "_dark" do logo é feita para fundo escuro
        sig = html.escape(t["sigla"])
        src = t["logo"].replace("_light.svg", "_dark.svg")
        img = (f'<img src="{html.escape(src)}" onerror="this.remove()">' if src else "")
        return (f'<div class="bolha" style="--c:{cor(t["sigla"])};width:{tam}px;height:{tam}px">'
                f'<span style="font-size:{int(tam*0.3)}px">{sig}</span>{img}</div>')

    hero_html = ""
    if hero:
        a, h = hero["fora"], hero["casa"]
        hero_html = f"""
        <div class="hero" style="--a:{cor(a['sigla'])};--h:{cor(h['sigla'])}">
          <div class="hero-bg"></div>
          <div class="hero-tag">🔥 JOGO DA NOITE</div>
          <div class="hero-row">
            <div class="hero-time">{bolha(a, 215)}<b>{html.escape(a['sigla'])}</b></div>
            <div class="vs">VS</div>
            <div class="hero-time">{bolha(h, 215)}<b>{html.escape(h['sigla'])}</b></div>
          </div>
          <div class="hero-hora">{hero['hora']}</div>
        </div>"""

    itens = []
    for l in resto:
        a, h = l["fora"], l["casa"]
        itens.append(f"""
        <div class="jogo" style="--a:{cor(a['sigla'])};--h:{cor(h['sigla'])}">
          <div class="t">{bolha(a, int(row*0.92))}<b>{html.escape(a['sigla'])}</b></div>
          <div class="at">@</div>
          <div class="t">{bolha(h, int(row*0.92))}<b>{html.escape(h['sigla'])}</b></div>
          <div class="hora">{l['hora']}</div>
        </div>""")

    if not linhas:
        corpo = '<div class="vazio">SEM JOGOS<br>HOJE.<br><em>VOLTA AMANHÃ.</em></div>'
    else:
        corpo = hero_html + f'<div class="lista{" duas" if duas else ""}">{"".join(itens)}</div>'
    total = f"{n} JOGO{'S' if n != 1 else ''}" if n else "NHL"

    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
    :root {{ --navy:#0A1A3F; --navy2:#13296A; --laranja:#FF6B1A; --branco:#FFF; --r:{row}px; --s:{s}; }}
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ width:1080px; height:1920px; font-family:'Inter',sans-serif; color:#fff; overflow:hidden; position:relative;
      background:
        radial-gradient(900px 700px at 100% 0%, rgba(255,107,26,.35), transparent 60%),
        radial-gradient(900px 900px at 0% 100%, rgba(43,91,215,.45), transparent 60%),
        linear-gradient(170deg, #0D2152 0%, #0A1A3F 45%, #050D24 100%); }}
    /* faixa diagonal laranja atrás do título */
    .faixa {{ position:absolute; left:-200px; right:-200px; top:255px; height:335px; background:var(--laranja);
      transform:rotate(-8deg); box-shadow:0 30px 80px rgba(255,107,26,.45); }}
    .faixa::after {{ content:""; position:absolute; inset:0;
      background:repeating-linear-gradient(90deg, rgba(0,0,0,.08) 0 3px, transparent 3px 34px); }}
    .marca {{ position:absolute; right:-60px; bottom:120px; font-weight:900; font-size:520px; letter-spacing:-20px;
      color:transparent; -webkit-text-stroke:3px rgba(255,255,255,.06); line-height:1; transform:rotate(-8deg); }}
    .wrap {{ position:absolute; left:64px; right:64px; top:200px; bottom:330px; display:flex; flex-direction:column; }}
    .topo {{ display:flex; justify-content:space-between; align-items:center; }}
    .pill {{ font-weight:900; font-size:30px; letter-spacing:3px; padding:12px 26px; border-radius:999px;
      background:#fff; color:var(--navy); }}
    .pill.o {{ background:transparent; color:#fff; border:3px solid rgba(255,255,255,.7); }}
    h1 {{ position:relative; flex-shrink:0; margin-top:60px; font-weight:900; line-height:.82; letter-spacing:-6px;
      transform:rotate(-8deg); transform-origin:left center; }}
    h1 .l1 {{ display:block; font-size:92px; margin-bottom:70px; color:var(--navy); }}
    h1 .l2 {{ display:block; font-size:170px; color:#fff; text-shadow:0 8px 0 var(--navy), 0 20px 40px rgba(0,0,0,.35); }}
    .hero {{ position:relative; flex-shrink:0; margin-top:90px; height:360px; border-radius:36px; overflow:hidden;
      border:4px solid #fff; box-shadow:0 24px 60px rgba(0,0,0,.5); }}
    .hero-bg {{ position:absolute; inset:0;
      background:linear-gradient(115deg, var(--a) 0 49.6%, #fff 49.6% 50.4%, var(--h) 50.4% 100%); }}
    .hero-bg::after {{ content:""; position:absolute; inset:0;
      background:linear-gradient(180deg, rgba(0,0,0,.05), rgba(0,0,0,.45)); }}
    .hero-tag {{ position:absolute; top:22px; left:50%; transform:translateX(-50%); z-index:2; background:var(--navy);
      font-weight:900; font-size:24px; letter-spacing:3px; padding:9px 22px; border-radius:999px; white-space:nowrap; }}
    .hero-row {{ position:absolute; inset:0; display:flex; align-items:center; justify-content:space-around; padding:30px 0 50px; z-index:1; }}
    .hero-time {{ display:flex; flex-direction:column; align-items:center; gap:0; }}
    .hero-time b {{ font-size:44px; font-weight:900; letter-spacing:1px; text-shadow:0 4px 14px rgba(0,0,0,.5); }}
    .vs {{ font-weight:900; font-size:64px; font-style:italic; text-shadow:0 4px 14px rgba(0,0,0,.6); }}
    .hero-hora {{ position:absolute; bottom:18px; left:50%; transform:translateX(-50%); z-index:2; background:var(--laranja);
      font-weight:900; font-size:44px; padding:4px 28px; border-radius:16px; box-shadow:0 8px 20px rgba(0,0,0,.4); }}
    .lista {{ flex-shrink:0; margin-top:{22 if hero else 110}px; display:flex; flex-direction:column; gap:10px; }}
    .lista.duas {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }}
    .duas .jogo .bolha {{ display:none; }}
    .duas .jogo {{ grid-template-columns:auto 1fr auto auto; gap:8px; }}
    .duas .at {{ padding:0 4px; }}
    .jogo {{ height:var(--r); position:relative; display:grid; grid-template-columns:1fr calc(90px*var(--s) + 20px) 1fr calc(190px*var(--s) + 40px); align-items:center;
      padding:0 calc(26px*var(--s) + 10px) 0 calc(22px*var(--s) + 14px); border-radius:calc(22px*var(--s) + 6px); overflow:hidden;
      background:linear-gradient(90deg, color-mix(in srgb, var(--a) 55%, transparent) 0%, rgba(10,26,63,.85) 38%,
                 rgba(10,26,63,.85) 52%, color-mix(in srgb, var(--h) 55%, transparent) 88%, rgba(10,26,63,.9) 100%); }}
    .jogo::before {{ content:""; position:absolute; left:0; top:0; bottom:0; width:10px; background:var(--a); }}
    .t {{ display:flex; align-items:center; gap:calc(16px*var(--s) + 6px); }}
    .t b {{ font-weight:900; font-size:calc(54px*var(--s) + 6px); }}
    .at {{ text-align:center; font-weight:900; font-size:calc(34px*var(--s) + 6px); opacity:.55; }}
    .hora {{ font-weight:900; font-size:calc(48px*var(--s) + 6px); background:#fff; color:var(--navy);
      padding:calc(4px*var(--s) + 2px) calc(16px*var(--s) + 6px); border-radius:calc(12px*var(--s) + 4px); justify-self:end; }}
    .bolha {{ position:relative;
      display:flex; align-items:center; justify-content:center; flex-shrink:0; overflow:visible; }}
    .bolha span {{ font-weight:900; color:#fff; opacity:.9; }}
    .bolha img {{ position:absolute; inset:0; width:100%; height:100%; object-fit:contain;
      filter:drop-shadow(0 6px 16px rgba(0,0,0,.45)); }}
    .bolha:has(img) span {{ visibility:hidden; }}
    .vazio {{ margin-top:140px; font-weight:900; font-size:110px; line-height:.95; }}
    .vazio em {{ font-style:normal; color:var(--laranja); }}
    .rodape {{ position:absolute; left:64px; right:64px; bottom:220px; display:flex; justify-content:space-between; align-items:center; }}
    .rodape .info {{ font-weight:800; font-size:26px; letter-spacing:3px; opacity:.75; }}
    .chip {{ background:var(--laranja); font-weight:900; font-size:32px; padding:14px 30px; border-radius:999px; }}
    </style></head><body>
    <div class="faixa"></div>
    <div class="marca">NHL</div>
    <div class="wrap">
      <div class="topo"><div class="pill">NHL HOJE</div><div class="pill o">{data_txt}</div></div>
      <h1><span class="l1">HOJE TEM</span><span class="l2">HÓQUEI</span></h1>
      {corpo}
    </div>
    <div class="rodape"><div class="info">{total} · HORÁRIO DE BRASÍLIA</div><div class="chip">@romulop.esportes</div></div>
    </body></html>"""


async def screenshot(html_str, saida):
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1080, "height": 1920})
        await pg.set_content(html_str, wait_until="networkidle")
        await pg.wait_for_timeout(300)
        await pg.screenshot(path=saida, full_page=False)
        await b.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=datetime.now(TZ_BR).date().isoformat())
    ap.add_argument("--destaque", default=None)
    ap.add_argument("--sample", default=None)
    ap.add_argument("--saida", default=None)
    a = ap.parse_args()

    try:
        jogos = carregar_jogos(a.data, a.sample)
    except Exception as e:
        sys.exit(f"Erro ao buscar a agenda da NHL: {e}")
    linhas = montar(jogos, carregar_pontos(a.sample), a.destaque)
    saida = a.saida or f"jogos-hoje-{a.data}.png"
    asyncio.run(screenshot(render_html(linhas, a.data), saida))
    print(f"OK: {saida} ({len(linhas)} jogos)")
    enviar_telegram(saida, linhas, a.data)


def enviar_telegram(arquivo, linhas, dia):
    """Se TELEGRAM_TOKEN e TELEGRAM_CHAT_ID existirem, manda o PNG pro seu celular (como arquivo, sem compressão)."""
    import os
    token, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return
    import requests
    legenda = f"NHL hoje ({dia}): {len(linhas)} jogo(s). Pronto pro Story."
    with open(arquivo, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendDocument",
                          data={"chat_id": chat, "caption": legenda}, files={"document": f}, timeout=30)
    print("Telegram:", "enviado" if r.ok else r.text)


if __name__ == "__main__":
    main()
