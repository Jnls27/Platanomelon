#!/usr/bin/env python3
"""
Actualización diaria del dashboard Platano Melón (Meta Ads).

Qué hace:
  1. Calcula period_to = ayer (hora España, aproximación CET/CEST fija,
     igual que en el dashboard de FFJ -- el margen de una hora no afecta
     a la fecha calendario en la práctica).
  2. Pide a Windsor.ai (API REST pública) los datos de la cuenta
     Playwithplatano: por campaña+fecha, por adset+fecha, por anuncio
     (totales) y por anuncio+fecha (últimos 90 días).
  3. Clasifica mercado (ES/MEX) y audiencia (Prospecting/Retargeting) por
     nombre de campaña/adset -- misma lógica que el dashboard.
  4. Escribe data.json en la raíz del repo, listo para que index.html lo
     cargue con fetch(). No toca insights.json (eso lo gestiona una tarea
     semanal aparte, no este script).

Requiere la variable de entorno WINDSOR_API_KEY (GitHub secret en producción).
"""

import os
import sys
import json
import time
from datetime import date, datetime, timedelta, timezone

import requests

WINDSOR_BASE = "https://connectors.windsor.ai"
API_KEY = os.environ.get("WINDSOR_API_KEY")
if not API_KEY:
    print("ERROR: falta la variable de entorno WINDSOR_API_KEY", file=sys.stderr)
    sys.exit(1)

META_ACCOUNT = "987581319254631"
PERIOD_FROM = "2026-01-01"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RET_KEYWORDS = ["ALL AUDIENCE", "BUYERS", "EMAIL", "IG", "OWN AUDIENCE", "COMPRADORES", "RETARGETING"]
PROS_KEYWORDS = ["ADVANTAGE", "BROAD", "INTERESES", "PROSPECTING"]


def madrid_yesterday():
    now_utc = datetime.now(timezone.utc)
    offset = 2 if 4 <= now_utc.month <= 10 else 1
    now_madrid = now_utc + timedelta(hours=offset)
    return (now_madrid - timedelta(days=1)).date()


def windsor_get(fields, date_from, date_to, retries=3):
    params = {
        "api_key": API_KEY,
        "fields": ",".join(fields),
        "filter": json.dumps([["account_id", "eq", META_ACCOUNT]]),
        "date_from": date_from,
        "date_to": date_to,
    }
    url = f"{WINDSOR_BASE}/facebook"
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=170)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            if isinstance(data, list):
                return data
            raise ValueError(f"Respuesta inesperada de Windsor: {data!r}"[:500])
        except Exception as e:
            last_err = e
            print(f"  [aviso] intento {attempt}/{retries} falló: {e}", file=sys.stderr)
            time.sleep(3 * attempt)
    raise RuntimeError(f"Fallo definitivo pidiendo datos: {last_err}")


def month_chunks(date_from, date_to):
    cur = date.fromisoformat(date_from).replace(day=1)
    to_d = date.fromisoformat(date_to)
    while cur <= to_d:
        nxt = date(cur.year + 1, 1, 1) if cur.month == 12 else date(cur.year, cur.month + 1, 1)
        m_to = min(nxt - timedelta(days=1), to_d)
        yield cur.isoformat(), m_to.isoformat()
        cur = nxt


def to_float(v):
    try:
        return float(v) if v not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def market_of(campaign_name):
    return "MEX" if "MEX" in (campaign_name or "").upper() else "ES"


def audience_of(campaign_name, adset_name):
    c = (campaign_name or "").upper()
    if "PROS" in c:
        return "Prospecting"
    if "RET" in c:
        return "Retargeting"
    a = (adset_name or "").upper()
    if any(k in a for k in RET_KEYWORDS):
        return "Retargeting"
    if any(k in a for k in PROS_KEYWORDS):
        return "Prospecting"
    return "Prospecting"  # por defecto, si no hay señal de retargeting


