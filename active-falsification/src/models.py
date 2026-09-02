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
    """

    alias: str
    model_id: str
    size_note: str
    thinking_mode: str = "instruct"
    merge_system_into_user: bool = False
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
        note=(
            "reasoning-distilled; reasons by default with no flag. The model card "
            "advises against a separate system prompt, so the instruction is "
            "merged into the user turn."
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
        response, out_tokens, in_tokens = self._generate(
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
    ) -> tuple:  # (text, output_tokens, prompt_tokens)
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

    Output token accounting is exact: we count generated token ids, not
    characters and not an estimate.

    Reasoning behaviour is resolved per model from ``spec.thinking_mode`` and
    recorded in :meth:`describe`, so the manifest states what actually ran
    rather than what a generic flag requested.
    """

    def __init__(self, spec: ModelSpec, config: Dict[str, Any]):
        super().__init__(spec, config)
        import torch  # noqa: F401  (imported lazily so non-GPU tests work)
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self._torch = torch
        precision = str(config.get("precision", "bf16_or_fp16"))
        self.precision = precision

        kwargs: Dict[str, Any] = {"trust_remote_code": True}
        if precision == "4bit":
            from transformers import BitsAndBytesConfig

            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
            )
        else:
            supports_bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
            kwargs["torch_dtype"] = torch.bfloat16 if supports_bf16 else torch.float16
        kwargs["device_map"] = "auto" if torch.cuda.is_available() else None

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
                    f"could not load gated model {spec.model_id!r} ({exc.__class__.__name__}: "
                    f"{exc}).\n"
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
        # resolved lazily on the first call, then recorded
        self.chat_template_flag_accepted: Optional[bool] = None

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
        if self.spec.thinking_mode == "chat_template_flag":
            try:
                text = self.tokenizer.apply_chat_template(
                    messages, enable_thinking=True, **base
                )
                self.chat_template_flag_accepted = True
                return text
            except TypeError:
                # the template does not take the argument; do NOT force it
                self.chat_template_flag_accepted = False
        try:
            return self.tokenizer.apply_chat_template(messages, **base)
        except Exception:  # pragma: no cover - templateless models
            return f"{system}\n\n{user}\n\n"

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
        # EXACT output-token count (spec S.24.6)
        output_tokens = int(new_ids.shape[-1])
        response = self.tokenizer.decode(new_ids, skip_special_tokens=True)
        return response, output_tokens, prompt_len

    def describe(self) -> Dict[str, Any]:
        info = super().describe()
        info.update({
            "revision": self.revision,
            "tokenizer": getattr(self.tokenizer, "name_or_path", None),
            "tokenizer_class": type(self.tokenizer).__name__,
            "thinking_mode": self.thinking_mode,
            "chat_template_enable_thinking_accepted": self.chat_template_flag_accepted,
            "merge_system_into_user": self.spec.merge_system_into_user,
            "generation": {
                "do_sample": True,
                "temperature": self.config.get("temperature"),
                "top_p": self.config.get("top_p"),
                "top_k": self.config.get("top_k"),
            },
        })
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
        tokens = min(max_new_tokens, max(1, len(text) // 4))
        return text, tokens, max(1, len(system + user) // 4)

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
            report["gpu_name"] = torch.cuda.get_device_name(0)
            report["gpu_count"] = torch.cuda.device_count()
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
