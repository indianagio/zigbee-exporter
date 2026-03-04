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
    DEFAULT_TOPIC,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_FILE_CSV,
    SERVICE_GENERATE,
)

@dataclass
class InventoryConfig:
    topic: str
    output_dir: str
    file_csv: str

def _get_cfg(entry: ConfigEntry) -> InventoryConfig:
    data = {**entry.data, **entry.options}
    return InventoryConfig(
        topic=data.get(CONF_TOPIC, DEFAULT_TOPIC),
        output_dir=data.get(CONF_OUTPUT_DIR, DEFAULT_OUTPUT_DIR),
        file_csv=data.get(CONF_FILE_CSV, DEFAULT_FILE_CSV),
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

def _write_files(base_www: Path, cfg: InventoryConfig, rows: list[dict[str, Any]]) -> Path:
    out_dir = base_www / cfg.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / cfg.file_csv

    fields = ["vendor", "model", "description", "type", "friendly_name", "ieee_address", "exposes", "endpoints"]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    return csv_path

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    cfg = _get_cfg(entry)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "cfg": cfg,
        "unsub": None,
        "last_hash": None,
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

    base_www = Path(hass.config.path("www"))

    def _io_job():
        return _write_files(base_www, cfg, rows)

    csv_path = await hass.async_add_executor_job(_io_job)

    domain_data["last_hash"] = payload_hash

    hass.logger.info(
        "Z2M inventory generata: CSV=%s (topic=%s, devices=%d)",
        str(csv_path),
        cfg.topic,
        len(rows),
    )
