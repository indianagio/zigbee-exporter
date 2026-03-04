from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_TOPIC,
    CONF_OUTPUT_DIR,
    CONF_FILE_CSV,
    CONF_FILE_HTML,
    DEFAULT_TOPIC,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_FILE_CSV,
    DEFAULT_FILE_HTML,
    SERVICE_GENERATE,
)

@dataclass
class InventoryConfig:
    topic: str
    output_dir: str
    file_csv: str
    file_html: str

def _get_cfg(entry: ConfigEntry) -> InventoryConfig:
    data = {**entry.data, **entry.options}
    return InventoryConfig(
        topic=data.get(CONF_TOPIC, DEFAULT_TOPIC),
        output_dir=data.get(CONF_OUTPUT_DIR, DEFAULT_OUTPUT_DIR),
        file_csv=data.get(CONF_FILE_CSV, DEFAULT_FILE_CSV),
        file_html=data.get(CONF_FILE_HTML, DEFAULT_FILE_HTML),
    )

def _flatten_exposes(exposes: list[dict[str, Any]]) -> list[str]:
    access_map = {1: "r", 2: "w", 3: "rw", 4: "r", 5: "rw", 7: "rw"}
    out: list[str] = []

    for e in exposes:
        etype = e.get("type", "")
        if "features" in e and isinstance(e["features"], list):
            for f in e["features"]:
                name = f.get("name") or f.get("property") or ""
                if not name:
                    continue
                access = access_map.get(int(f.get("access", 0) or 0), "?")
                unit = f.get("unit") or ""
                out.append(f"{name}({access}){f'[{unit}]' if unit else ''}")
        else:
            name = e.get("name") or etype or ""
            if not name:
                continue
            access = access_map.get(int(e.get("access", 0) or 0), "?")
            unit = e.get("unit") or ""
            out.append(f"{name}({access}){f'[{unit}]' if unit else ''}")

    return sorted(set(out))

def _format_endpoints(endpoints: dict[str, Any]) -> str:
    parts: list[str] = []
    for ep_id in sorted(endpoints.keys(), key=lambda x: int(x) if str(x).isdigit() else 9999):
        ep = endpoints.get(ep_id, {}) or {}
        clusters = (ep.get("clusters") or {}) if isinstance(ep.get("clusters"), dict) else {}
        cin = clusters.get("input") or []
        cout = clusters.get("output") or []
        if not isinstance(cin, list):
            cin = []
        if not isinstance(cout, list):
            cout = []
        parts.append(f"EP{ep_id}[in:{','.join(cin) or '-'}|out:{','.join(cout) or '-'}]")
    return " ".join(parts)

