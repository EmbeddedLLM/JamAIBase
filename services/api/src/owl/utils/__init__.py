from owl.utils.exceptions import ResourceNotFoundError


def get_api_key(
    model: str,
    openai_api_key: str = "",
    anthropic_api_key: str = "",
    gemini_api_key: str = "",
    cohere_api_key: str = "",
    groq_api_key: str = "",
    together_api_key: str = "",
    jina_api_key: str = "",
    voyage_api_key: str = "",
) -> str:
    if model.startswith("ellm"):
        key = "DUMMY_KEY"
    elif model.startswith("openai"):
        key = openai_api_key
    elif model.startswith("anthropic"):
        key = anthropic_api_key
    elif model.startswith("gemini"):
        key = gemini_api_key
    elif model.startswith("cohere"):
        key = cohere_api_key
    elif model.startswith("groq"):
        key = groq_api_key
    elif model.startswith("together"):
        key = together_api_key
    elif model.startswith("jina"):
        key = jina_api_key
    elif model.startswith("voyage"):
        key = voyage_api_key
    elif model.startswith("ellm"):
        key = "DUMMY_KEY"
    else:
        raise ResourceNotFoundError(f"Unsupported model: {model}")
    if key == "" or not key:
        raise ResourceNotFoundError(f"No suitable API key for model: {model}")
    return key
