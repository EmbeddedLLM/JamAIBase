# JamAI Base: Let Your Database Orchestrate LLMs and RAG

## Usage

### JamAI Client

You can use `JamAI` to call into all of the APIs using Python. It has complete type-hinting for easy development in an IDE.

```python
from jamaibase import JamAI


client = JamAI()
print(client.api_base)
```

#### API base

The main parameter to change is `api_key` (and `api_base` for OSS) when instantiating the client, which can be changed in 3 ways (from highest priority to least priority):

- Passing it as `str` argument

  ```python
  from jamaibase import JamAI

  # Cloud
  client = JamAI(api_key="...")
  print(client.api_base)

  # OSS
  client = JamAI(api_key="...", api_base="...")
  print(client.api_base)
  ```

- Specifying it as environment variable named `JAMAI_API_KEY` and `JAMAI_API_BASE`
- Specifying it in `.env` file as `JAMAI_API_KEY` and `JAMAI_API_BASE`

## OSS Setup

Please refer to [our GitHub repo for details](https://github.com/EmbeddedLLM/JamAIBase).