def build():
    period_to = madrid_yesterday().isoformat()
    print(f"Actualizando dashboard Platano Melón hasta {period_to}...")

    # ---- 1) campaña + fecha -> ROWS + CAMPAIGNS ----
    print("  fetch campañas+fecha...")
    camp_field_rows = []
    for m_from, m_to in month_chunks(PERIOD_FROM, period_to):
        camp_field_rows += windsor_get(
            ["date", "campaign", "campaign_effective_status", "spend", "impressions",
             "clicks", "outbound_clicks_outbound_click", "reach", "actions_omni_purchase",
             "action_values_omni_purchase", "actions_lead", "actions_landing_page_view"],
            m_from, m_to)

    campaigns_idx = {}
    campaigns_list = []
    campaign_status = {}
    rows_by_key = {}
    for r in camp_field_rows:
        c = r.get("campaign") or "(sin nombre)"
        d = r.get("date")
        if not d:
            continue
        if r.get("campaign_effective_status"):
            campaign_status[c] = r["campaign_effective_status"]
        if c not in campaigns_idx:
            campaigns_idx[c] = len(campaigns_list)
            campaigns_list.append(c)
        ci = campaigns_idx[c]
        key = (ci, d)
        acc = rows_by_key.setdefault(key, [0.0] * 9)
        acc[0] += to_float(r.get("spend"))
        acc[1] += to_float(r.get("impressions"))
        acc[2] += to_float(r.get("clicks"))
        acc[3] += to_float(r.get("outbound_clicks_outbound_click"))
        acc[4] += to_float(r.get("reach"))
        acc[5] += to_float(r.get("actions_omni_purchase"))
        acc[6] += to_float(r.get("action_values_omni_purchase"))
        acc[7] += to_float(r.get("actions_lead"))
        acc[8] += to_float(r.get("actions_landing_page_view"))

    CAMPAIGNS = [[name, market_of(name), campaign_status.get(name, "Pausado")] for name in campaigns_list]
    ROWS = []
    for (ci, d), a in sorted(rows_by_key.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        mkt_idx = 0 if CAMPAIGNS[ci][1] == "ES" else 1
        ROWS.append([mkt_idx, ci] + [d] + a)
    # ROWS schema expected: [marketIdx, campIdx, date, spend, impr, clicks, outc, reach, purch, rev, leads, views]
    ROWS = [[r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11]] for r in ROWS]

    # ---- 2) adset + fecha -> ADSET_ROWS + ADSETS ----
    print("  fetch adsets+fecha...")
    adset_field_rows = []
    for m_from, m_to in month_chunks(PERIOD_FROM, period_to):
        adset_field_rows += windsor_get(
            ["date", "campaign", "adset_name", "adset_effective_status", "spend", "impressions",
             "clicks", "outbound_clicks_outbound_click", "reach", "actions_omni_purchase",
             "action_values_omni_purchase", "actions_lead", "actions_landing_page_view"],
            m_from, m_to)

    adsets_idx = {}
    adsets_list = []  # (name, campIdx)
    adset_status = {}
    adset_rows_by_key = {}
    for r in adset_field_rows:
        c = r.get("campaign") or "(sin nombre)"
        a_name = r.get("adset_name") or "(sin nombre)"
        d = r.get("date")
        if not d or c not in campaigns_idx:
            continue
        ci = campaigns_idx[c]
        akey = (a_name, ci)
        if r.get("adset_effective_status"):
            adset_status[akey] = r["adset_effective_status"]
        if akey not in adsets_idx:
            adsets_idx[akey] = len(adsets_list)
            adsets_list.append(akey)
        ai = adsets_idx[akey]
        key = (ai, d)
        acc = adset_rows_by_key.setdefault(key, [0.0] * 9)
        acc[0] += to_float(r.get("spend"))
        acc[1] += to_float(r.get("impressions"))
        acc[2] += to_float(r.get("clicks"))
        acc[3] += to_float(r.get("outbound_clicks_outbound_click"))
        acc[4] += to_float(r.get("reach"))
        acc[5] += to_float(r.get("actions_omni_purchase"))
        acc[6] += to_float(r.get("action_values_omni_purchase"))
        acc[7] += to_float(r.get("actions_lead"))
        acc[8] += to_float(r.get("actions_landing_page_view"))

    ADSETS = []
    for (a_name, ci) in adsets_list:
        mkt = CAMPAIGNS[ci][1]
        status = adset_status.get((a_name, ci), "Pausado")
        aud = audience_of(campaigns_list[ci], a_name)
        ADSETS.append([a_name, ci, mkt, status, aud])
    ADSET_ROWS = []
    for (ai, d), a in sorted(adset_rows_by_key.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        ADSET_ROWS.append([ai, d] + a)

    # ---- 3) anuncios (totales, sin fecha) -> AD_META ----
    print("  fetch anuncios (totales)...")
    ad_totals_rows = []
    for m_from, m_to in month_chunks(PERIOD_FROM, period_to):
        ad_totals_rows += windsor_get(
            ["campaign", "adset_name", "ad_name", "effective_status", "thumbnail_url",
             "image_asset_url", "carousel_card_media_urls", "website_destination_url",
             "spend", "impressions", "outbound_clicks_outbound_click", "reach",
             "actions_omni_purchase", "action_values_omni_purchase",
             "video_play_actions_video_view", "video_thruplay_watched_actions_video_view"],
            m_from, m_to)

    ad_acc = {}
    for r in ad_totals_rows:
        c = r.get("campaign") or "(sin nombre)"
        a_name = r.get("adset_name") or "(sin nombre)"
        ad_name = r.get("ad_name") or "(sin nombre)"
        if c not in campaigns_idx:
            continue
        ci = campaigns_idx[c]
        key = (ad_name, ci, a_name)
        o = ad_acc.setdefault(key, {
            "status": None, "thumb": "", "dest": "",
            "spend": 0.0, "impr": 0.0, "outc": 0.0, "reach": 0.0,
            "purch": 0.0, "rev": 0.0, "v3": 0.0, "vthru": 0.0,
        })
        if r.get("effective_status"):
            o["status"] = r["effective_status"]
        if not o["thumb"]:
            img = r.get("image_asset_url") or ""
            if not img:
                carousel = r.get("carousel_card_media_urls") or ""
                img = carousel.split(";")[0].strip() if carousel else ""
            if not img:
                img = r.get("thumbnail_url") or ""
            o["thumb"] = img
        if not o["dest"] and r.get("website_destination_url"):
            o["dest"] = r["website_destination_url"]
        o["spend"] += to_float(r.get("spend"))
        o["impr"] += to_float(r.get("impressions"))
        o["outc"] += to_float(r.get("outbound_clicks_outbound_click"))
        o["reach"] += to_float(r.get("reach"))
        o["purch"] += to_float(r.get("actions_omni_purchase"))
        o["rev"] += to_float(r.get("action_values_omni_purchase"))
        o["v3"] += to_float(r.get("video_play_actions_video_view"))
        o["vthru"] += to_float(r.get("video_thruplay_watched_actions_video_view"))

    ads_idx = {}
    ads_list = list(ad_acc.keys())
    AD_META = []
    for i, (ad_name, ci, a_name) in enumerate(ads_list):
        ads_idx[(ad_name, ci, a_name)] = i
        o = ad_acc[(ad_name, ci, a_name)]
        mkt = CAMPAIGNS[ci][1]
        aud = audience_of(campaigns_list[ci], a_name)
        AD_META.append([
            ad_name, ci, a_name, mkt, o["status"] or "Pausado", aud, o["thumb"],
            o["spend"], o["impr"], o["outc"], o["reach"], o["purch"], o["rev"],
            o["v3"], o["vthru"], o["dest"],
        ])

    # ---- 4) anuncios + fecha, últimos 90 días -> AD_ROWS90 ----
    print("  fetch anuncios+fecha (90 días)...")
    ad90_from = (date.fromisoformat(period_to) - timedelta(days=89)).isoformat()
    ad90_rows_raw = []
    for m_from, m_to in month_chunks(ad90_from, period_to):
        ad90_rows_raw += windsor_get(
            ["date", "campaign", "adset_name", "ad_name", "spend", "impressions",
             "outbound_clicks_outbound_click", "reach", "actions_omni_purchase",
             "action_values_omni_purchase", "video_play_actions_video_view",
             "video_thruplay_watched_actions_video_view"],
            m_from, m_to)

    ad90_acc = {}
    for r in ad90_rows_raw:
        c = r.get("campaign") or "(sin nombre)"
        a_name = r.get("adset_name") or "(sin nombre)"
        ad_name = r.get("ad_name") or "(sin nombre)"
        d = r.get("date")
        if not d or c not in campaigns_idx:
            continue
        ci = campaigns_idx[c]
        akey = (ad_name, ci, a_name)
        if akey not in ads_idx:
            continue  # anuncio sin totales (raro, se ignora)
        ai = ads_idx[akey]
        key = (ai, d)
        acc = ad90_acc.setdefault(key, [0.0] * 8)
        acc[0] += to_float(r.get("spend"))
        acc[1] += to_float(r.get("impressions"))
        acc[2] += to_float(r.get("outbound_clicks_outbound_click"))
        acc[3] += to_float(r.get("reach"))
        acc[4] += to_float(r.get("actions_omni_purchase"))
        acc[5] += to_float(r.get("action_values_omni_purchase"))
        acc[6] += to_float(r.get("video_play_actions_video_view"))
        acc[7] += to_float(r.get("video_thruplay_watched_actions_video_view"))
    AD_ROWS90 = []
    for (ai, d), a in sorted(ad90_acc.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        AD_ROWS90.append([ai, d] + a)
    # AD_ROWS90 schema: [adIdx, date, spend, impr, outc, reach, purch, rev, v3, vthru]

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "periodTo": period_to,
        "rows": ROWS,
        "campaigns": CAMPAIGNS,
        "adsets": ADSETS,
        "adsetRows": ADSET_ROWS,
        "adMeta": AD_META,
        "adRows90": AD_ROWS90,
    }


def sanity_check(data):
    errors = []
    if not data["rows"] or sum(r[3] for r in data["rows"]) <= 0:
        errors.append("Inversión total <= 0, algo falló en el fetch.")
    if not data["campaigns"]:
        errors.append("No se ha obtenido ninguna campaña.")
    if len(data["adMeta"]) < 10:
        errors.append(f"Solo {len(data['adMeta'])} anuncios -- parece muy poco, revisar.")
    return errors


def main():
    data = build()
    errors = sanity_check(data)
    if errors:
        print("VERIFICACIÓN FALLIDA -- no se sobrescribe data.json:", file=sys.stderr)
        for e in errors:
            print("  - " + e, file=sys.stderr)
        sys.exit(2)
    with open(os.path.join(REPO_ROOT, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"OK. data.json actualizado hasta {data['periodTo']}.")


if __name__ == "__main__":
    main()