def _render_html(rows: list[dict[str, Any]], generated_at: str) -> str:
    def esc(s: str) -> str:
        return (
            (s or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    trs = []
    for r in rows:
        trs.append(
            "<tr>"
            f"<td>{esc(r['vendor'])}</td>"
            f"<td>{esc(r['model'])}</td>"
            f"<td>{esc(r['description'])}</td>"
            f"<td>{esc(r['type'])}</td>"
            f"<td>{esc(r['friendly_name'])}</td>"
            f"<td><code>{esc(r['ieee_address'])}</code></td>"
            f"<td class='small'>{esc(r['exposes'])}</td>"
            f"<td class='small'>{esc(r['endpoints'])}</td>"
            "</tr>"
        )

    return f\"\"\"<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Zigbee Exporter</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 16px; }}
h1 {{ margin: 0 0 6px 0; }}
.meta {{ color: #555; margin-bottom: 12px; }}
input {{ width: min(520px, 100%); padding: 8px 10px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
th, td {{ border-bottom: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; }}
th {{ cursor: pointer; user-select: none; background: #f7f7f7; position: sticky; top: 0; }}
.small {{ font-size: 12px; color: #444; }}
.hidden {{ display: none; }}
</style>
</head>
<body>
<h1>Zigbee2MQTT Inventory</h1>
<div class="meta">Generato: {esc(generated_at)} · Dispositivi: {len(rows)}</div>
<input id="q" type="text" placeholder="Cerca vendor, model, name, exposes..." oninput="filterRows()">

<table id="t">
<thead>
<tr>
  <th onclick="sortTable(0)">Vendor</th>
  <th onclick="sortTable(1)">Model</th>
  <th onclick="sortTable(2)">Descrizione</th>
  <th onclick="sortTable(3)">Tipo</th>
  <th onclick="sortTable(4)">Friendly name</th>
  <th onclick="sortTable(5)">IEEE</th>
  <th>Exposes</th>
  <th>Endpoints</th>
</tr>
</thead>
<tbody>
{''.join(trs)}
</tbody>
</table>

<script>
let dir = {{}};
function filterRows() {{
  const q = document.getElementById('q').value.toLowerCase();
  const rows = document.querySelectorAll('#t tbody tr');
  rows.forEach(r => {{
    const txt = r.textContent.toLowerCase();
    r.classList.toggle('hidden', q && !txt.includes(q));
  }});
}}
function sortTable(col) {{
  const tbody = document.querySelector('#t tbody');
  const rows = Array.from(tbody.querySelectorAll('tr'));
  dir[col] = !dir[col];
  rows.sort((a,b) => {{
    const va = (a.children[col].textContent || '').trim().toLowerCase();
    const vb = (b.children[col].textContent || '').trim().toLowerCase();
    return dir[col] ? va.localeCompare(vb) : vb.localeCompare(va);
  }});
  rows.forEach(r => tbody.appendChild(r));
}}
</script>
</body>
</html>\"\"\"

def _write_files(base_www: Path, cfg: InventoryConfig, rows: list[dict[str, Any]], generated_at: str) -> tuple[Path, Path]:
    out_dir = base_www / cfg.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / cfg.file_csv
    html_path = out_dir / cfg.file_html

    fields = ["vendor", "model", "description", "type", "friendly_name", "ieee_address", "exposes", "endpoints"]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    html = _render_html(rows, generated_at)
    html_path.write_text(html, encoding="utf-8")

    return csv_path, html_path

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    cfg = _get_cfg(entry)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "cfg": cfg,
        "unsub": None,
        "last_hash": None,
        "last_generated": None,
    }

    if not mqtt.is_connected(hass):
        raise HomeAssistantError("MQTT non connesso: configura prima l'integrazione MQTT in Home Assistant.")

    @callback
    def _handle_msg(msg: mqtt.ReceiveMessage) -> None:
        hass.async_create_task(_process_payload(hass, entry, msg.payload, force=False))

    unsub = await mqtt.async_subscribe(hass, cfg.topic, _handle_msg, qos=0)
    hass.data[DOMAIN][entry.entry_id]["unsub"] = unsub

    async def _service_generate(call: ServiceCall) -> None:
        force = bool(call.data.get("force", False))
        last = hass.data[DOMAIN][entry.entry_id].get("last_payload")
        if not last:
            raise HomeAssistantError("Nessun payload ricevuto ancora. Attendi un messaggio retained su bridge/devices o riavvia Zigbee2MQTT.")
        await _process_payload(hass, entry, last, force=force)

    if hass.services.has_service(DOMAIN, SERVICE_GENERATE) is False:
        hass.services.async_register(DOMAIN, SERVICE_GENERATE, _service_generate)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data and data.get("unsub"):
        data["unsub"]()
    return True

async def _process_payload(hass: HomeAssistant, entry: ConfigEntry, payload: str, force: bool) -> None:
    domain_data = hass.data[DOMAIN][entry.entry_id]
    domain_data["last_payload"] = payload

    payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if not force and domain_data.get("last_hash") == payload_hash:
        return

    cfg: InventoryConfig = domain_data["cfg"]

    try:
        devices = json.loads(payload)
        if not isinstance(devices, list):
            raise ValueError("bridge/devices non è una lista JSON")
    except Exception as err:
        raise HomeAssistantError(f"Errore parsing JSON da {cfg.topic}: {err}") from err

    rows: list[dict[str, Any]] = []
    for d in devices:
        definition = d.get("definition") or {}
        exposes = definition.get("exposes") or []
        endpoints = d.get("endpoints") or {}

        flat_exposes = _flatten_exposes(exposes if isinstance(exposes, list) else [])
        endpoints_s = _format_endpoints(endpoints if isinstance(endpoints, dict) else {})

        rows.append(
            {
                "vendor": definition.get("vendor") or "—",
                "model": definition.get("model") or "—",
                "description": definition.get("description") or "",
                "type": d.get("type") or "—",
                "friendly_name": d.get("friendly_name") or "",
                "ieee_address": d.get("ieee_address") or "",
                "exposes": ", ".join(flat_exposes),
                "endpoints": endpoints_s,
            }
        )

    rows.sort(key=lambda r: (r["vendor"].lower(), r["model"].lower(), r["friendly_name"].lower()))

    generated_at = dt_util.as_local(dt_util.utcnow()).strftime("%Y-%m-%d %H:%M:%S")
    base_www = Path(hass.config.path("www"))

    def _io_job():
        return _write_files(base_www, cfg, rows, generated_at)

    csv_path, html_path = await hass.async_add_executor_job(_io_job)

    domain_data["last_hash"] = payload_hash
    domain_data["last_generated"] = datetime.now().isoformat(timespec="seconds")

    hass.logger.info(
        "Z2M inventory generata: CSV=%s HTML=%s (topic=%s, devices=%d)",
        str(csv_path),
        str(html_path),
        cfg.topic,
        len(rows),
    )
