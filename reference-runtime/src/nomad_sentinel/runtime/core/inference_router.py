"""
Nomad Sentinel — Inference Router
═══════════════════════════════════════════════════════
Forked from Nomad Runtime's ADTC submission build. The ADTC competition
required llama.cpp as the sole runtime and explicitly disabled the
cloud-backed STALLION mode; Nomad Sentinel targets a different track
(EdgeAgent) where a cloud reasoning backend is the point, so STALLION
is re-enabled here and pointed at Qwen Cloud instead of Ollama:

    - GUARDIAN mode  -> guardian plugin (deterministic rules, zero deps,
                        also mirrors bhs.cognition's local heuristics)
    - NOMAD mode     -> llama_cpp plugin (tiny local model, offline-first)
    - WORKHORSE mode -> llama_cpp plugin (larger local model, still no
                        network dependency)
    - STALLION mode  -> qwen_cloud plugin (Qwen Cloud, requires network --
                        this is what bhs/cloud_cognition.py escalates to)

ModeSwitcher decides which of these is reachable right now based on
device + link conditions; this file just maps that decision to a
concrete plugin + model, same as it did in the ADTC build.
"""

from __future__ import annotations


import os
from dataclasses import dataclass
from typing import Optional

from mode_switcher import Mode
from plugin_base    import PluginInferenceResult
from plugin_registry import PluginRegistry

# -- Mode -> engine configuration --------------------------------------------
# engine_id must match a registered InferencePlugin.engine_id.

MODEL_REGISTRY = {
    Mode.NOMAD: {
        "engine_id":   "llama_cpp",
        "model":        "model/Phi-3-mini-4k-instruct-Q4_K_M.gguf",
        "description":  "Nomad -- Phi-3-mini 3.8B Q4_K_M via llama.cpp, offline-first",
        "est_ram_gb":   2.2,
    },
    Mode.WORKHORSE: {
        "engine_id":   "llama_cpp",
        "model":        "model/Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "description":  "Workhorse -- Llama 3.2-3B Q4_K_M via llama.cpp",
        "est_ram_gb":   3.8,
    },
    Mode.GUARDIAN: {
        "engine_id":   "guardian",
        "model":        "guardian-rules-v1",
        "description":  "Guardian -- deterministic rules, zero dependencies",
        "est_ram_gb":   0.0,
    },
    Mode.STALLION: {
        "engine_id":   "qwen_cloud",
        "model":        os.getenv("QWEN_MODEL", "qwen-plus"),
        "description":  "Stallion -- Qwen Cloud, richer cognitive reasoning, requires network",
        "est_ram_gb":   0.0,
    },
}


@dataclass
class InferenceResult:
    """External-facing result shape — unchanged so all callers stay compatible."""
    mode:           Mode
    model:          str
    backend:        str
    prompt_tokens:  int
    output_tokens:  int
    latency_ms:     float
    response_text:  str
    error:          Optional[str] = None
    ram_est_gb:     float = 0.0
    engine_meta:    Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "mode":          self.mode.value,
            "model":         self.model,
            "backend":       self.backend,
            "prompt_tokens": self.prompt_tokens,
            "output_tokens": self.output_tokens,
            "latency_ms":    round(self.latency_ms, 1),
            "response_text": self.response_text,
            "error":         self.error,
            "ram_est_gb":    self.ram_est_gb,
            "engine_meta":   self.engine_meta,
        }


class InferenceRouter:
    def __init__(self, registry: Optional[PluginRegistry] = None):
        if registry is None:
            registry = PluginRegistry()
            registry.discover()
        self._registry = registry

    def infer(
        self,
        mode: Mode,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 512,
    ) -> InferenceResult:
        if mode not in MODEL_REGISTRY:
            # Stallion requested but ADTC_SUBMISSION=true — fall back to Nomad
            mode = Mode.NOMAD

        cfg       = MODEL_REGISTRY[mode]
        engine_id = cfg["engine_id"]
        model_id  = cfg["model"]

        plugin_result: PluginInferenceResult = self._registry.safe_infer(
            engine_id     = engine_id,
            model_id      = model_id,
            prompt        = prompt,
            system_prompt = system_prompt,
            max_tokens    = max_tokens,
        )

        return InferenceResult(
            mode          = mode,
            model         = model_id,
            backend       = engine_id,
            prompt_tokens  = plugin_result.prompt_tokens,
            output_tokens  = plugin_result.output_tokens,
            latency_ms     = plugin_result.latency_ms,
            response_text  = plugin_result.response_text,
            error          = plugin_result.error,
            ram_est_gb     = cfg["est_ram_gb"],
            engine_meta    = plugin_result.raw_engine_meta or None,
        )

    def list_available_models(self) -> list[dict]:
        models = []
        for record in self._registry.list_engines():
            engine_id = record["engine_id"]
            plugin    = self._registry.get(engine_id)
            if plugin:
                try:
                    for m in plugin.list_models():
                        m.setdefault("engine", engine_id)
                        models.append(m)
                except Exception:
                    pass
        return models

    @property
    def registry(self) -> PluginRegistry:
        return self._registry
