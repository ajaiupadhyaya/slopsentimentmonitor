"""The catalog of tracked models and the aliases people actually type.

This is seed data for the `models` table, not the runtime source of truth — the
README requires new models be addable through the database rather than a deploy.
Detection reads from the database; this module bootstraps it and gives tests a
fixture that does not need Postgres.

Alias design notes, learned from how these names appear in the wild:

* `case_sensitive` exists for aliases that are ordinary English words in
  lowercase. "grok" is a verb, "Grok" is a product.
* `requires_context` marks aliases too ambiguous to stand alone ("Nova",
  "Codex", "Gemini"). They only count when the surrounding document also talks
  about AI. This trades a little recall for a lot of precision, which is the
  right trade when every downstream metric is a count of these.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Alias:
    text: str
    case_sensitive: bool = False
    requires_context: bool = False
    #: Multiplier applied to the match confidence. Lower it for aliases that are
    #: real but sloppy ("sonnet" alone almost always means Claude Sonnet in an AI
    #: thread, but not always).
    weight: float = 1.0
    #: Following words that prove a different referent. Context gating cannot
    #: catch these: "Claude Monet" appears in articles thick with AI vocabulary.
    blocked_next: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelSpec:
    slug: str
    name: str
    company: str
    website: str | None = None
    aliases: tuple[Alias, ...] = field(default_factory=tuple)

    def all_aliases(self) -> tuple[Alias, ...]:
        """The canonical name is always matchable, plus declared aliases."""
        declared = {a.text.lower() for a in self.aliases}
        if self.name.lower() in declared:
            return self.aliases
        return (Alias(self.name),) + self.aliases


def _a(
    text: str,
    *,
    cs: bool = False,
    ctx: bool = False,
    w: float = 1.0,
    block: tuple[str, ...] = (),
) -> Alias:
    return Alias(
        text=text, case_sensitive=cs, requires_context=ctx, weight=w, blocked_next=block
    )


#: Famous humans whose given name is Claude. Without this, any article about
#: Impressionism or information theory reads as Anthropic coverage.
_CLAUDE_HUMANS: tuple[str, ...] = (
    "monet", "debussy", "shannon", "lévi", "levi", "bernard", "rains",
    "akerlof", "lorrain", "chappe", "juncker", "berri", "sautet", "lanzmann",
)


#: Terms that establish a document is talking about AI at all. Used to gate the
#: ambiguous aliases above.
AI_CONTEXT_TERMS: frozenset[str] = frozenset(
    {
        "ai", "llm", "llms", "model", "models", "prompt", "prompting", "token", "tokens",
        "context window", "inference", "fine-tune", "fine-tuning", "finetune",
        "chatbot", "agent", "agents", "agentic", "rag", "embedding", "embeddings",
        "openai", "anthropic", "hugging face", "huggingface", "transformer",
        "gpt", "chatgpt", "claude", "gemini", "copilot", "coding assistant",
        "hallucination", "hallucinations", "benchmark", "temperature", "api",
        "machine learning", "neural", "deep learning", "assistant", "completion",
    }
)


MODELS: tuple[ModelSpec, ...] = (
    # ---------------- OpenAI ----------------
    ModelSpec(
        slug="chatgpt", name="ChatGPT", company="OpenAI", website="https://chatgpt.com",
        aliases=(_a("chat gpt"), _a("chat-gpt")),
    ),
    ModelSpec(
        slug="gpt-5", name="GPT-5", company="OpenAI",
        aliases=(_a("gpt5"), _a("gpt 5")),
    ),
    ModelSpec(
        slug="gpt-5-mini", name="GPT-5 Mini", company="OpenAI",
        aliases=(_a("gpt5 mini"), _a("gpt-5-mini")),
    ),
    ModelSpec(
        slug="gpt-5-nano", name="GPT-5 Nano", company="OpenAI",
        aliases=(_a("gpt5 nano"), _a("gpt-5-nano")),
    ),
    ModelSpec(
        slug="gpt-4o", name="GPT-4o", company="OpenAI",
        aliases=(_a("gpt4o"), _a("gpt 4o")),
    ),
    ModelSpec(
        # "Codex" is also a manuscript and a Mozilla docs site.
        slug="codex", name="Codex", company="OpenAI",
        aliases=(_a("openai codex"), _a("codex cli"), _a("Codex", cs=True, ctx=True)),
    ),
    ModelSpec(
        slug="sora", name="Sora", company="OpenAI",
        aliases=(_a("Sora", cs=True, ctx=True),),
    ),

    # ---------------- Anthropic ----------------
    ModelSpec(
        slug="claude", name="Claude", company="Anthropic", website="https://claude.ai",
        aliases=(_a("claude", block=_CLAUDE_HUMANS), _a("claude ai"), _a("claude.ai")),
    ),
    ModelSpec(
        slug="claude-code", name="Claude Code", company="Anthropic",
        aliases=(_a("claudecode"), _a("cc", cs=True, ctx=True, w=0.5)),
    ),
    ModelSpec(
        slug="claude-sonnet", name="Claude Sonnet", company="Anthropic",
        aliases=(_a("sonnet", ctx=True, w=0.8), _a("claude-sonnet")),
    ),
    ModelSpec(
        slug="claude-opus", name="Claude Opus", company="Anthropic",
        aliases=(_a("opus", ctx=True, w=0.8), _a("claude-opus")),
    ),
    ModelSpec(
        slug="claude-haiku", name="Claude Haiku", company="Anthropic",
        aliases=(_a("haiku", ctx=True, w=0.7), _a("claude-haiku")),
    ),

    # ---------------- Google ----------------
    ModelSpec(
        # Also a zodiac sign and NASA's program.
        slug="gemini", name="Gemini", company="Google",
        aliases=(_a("google gemini"), _a("Gemini", cs=True, ctx=True)),
    ),
    ModelSpec(
        slug="gemini-cli", name="Gemini CLI", company="Google",
        aliases=(_a("gemini-cli"),),
    ),
    ModelSpec(
        slug="gemini-pro", name="Gemini Pro", company="Google",
        aliases=(_a("gemini-pro"),),
    ),
    ModelSpec(
        slug="gemini-flash", name="Gemini Flash", company="Google",
        aliases=(_a("gemini-flash"),),
    ),
    ModelSpec(
        slug="deep-research", name="Deep Research", company="Google",
        aliases=(_a("deep research", ctx=True),),
    ),
    ModelSpec(
        slug="gemma", name="Gemma", company="Google",
        aliases=(_a("Gemma", cs=True, ctx=True),),
    ),

    # ---------------- xAI ----------------
    ModelSpec(
        # "grok" the verb (Heinlein) is common on Hacker News specifically.
        slug="grok", name="Grok", company="xAI",
        aliases=(_a("Grok", cs=True), _a("grok-4"), _a("grok 4")),
    ),

    # ---------------- Meta ----------------
    ModelSpec(
        slug="llama", name="Llama", company="Meta",
        aliases=(_a("Llama", cs=True, ctx=True), _a("llama 3"), _a("llama3"),
                 _a("llama 4"), _a("llama4")),
    ),

    # ---------------- Mistral ----------------
    ModelSpec(
        slug="mistral", name="Mistral", company="Mistral AI",
        aliases=(_a("mistral ai"), _a("mixtral")),
    ),
    ModelSpec(
        slug="le-chat", name="Le Chat", company="Mistral AI",
        aliases=(_a("lechat"),),
    ),

    # ---------------- Others ----------------
    ModelSpec(
        slug="deepseek", name="DeepSeek", company="DeepSeek",
        aliases=(_a("deep seek"), _a("deepseek-r1"), _a("deepseek r1"), _a("deepseek-v3")),
    ),
    ModelSpec(
        slug="perplexity", name="Perplexity", company="Perplexity AI",
        aliases=(_a("perplexity ai"), _a("pplx")),
    ),
    ModelSpec(
        # Disambiguated from Microsoft 365 Copilot only by context; both are
        # legitimately "Copilot" for our purposes.
        slug="copilot", name="Copilot", company="Microsoft",
        aliases=(_a("github copilot"), _a("gh copilot"), _a("microsoft copilot"),
                 _a("copilot")),
    ),
    ModelSpec(
        slug="nova", name="Nova", company="Amazon",
        aliases=(_a("amazon nova"), _a("Nova", cs=True, ctx=True, w=0.6)),
    ),
    ModelSpec(
        slug="cohere", name="Cohere", company="Cohere",
        aliases=(_a("command r"), _a("command-r")),
    ),
    ModelSpec(
        slug="qwen", name="Qwen", company="Alibaba",
        aliases=(_a("qwen2"), _a("qwen3"), _a("qwen 3")),
    ),
    ModelSpec(
        slug="kimi", name="Kimi", company="Moonshot AI",
        aliases=(_a("Kimi", cs=True, ctx=True), _a("kimi k2"), _a("moonshot")),
    ),

    # ---------------- Open source tooling ----------------
    ModelSpec(
        slug="ollama", name="Ollama", company="Open Source",
        aliases=(),
    ),
    ModelSpec(
        slug="lm-studio", name="LM Studio", company="Open Source",
        aliases=(_a("lmstudio"),),
    ),
    ModelSpec(
        slug="vllm", name="vLLM", company="Open Source",
        aliases=(_a("vllm"),),
    ),
    ModelSpec(
        slug="llama-cpp", name="llama.cpp", company="Open Source",
        aliases=(_a("llamacpp"), _a("llama cpp")),
    ),
)


def by_slug(slug: str) -> ModelSpec:
    for spec in MODELS:
        if spec.slug == slug:
            return spec
    raise KeyError(slug)
