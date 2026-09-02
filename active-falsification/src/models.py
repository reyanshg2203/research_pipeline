"""Generic model interface.

Design constraints (spec S.3, S.14):
  * one interface for every backend;
  * models are loaded and unloaded one at a time (GPU memory pressure);
  * EXACT output token counts are recorded, never estimated -- the compute
    matching between Active and Passive depends on them;
  * every prompt and every raw response is retained.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from schemas import Generation

# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------


@dataclass
class ModelSpec:
    """Static description of a supported model.

    ``thinking_mode`` records how reasoning is controlled for THIS model
    (calibration spec S.6).  There is no blanket ``use_thinking`` flag: applying
    one generic switch across models with different chat templates would either
    silently do nothing or raise, and either way the recorded configuration
    would not describe what actually ran.

      "chat_template_flag"  the tokenizer's chat template takes an
                            ``enable_thinking`` argument; we pass it explicitly
      "native"              the model reasons by default with no switch to set
      "instruct"            an ordinary instruct model; no reasoning mode

    ``reasoning_prefix`` is appended to the generation prompt so the model is
    forced to *begin* in its reasoning mode.  DeepSeek-R1-Distill's model card
    recommends exactly this, because the distilled models otherwise sometimes
    skip the reasoning span.  The prefix is part of the PROMPT, so it is counted
    in ``prompt_tokens`` and not in ``output_tokens``; it is prepended back onto
    the stored response so the saved trace shows what the model actually
    continued from.
    """

    alias: str
    model_id: str
    size_note: str
    thinking_mode: str = "instruct"
    merge_system_into_user: bool = False
    reasoning_prefix: Optional[str] = None
    gated: bool = False
    note: str = ""


MODEL_REGISTRY: Dict[str, ModelSpec] = {
    "qwen3_8b": ModelSpec(
        alias="qwen3_8b",
        model_id="Qwen/Qwen3-8B",
        size_note="8B",
        thinking_mode="chat_template_flag",
        note="Qwen3 chat template accepts enable_thinking; thinking mode is on",
    ),
    "deepseek_r1_llama_8b": ModelSpec(
        alias="deepseek_r1_llama_8b",
        model_id="deepseek-ai/DeepSeek-R1-Distill-Llama-8B",
        size_note="8B",
        thinking_mode="native",
        merge_system_into_user=True,
        reasoning_prefix="<think>\n",
        note=(
            "reasoning-distilled. Following its model card: no separate system "
            "turn (the instruction is merged into the user turn), and generation "
            "is forced to start with '<think>\\n' so the model always enters its "
            "reasoning mode. The zero-shot instruction and the FINAL_ANSWER "
            "convention are unchanged."
        ),
    ),
    "smollm3_3b": ModelSpec(
        alias="smollm3_3b",
        model_id="HuggingFaceTB/SmolLM3-3B",
        size_note="3B",
        thinking_mode="chat_template_flag",
        note="SmolLM3 chat template accepts enable_thinking; thinking mode is on",
    ),
    "llama32_3b": ModelSpec(
        alias="llama32_3b",
        model_id="meta-llama/Llama-3.2-3B-Instruct",
        size_note="3B",
        thinking_mode="instruct",
        gated=True,
        note="requires Hugging Face licence acceptance and an HF token",
    ),
    "phi35_mini": ModelSpec(
        alias="phi35_mini",
        model_id="microsoft/Phi-3.5-mini-instruct",
        size_note="3.8B",
        thinking_mode="instruct",
        note=(
            "NON-GATED FALLBACK. ~3.8B parameters, NOT an exact 3B model. Using "
            "it in place of llama32_3b requires explicit author approval and must "
            "be stated wherever the numbers appear."
        ),
    ),
    "mock": ModelSpec(
        alias="mock",
        model_id="mock://deterministic",
        size_note="n/a",
        thinking_mode="instruct",
        note="offline pipeline test harness; produces NO scientific results",
    ),
}


class GatedModelError(RuntimeError):
    """A gated model could not be loaded.

    Calibration stops rather than silently substituting a different model
    (calibration spec S.2).
    """


# --------------------------------------------------------------------------
# base interface
# --------------------------------------------------------------------------


class BaseModel:
    """Common interface.  Subclasses implement :meth:`_generate`."""

    is_mock = False

    def __init__(self, spec: ModelSpec, config: Dict[str, Any]):
        self.spec = spec
        self.config = config
        self.generations: List[Generation] = []
        self.total_output_tokens: int = 0

    # -- public -----------------------------------------------------------
    def generate(
        self,
        stage: str,
        family: str,
        system: str,
        user: str,
        max_new_tokens: int,
        seed: Optional[int] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Generation:
        started = time.time()
        response, out_tokens, in_tokens, hit_cap = self._generate(
            system, user, max_new_tokens, seed
        )
        gen = Generation(
            stage=stage,
            model=self.spec.alias,
            family=family,
            prompt=json.dumps({"system": system, "user": user}),
            response=response,
            output_tokens=out_tokens,
            prompt_tokens=in_tokens,
            hit_max_new_tokens=bool(hit_cap),
            meta={
                "max_new_tokens": max_new_tokens,
                "seed": seed,
                "seconds": round(time.time() - started, 3),
                **(meta or {}),
            },
        )
        self.generations.append(gen)
        self.total_output_tokens += out_tokens
        return gen

    def _generate(
        self, system: str, user: str, max_new_tokens: int, seed: Optional[int]
    ) -> tuple:
        """Return (text, output_tokens, prompt_tokens, hit_max_new_tokens)."""
        raise NotImplementedError

    def unload(self) -> None:
        pass

    def describe(self) -> Dict[str, Any]:
        return {
            "alias": self.spec.alias,
            "model_id": self.spec.model_id,
            "size_note": self.spec.size_note,
            "note": self.spec.note,
            "is_mock": self.is_mock,
            "precision": self.config.get("precision"),
            "thinking_mode": self.spec.thinking_mode,
        }


# --------------------------------------------------------------------------
# Hugging Face backend
# --------------------------------------------------------------------------


class HFModel(BaseModel):
    """transformers backend.

    Three things are recorded rather than assumed:

    * the RESOLVED inference configuration -- the dtype the weights actually
      loaded as, where the parameters actually landed, whether anything spilled
      to CPU or disk -- not just the precision label that was requested;
    * exact output-token counts, taken from generated token ids;
    * whether generation stopped at the token cap instead of finishing.

    Reasoning behaviour is resolved per model from the registry, so the manifest
    states what actually ran rather than what a generic flag requested.
    """

    def __init__(self, spec: ModelSpec, config: Dict[str, Any]):
        super().__init__(spec, config)
        import torch  # noqa: F401  (imported lazily so non-GPU tests work)
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self._torch = torch
        precision = str(config.get("precision", "bf16_or_fp16"))
        self.requested_precision = precision
        self.precision = precision

        has_cuda = bool(torch.cuda.is_available())
        supports_bf16 = bool(has_cuda and torch.cuda.is_bf16_supported())
        self.bf16_supported = supports_bf16

        kwargs: Dict[str, Any] = {"trust_remote_code": True}
        if precision == "4bit":
            from transformers import BitsAndBytesConfig

            # 4-bit NF4 with a BF16 compute dtype only where the GPU supports
            # BF16; a T4 (compute capability 7.5) does not, and asking for it
            # there is either rejected or silently slow.
            compute_dtype = torch.bfloat16 if supports_bf16 else torch.float16
            self.quantization = {
                "load_in_4bit": True,
                "bnb_4bit_quant_type": "nf4",
                "bnb_4bit_compute_dtype": str(compute_dtype).replace("torch.", ""),
                "bnb_4bit_use_double_quant": True,
            }
            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=compute_dtype,
                bnb_4bit_use_double_quant=True,
            )
        else:
            self.quantization = None
            kwargs["torch_dtype"] = torch.bfloat16 if supports_bf16 else torch.float16
        kwargs["device_map"] = "auto" if has_cuda else None

        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        if token:
            kwargs["token"] = token

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                spec.model_id, trust_remote_code=True, token=token
            )
            self.model = AutoModelForCausalLM.from_pretrained(spec.model_id, **kwargs)
        except Exception as exc:  # noqa: BLE001
            if spec.gated:
                raise GatedModelError(
                    f"could not load gated model {spec.model_id!r} "
                    f"({exc.__class__.__name__}: {exc}).\n"
                    f"Accept the licence on its Hugging Face page and export HF_TOKEN, "
                    f"or re-run with an EXPLICIT substitution:\n"
                    f"    python scripts/run_calibration.py --config <cfg> "
                    f"--substitute {spec.alias}=phi35_mini\n"
                    f"Nothing is substituted automatically."
                ) from exc
            raise

        self.model.eval()
        self.revision = getattr(self.model.config, "_commit_hash", None)
        self.thinking_mode = spec.thinking_mode
        self.reasoning_prefix = spec.reasoning_prefix
        self.chat_template_flag_accepted: Optional[bool] = None
        self.resolved = self._resolve_placement()

    # -- what actually loaded ---------------------------------------------
    def _resolve_placement(self) -> Dict[str, Any]:
        """Inspect the loaded model instead of trusting the requested config."""
        torch = self._torch
        dtypes: Dict[str, int] = {}
        devices: Dict[str, int] = {}
        for param in self.model.parameters():
            dtypes[str(param.dtype)] = dtypes.get(str(param.dtype), 0) + 1
            devices[str(param.device)] = devices.get(str(param.device), 0) + 1

        device_map = getattr(self.model, "hf_device_map", None)
        placements = set(str(v) for v in (device_map or {}).values())
        offloaded_modules = sorted(
            k for k, v in (device_map or {}).items()
            if str(v) in ("cpu", "disk") or str(v).startswith("cpu")
        )
        cpu_offload = bool(offloaded_modules) or any(
            d.startswith("cpu") for d in devices
        )
        disk_offload = any(str(v) == "disk" for v in (device_map or {}).values())

        info: Dict[str, Any] = {
            "requested_precision": self.requested_precision,
            "parameter_dtypes": dtypes,
            "dominant_parameter_dtype": (
                max(dtypes, key=dtypes.get) if dtypes else None
            ),
            "quantization": self.quantization,
            "bf16_supported_by_gpu": self.bf16_supported,
            "compute_dtype": (
                self.quantization["bnb_4bit_compute_dtype"] if self.quantization
                else (max(dtypes, key=dtypes.get) if dtypes else None)
            ),
            "device_map": device_map,
            "device_map_placements": sorted(placements) if placements else None,
            "parameter_devices": devices,
            "model_device": str(getattr(self.model, "device", "unknown")),
            "cpu_offload": cpu_offload,
            "disk_offload": disk_offload,
            "offloaded_modules": offloaded_modules or None,
        }
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            free, total = torch.cuda.mem_get_info()
            info.update({
                "gpu_name": props.name,
                "gpu_count": torch.cuda.device_count(),
                "gpu_total_vram_bytes": int(props.total_memory),
                "gpu_total_vram_gib": round(props.total_memory / 2 ** 30, 2),
                "gpu_free_vram_gib_after_load": round(free / 2 ** 30, 2),
                "gpu_used_vram_gib_after_load": round((total - free) / 2 ** 30, 2),
                "gpu_capability": f"{props.major}.{props.minor}",
            })
        else:
            info.update({"gpu_name": None, "gpu_total_vram_gib": None})
        return info

    # -- chat templating --------------------------------------------------
    def _messages(self, system: str, user: str) -> List[Dict[str, str]]:
        if self.spec.merge_system_into_user:
            return [{"role": "user", "content": f"{system}\n\n{user}"}]
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def _apply_template(self, system: str, user: str) -> str:
        messages = self._messages(system, user)
        base: Dict[str, Any] = {"tokenize": False, "add_generation_prompt": True}
        text = None
        if self.spec.thinking_mode == "chat_template_flag":
            try:
                text = self.tokenizer.apply_chat_template(
                    messages, enable_thinking=True, **base
                )
                self.chat_template_flag_accepted = True
            except TypeError:
                # the template does not take the argument; do NOT force it
                self.chat_template_flag_accepted = False
        if text is None:
            try:
                text = self.tokenizer.apply_chat_template(messages, **base)
            except Exception:  # pragma: no cover - templateless models
                text = f"{system}\n\n{user}\n\n"
        if self.reasoning_prefix and not text.rstrip().endswith(
            self.reasoning_prefix.strip()
        ):
            # force the model to begin inside its reasoning span
            text = text + self.reasoning_prefix
        return text

    def _generate(
        self, system: str, user: str, max_new_tokens: int, seed: Optional[int]
    ) -> tuple:
        torch = self._torch
        if seed is not None:
            torch.manual_seed(seed)
        text = self._apply_template(system, user)
        inputs = self.tokenizer(text, return_tensors="pt")
        if torch.cuda.is_available():
            inputs = {k: v.to(self.model.device) for k, v in inputs.items()}
        prompt_len = int(inputs["input_ids"].shape[-1])
        gen_kwargs = dict(
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=float(self.config.get("temperature", 0.6)),
            top_p=float(self.config.get("top_p", 0.95)),
            pad_token_id=self.tokenizer.pad_token_id or self.tokenizer.eos_token_id,
        )
        top_k = self.config.get("top_k")
        if top_k:
            gen_kwargs["top_k"] = int(top_k)
        with torch.no_grad():
            out = self.model.generate(**inputs, **gen_kwargs)
        new_ids = out[0][prompt_len:]
        # EXACT output-token count
        output_tokens = int(new_ids.shape[-1])
        response = self.tokenizer.decode(new_ids, skip_special_tokens=True)

        # truncation: the cap was reached and the run did not end on a stop token
        eos_ids = {self.tokenizer.eos_token_id}
        extra_eos = getattr(self.model.generation_config, "eos_token_id", None)
        if isinstance(extra_eos, (list, tuple)):
            eos_ids.update(int(t) for t in extra_eos)
        elif extra_eos is not None:
            eos_ids.add(int(extra_eos))
        ended_on_stop = bool(
            output_tokens and int(new_ids[-1]) in {t for t in eos_ids if t is not None}
        )
        hit_cap = output_tokens >= max_new_tokens and not ended_on_stop

        if self.reasoning_prefix:
            # the forced prefix is part of the prompt; put it back on the stored
            # trace so the saved response shows what the model continued from
            response = self.reasoning_prefix + response
        return response, output_tokens, prompt_len, hit_cap

    def describe(self) -> Dict[str, Any]:
        info = super().describe()
        info.update({
            "requested_precision": self.requested_precision,
            "revision": self.revision,
            "tokenizer": getattr(self.tokenizer, "name_or_path", None),
            "tokenizer_class": type(self.tokenizer).__name__,
            "thinking_mode": self.thinking_mode,
            "chat_template_enable_thinking_accepted": self.chat_template_flag_accepted,
            "merge_system_into_user": self.spec.merge_system_into_user,
            "forced_reasoning_prefix": self.reasoning_prefix,
            "resolved_inference": self.resolved,
            "generation": {
                "do_sample": True,
                "temperature": self.config.get("temperature"),
                "top_p": self.config.get("top_p"),
                "top_k": self.config.get("top_k"),
            },
        })
        if self.requested_precision == "4bit":
            info["WARNING_precision"] = (
                "4-bit NF4 is a SMOKE / PILOT setting. These numbers must not be "
                "used to select a difficulty tier and must not be pooled with "
                "full-precision results without a visible warning."
            )
        return info

    def unload(self) -> None:
        try:
            del self.model
        except AttributeError:
            pass
        try:
            self._torch.cuda.empty_cache()
        except Exception:
            pass


# --------------------------------------------------------------------------
# offline mock backend
# --------------------------------------------------------------------------


class MockModel(BaseModel):
    """Deterministic offline stand-in used to exercise the pipeline end to end.

    IMPORTANT: this model has no access to hidden labels and no mathematical
    ability.  Its outputs are a deterministic function of the prompt hash.  Runs
    that use it are stamped ``is_mock: true`` in the manifest and every summary
    table, and they produce NO scientific results.
    """

    is_mock = True

    def _hash(self, text: str) -> int:
        return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)

    def _generate(
        self, system: str, user: str, max_new_tokens: int, seed: Optional[int]
    ) -> tuple:
        h = self._hash(f"{system}\n{user}\n{seed}")
        if "FINAL_ANSWER" in system:
            body = "Working through the problem.\n"
            answer = ["12", "NONE", "1", "3/2", "0", "YES"][h % 6]
            text = f"{body}FINAL_ANSWER: {answer}"
        elif '"strategy"' in user and '"hypothesis"' in user:
            text = json.dumps(
                {
                    "strategy": "MOCK STRATEGY: apply the shared method from the examples.",
                    "hypothesis": "MOCK HYPOTHESIS v0: the method works unless the "
                    "problem shows an obvious structural obstruction.",
                }
            )
        elif '"constraints"' in user:
            text = json.dumps(
                {"constraints": self._mock_constraints(user, h), "reason": "MOCK reason."}
            )
        elif '"hypothesis"' in user:
            text = json.dumps(
                {"hypothesis": f"MOCK HYPOTHESIS v{h % 97}: refined from the evidence."}
            )
        elif "APPLIES" in user:
            text = "APPLIES" if h % 2 == 0 else "DOES_NOT_APPLY"
        else:
            text = "MOCK RESPONSE"
        # a plausible, deterministic token count (~4 chars per token)
        wanted = max(1, len(text) // 4)
        tokens = min(max_new_tokens, wanted)
        hit_cap = wanted >= max_new_tokens
        return text, tokens, max(1, len(system + user) // 4), hit_cap

    @staticmethod
    def _mock_constraints(user: str, h: int) -> Dict[str, str]:
        """Pick one real (feature, value) pair from the schema block in the prompt."""
        options = []
        for line in user.splitlines():
            line = line.strip()
            if line.startswith("- ") and ": " in line:
                name, values = line[2:].split(": ", 1)
                vals = [v.strip() for v in values.split(",") if v.strip()]
                if vals:
                    options.append((name.strip(), vals))
        if not options:
            return {"unknown_feature": "unknown_value"}
        name, vals = options[h % len(options)]
        return {name: vals[(h // 7) % len(vals)]}


# --------------------------------------------------------------------------
# loader
# --------------------------------------------------------------------------


def load_model(alias: str, config: Dict[str, Any]) -> BaseModel:
    if alias not in MODEL_REGISTRY:
        raise KeyError(
            f"unknown model alias {alias!r}; known: {sorted(MODEL_REGISTRY)}"
        )
    spec = MODEL_REGISTRY[alias]
    if alias == "mock":
        return MockModel(spec, config)
    return HFModel(spec, config)


def resolve_substitutions(
    aliases: List[str], substitutions: Dict[str, str]
) -> List[str]:
    """Apply EXPLICIT, user-approved model substitutions.

    Nothing is ever substituted automatically (calibration spec S.2): a gated
    model that cannot be loaded raises :class:`GatedModelError`, and only an
    explicit ``--substitute a=b`` on the command line changes the model list.
    """
    resolved = []
    for alias in aliases:
        target = substitutions.get(alias, alias)
        if target not in MODEL_REGISTRY:
            raise KeyError(f"unknown substitution target {target!r}")
        resolved.append(target)
    return resolved


def environment_report() -> Dict[str, Any]:
    """Versions and hardware, recorded in run_manifest.json."""
    report: Dict[str, Any] = {}
    try:
        import torch

        report["torch"] = torch.__version__
        report["cuda_available"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            free, total = torch.cuda.mem_get_info()
            report["gpu_name"] = props.name
            report["gpu_count"] = torch.cuda.device_count()
            report["gpu_total_vram_gib"] = round(props.total_memory / 2 ** 30, 2)
            report["gpu_free_vram_gib"] = round(free / 2 ** 30, 2)
            report["gpu_capability"] = f"{props.major}.{props.minor}"
            report["bf16_supported"] = bool(torch.cuda.is_bf16_supported())
            report["cuda_version"] = torch.version.cuda
    except Exception as exc:  # pragma: no cover
        report["torch"] = f"unavailable ({exc.__class__.__name__})"
    try:
        import transformers

        report["transformers"] = transformers.__version__
    except Exception as exc:  # pragma: no cover
        report["transformers"] = f"unavailable ({exc.__class__.__name__})"
    try:
        import sympy

        report["sympy"] = sympy.__version__
    except Exception:  # pragma: no cover
        pass
    return report
