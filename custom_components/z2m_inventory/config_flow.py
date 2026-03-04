from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

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
)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="Zigbee Exporter", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_TOPIC, default=DEFAULT_TOPIC): str,
                vol.Required(CONF_OUTPUT_DIR, default=DEFAULT_OUTPUT_DIR): str,
                vol.Required(CONF_FILE_CSV, default=DEFAULT_FILE_CSV): str,
                vol.Required(CONF_FILE_HTML, default=DEFAULT_FILE_HTML): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @callback
    @staticmethod
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        data = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_TOPIC, default=data.get(CONF_TOPIC, DEFAULT_TOPIC)): str,
                vol.Required(CONF_OUTPUT_DIR, default=data.get(CONF_OUTPUT_DIR, DEFAULT_OUTPUT_DIR)): str,
                vol.Required(CONF_FILE_CSV, default=data.get(CONF_FILE_CSV, DEFAULT_FILE_CSV)): str,
                vol.Required(CONF_FILE_HTML, default=data.get(CONF_FILE_HTML, DEFAULT_FILE_HTML)): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
