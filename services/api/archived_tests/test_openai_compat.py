from openai import OpenAI

from jamaibase import JamAI


def test_openai_api_compat():
    client = JamAI()
    openai_client = OpenAI(base_url=client.api_base, api_key="dummy")
    kwargs = dict(
        model=client.model_names("openhermes-2.5-mistral-7b", capabilities=["chat"]),
        messages=[
            {"role": "system", "content": "You are a concise assistant."},
            {"role": "user", "content": "Hi"},
        ],
    )
    print(f"Chat completion kwargs: {kwargs}")

    # Non-streaming
    completion = openai_client.chat.completions.create(stream=False, **kwargs)
    reply = completion.choices[0].message.content
    assert isinstance(reply, str)
    assert len(reply) > 0

    # Streaming
    completion = openai_client.chat.completions.create(stream=True, **kwargs)
    reply = ""
    for chunk in completion:
        chunk_message = chunk.choices[0].delta
        reply += chunk_message.content
    assert isinstance(reply, str)
    assert len(reply) > 0


if __name__ == "__main__":
    test_openai_api_compat()
