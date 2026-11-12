"""U-M GPT Toolkit provider: the University of Michigan's OpenAI-compatible gateway (Portkey in front of Azure
OpenAI), https://api.toolkit.umgpt.umich.edu/v1. Same Chat Completions contract as OpenRouter (strict json_schema
output, multi-turn messages, usage), so it reuses that adapter. Differences, verified against the gateway on
2026-11-12: the token limit is `max_completion_tokens` (`max_tokens` is rejected with 400), no OpenRouter
`X-Title` / `reasoning` fields, and no cost in the usage block (billing is the university's, not OpenAI's list
price).
"""

from app.llm.openrouter import OpenRouterProvider


class UMToolkitProvider(OpenRouterProvider):
    name = "um_toolkit"
    token_param = "max_completion_tokens"
    missing_key = ("UM_TOOLKIT_API_KEY is not configured on the backend. Add it to backend/.env (U-M GPT Toolkit) "
                   "or choose another LLM_PROVIDER.")

    def __init__(self, api_key: str | None, base_url: str, client=None):  # noqa: ANN001 - httpx.Client | None
        super().__init__(api_key, base_url, app_title="", client=client, reasoning_effort=None)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}
