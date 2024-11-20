# Python SDK Documentation

## Introduction

The JamAI Python SDK provides a convenient way to interact with the JamAI API, allowing you to leverage various AI capabilities in your Python applications.

## Getting Started

The recommended way of using JamAI Base is via Cloud 🚀. Did we mention that you can get free LLM tokens?

### Cloud 🚀

1. First, [sign up for a free account on JamAI Base Cloud!](https://cloud.jamaibase.com/)
2. Create a project and give it any name that you want.
3. Create a Python (>= 3.10) environment and install `jamaibase` (here we use [micromamba](https://mamba.readthedocs.io/en/latest/user_guide/micromamba.html) but you can use other tools such as [conda](https://conda.io/projects/conda/en/latest/user-guide/getting-started.html), virtualenv, etc):

   ```shell
   $ micromamba create -n jam310 python=3.10 -y
   $ micromamba activate jam310
   $ pip install jamaibase
   ```

4. In your script, import the `JamAI` class and create an instance.

   - API key can be obtained from [the "API Keys" section at cloud.jamaibase](https://cloud.jamaibase.com/organization/secrets).
   - Project ID can be obtained by browsing to any of your projects.

   ```python
   from jamaibase import JamAI, protocol as p

   jamai = JamAI(token="your_pat", project_id="your_project_id")
   ```

   Async is supported too:

   ```python
   from jamaibase import JamAIAsync, protocol as p

   jamai = JamAIAsync(token="your_pat", project_id="your_project_id")
   ```

### OSS

1. Clone the repository:

   ```shell
   $ git clone https://github.com/EmbeddedLLM/JamAIBase.git
   $ cd JamAIBase
   ```

2. Modify the configuration to suit your needs:

   - `services/api/src/owl/configs/models.json` specifies all the available models.
   - `.env` specifies which model to run on the `infinity` service for locally-hosted embedding and reranking models.
   - `.env` also specifies all the third party API keys to be used.

   For OSS mode, in order for you to see and use the other third party models such as OpenAI, you need to provide your own OpenAI API key in `.env` file. You can add one or more providers:

   ```
   OPENAI_API_KEY=...
   ANTHROPIC_API_KEY=...
   COHERE_API_KEY=...
   TOGETHER_API_KEY=...
   ```

3. Launch the Docker containers by running one of these:

   ```shell
   # CPU-only
   $ docker compose -f docker/compose.cpu.yml up --quiet-pull -d

   # With NVIDIA GPU
   $ docker compose -f docker/compose.nvidia.yml up --quiet-pull -d
   ```

   - By default, frontend and backend are accessible at ports 4000 and 6969.
   - You can change the ports exposed to host by setting env var in `.env` or shell like so `API_PORT=6970 FRONTEND_PORT=4001 docker compose -f docker/compose.cpu.yml up --quiet-pull -d`

4. Try the command below in your terminal, or open your browser and go to `localhost:4000`.

   ```shell
   $ curl localhost:6969/api/v1/models
   ```

5. To use our Python SDK, install `jamaibase` by following the steps outlined in Cloud section above.

6. In your script, import the `JamAI` class and create an instance.

   - `api_base` should point to the exposed port of `owl` service.

   ```python
   from jamaibase import JamAI, protocol as p

   jamai = JamAI(api_base="http://localhost:6969/api")
   ```

   Async is supported too:

   ```python
   from jamaibase import JamAIAsync, protocol as p

   jamai = JamAIAsync(api_base="http://localhost:6969/api")
   ```

### Tips

`project_id`, `api_key` and `api_base` can all be changed in 3 ways (from highest priority to least priority):

- Passing it as `str` argument

  ```python
  from jamaibase import JamAI

  # Cloud
  client = JamAI(project_id="...", token="...")
  print(client.api_base)

  # OSS
  client = JamAI(api_base="...")
  print(client.api_base)
  ```

- Specifying it as environment variable named `JAMAI_PROJECT_ID`, `JAMAI_API_KEY` and `JAMAI_API_BASE` respectively.
- Specifying it in `.env` file as `JAMAI_PROJECT_ID`, `JAMAI_API_KEY` and `JAMAI_API_BASE` respectively.

## Generative Tables (Basics)

There are 3 types of Generative Tables:

- Action: For chaining LLM reasoning steps
- Knowledge: For embedding external knowledge and files to power Retrieval Augmented Generation (RAG)
- Chat: For LLM agents with LLM chaining capabilities

We will guide you through the steps of leveraging Generative Tables to unleash the full potential of LLMs.

### Creating tables

Let's start with creating simple tables. Create a table by defining a schema.

<!-- prettier-ignore-start -->

> [!NOTE]
> When it comes to table names, there are some restrictions:
> 
> - Must have at least 1 character and up to 100 characters
> - Must start and end with an alphabet or number
> - Middle characters can contain alphabets, numbers, underscores `_`, dashes `-`, dots `.`
> 
> Column names have almost the same restrictions, except that:
> 
> - Spaces ` ` are accepted
> - Dots `.` are not accepted
> - Cannot be called "ID" or "Updated at" (case-insensitive)

<!-- prettier-ignore-end -->

```python
# Create an Action Table
table = jamai.table.create_action_table(
    p.ActionTableSchemaCreate(
        id="action-simple",
        cols=[
            p.ColumnSchemaCreate(id="image", dtype="file"),  # Image input
            p.ColumnSchemaCreate(id="length", dtype="int"),  # Integer input
            p.ColumnSchemaCreate(id="question", dtype="str"),
            p.ColumnSchemaCreate(
                id="answer",
                dtype="str",
                gen_config=p.LLMGenConfig(
                    model="openai/gpt-4o-mini",  # Leave this out to use a default model
                    system_prompt="You are a concise assistant.",
                    prompt="Image: ${image}\n\nQuestion: ${question}\n\nAnswer the question in ${length} words.",
                    temperature=0.001,
                    top_p=0.001,
                    max_tokens=100,
                ),
            ),
        ],
    )
)
print(table)

# Create a Knowledge Table
table = jamai.table.create_knowledge_table(
    p.KnowledgeTableSchemaCreate(
        id="knowledge-simple",
        cols=[],
        embedding_model="ellm/BAAI/bge-m3",
    )
)
print(table)

# Create a Chat Table
table = jamai.table.create_chat_table(
    p.ChatTableSchemaCreate(
        id="chat-simple",
        cols=[
            p.ColumnSchemaCreate(id="User", dtype="str"),
            p.ColumnSchemaCreate(
                id="AI",
                dtype="str",
                gen_config=p.LLMGenConfig(
                    model="openai/gpt-4o-mini",  # Leave this out to use a default model
                    system_prompt="You are a pirate.",
                    temperature=0.001,
                    top_p=0.001,
                    max_tokens=100,
                ),
            ),
        ],
    )
)
print(table)
```

### Adding rows

Now that we have our tables, we can start adding rows to them and receive the LLM responses.

First let's try adding to Action Table:

```python
text_a = 'Summarize this: "Arrival" is a 2016 science fiction drama film directed by Denis Villeneuve and adapted by Eric Heisserer.'
text_b = 'Summarize this: "Dune: Part Two is a 2024 epic science fiction film directed by Denis Villeneuve."'
text_c = "Identify the subject of the image."

# --- Action Table --- #
# Streaming
completion = jamai.table.add_table_rows(
    "action",
    p.RowAddRequest(
        table_id="action-simple",
        data=[dict(length=5, question=text_a)],
        stream=True,
    ),
)
for chunk in completion:
    if chunk.output_column_name != "answer":
        continue
    print(chunk.text, end="", flush=True)
print("")

# Non-streaming
completion = jamai.table.add_table_rows(
    "action",
    p.RowAddRequest(
        table_id="action-simple",
        data=[dict(length=5, question=text_b)],
        stream=False,
    ),
)
print(completion.rows[0].columns["answer"].text)

# Streaming (with image input)
upload_response = jamai.file.upload_file("clients/python/tests/files/jpeg/rabbit.jpeg")
completion = jamai.table.add_table_rows(
    "action",
    p.RowAddRequest(
        table_id="action-simple",
        data=[dict(image=upload_response.uri, length=5, question=text_c)],
        stream=True,
    ),
)
for chunk in completion:
    if chunk.output_column_name != "answer":
        continue
    print(chunk.text, end="", flush=True)
print("")

# Non-streaming (with image input)
completion = jamai.table.add_table_rows(
    "action",
    p.RowAddRequest(
        table_id="action-simple",
        data=[dict(image=upload_response.uri, length=5, question=text_c)],
        stream=False,
    ),
)
print(completion.rows[0].columns["answer"].text)
```

Next let's try adding to Chat Table:

```python
# --- Chat Table --- #
# Streaming
completion = jamai.table.add_table_rows(
    "chat",
    p.RowAddRequest(
        table_id="chat-simple",
        data=[dict(User="Who directed Arrival (2016)?")],
        stream=True,
    ),
)
for chunk in completion:
    if chunk.output_column_name != "AI":
        continue
    print(chunk.text, end="", flush=True)
print("")

# Non-streaming
completion = jamai.table.add_table_rows(
    "chat",
    p.RowAddRequest(
        table_id="chat-simple",
        data=[dict(User="Who directed Dune (2024)?")],
        stream=False,
    ),
)
print(completion.rows[0].columns["AI"].text)
```

Finally we can add rows to Knowledge Table too:

<!-- prettier-ignore-start -->

> [!TIP]
> Uploading files is the main way to add data into a Knowledge Table. Having said so, adding rows works too!

<!-- prettier-ignore-end -->

```python
# --- Knowledge Table --- #
# Streaming
completion = jamai.table.add_table_rows(
    "knowledge",
    p.RowAddRequest(
        table_id="knowledge-simple",
        data=[dict(Title="Arrival (2016)", Text=text_a)],
        stream=True,
    ),
)
assert len(list(completion)) == 0

# Non-streaming
completion = jamai.table.add_table_rows(
    "knowledge",
    p.RowAddRequest(
        table_id="knowledge-simple",
        data=[dict(Title="Dune (2024)", Text=text_b)],
        stream=False,
    ),
)
assert len(completion.rows[0].columns) == 0
```

### Retrieving rows

We can retrieve table rows by listing the rows or by fetching a specific row.

```python
# --- List rows -- #
# Action
rows = jamai.table.list_table_rows("action", "action-simple")
# Paginated items
for row in rows.items:
    print(row["ID"], row["answer"]["value"])

# Knowledge
rows = jamai.table.list_table_rows("knowledge", "knowledge-simple")
for row in rows.items:
    print(row["ID"], row["Title"]["value"])
    print(row["Title Embed"]["value"][:3])  # Knowledge Table has embeddings

# Chat
rows = jamai.table.list_table_rows("chat", "chat-simple")
for row in rows.items:
    print(row["ID"], row["User"]["value"], row["AI"]["value"])

# --- Fetch a specific row -- #
row = jamai.table.get_table_row("chat", "chat-simple", rows.items[0]["ID"])
print(row["ID"], row["AI"]["value"])

# --- Filter using a search term -- #
rows = jamai.table.list_table_rows("action", "action-simple", search_query="Dune")
for row in rows.items:
    print(row["ID"], row["answer"]["value"])
```

### Retrieving columns

We can retrieve columns by filtering them.

```python
# --- Only fetch specific columns -- #
rows = jamai.table.list_table_rows("action", "action-simple", columns=["length"])
for row in rows.items:
    # "ID" and "Updated at" will always be fetched
    print(row["ID"], row["length"]["value"])
```

### Retrieval Augmented Generation (RAG)

We can also upload files to Knowledge Table for Retrieval Augmented Generation (RAG). This allows LLM to generate answers that are grounded in the provided context and data.

```python
from os.path import join
from tempfile import TemporaryDirectory

with TemporaryDirectory() as tmp_dir:
    file_path = join(tmp_dir, "text.txt")
    with open(file_path, "w") as f:
        f.write("I bought a Mofusand book in 2024.\n\n")
        f.write("I went to Italy in 2018.\n\n")
    response = jamai.table.embed_file(file_path, "knowledge-simple")
    assert response.ok

# Create an Action Table with RAG
table = jamai.table.create_action_table(
    p.ActionTableSchemaCreate(
        id="action-rag",
        cols=[
            p.ColumnSchemaCreate(id="question", dtype="str"),
            p.ColumnSchemaCreate(
                id="answer",
                dtype="str",
                gen_config=p.LLMGenConfig(
                    model="openai/gpt-4o-mini",  # Leave this out to use a default model
                    system_prompt="You are a concise assistant.",
                    prompt="${question}",
                    rag_params=p.RAGParams(
                        table_id="knowledge-simple",
                        k=2,
                    ),
                    temperature=0.001,
                    top_p=0.001,
                    max_tokens=100,
                ),
            ),
        ],
    )
)
print(table)

# Ask a question with streaming
completion = jamai.table.add_table_rows(
    "action",
    p.RowAddRequest(
        table_id="action-rag",
        data=[dict(question="Where did I go in 2018?")],
        stream=True,
    ),
)
for chunk in completion:
    if chunk.output_column_name != "answer":
        continue
    if isinstance(chunk, p.GenTableStreamReferences):
        # References that are retrieved from KT
        assert len(chunk.chunks) == 2  # k = 2
        print(chunk.chunks)
    else:
        # LLM generation
        print(chunk.text, end="", flush=True)
print("")
```

### Retrieving tables

We can retrieve tables by listing the tables or by fetching a specific tables.

```python
# --- List tables -- #
# Action
tables = jamai.table.list_tables("action", count_rows=True)
assert len(tables.items) == 2
# Paginated items
for table in tables.items:
    print(f"{table.id=}, {table.num_rows=}")

# Knowledge
tables = jamai.table.list_tables("knowledge")
assert len(tables.items) == 1
for table in tables.items:
    print(f"{table.id=}, {table.num_rows=}")

# Chat
tables = jamai.table.list_tables("chat")
assert len(tables.items) == 1
for table in tables.items:
    print(f"{table.id=}, {table.num_rows=}")

# --- Fetch a specific table -- #
table = jamai.table.get_table("action", "action-rag")
print(f"{table.id=}, {table.num_rows=}")
```

### Deleting rows

Now that you know how to add rows into tables, let's see how to delete them instead.

```python
# Delete all rows
rows = jamai.table.list_table_rows("action", "action-simple")
response = jamai.table.delete_table_rows(
    "action",
    p.RowDeleteRequest(
        table_id="action-simple",
        row_ids=[row["ID"] for row in rows.items],
    ),
)
assert response.ok
# Assert that the table is empty
rows = jamai.table.list_table_rows("action", "action-simple")
assert len(rows.items) == 0
```

### Deleting tables

Let's see how to delete tables.

<!-- prettier-ignore-start -->

> [!TIP]
> Deletion will return "OK" even if the table does not exist.

<!-- prettier-ignore-end -->

```python
# Delete tables
response = jamai.table.delete_table("action", "action-simple")
assert response.ok
response = jamai.table.delete_table("knowledge", "knowledge-simple")
assert response.ok
response = jamai.table.delete_table("chat", "chat-simple")
assert response.ok
response = jamai.table.delete_table("action", "action-rag")
assert response.ok
```

We can combine this with the table list method to delete all tables without having to specify their names:

```python
batch_size = 100
for table_type in ["action", "knowledge", "chat"]:
    offset, total = 0, 1
    while offset < total:
        tables = jamai.table.list_tables(table_type, offset=offset, limit=batch_size)
        assert isinstance(tables.items, list)
        for table in tables.items:
            jamai.table.delete_table(table_type, table.id)
        total = tables.total
        offset += batch_size
```

### Full script

The full script is as follows:

```python
from jamaibase import JamAI
from jamaibase import protocol as p


def create_tables(jamai: JamAI):
    # Create an Action Table
    table = jamai.table.create_action_table(
        p.ActionTableSchemaCreate(
            id="action-simple",
            cols=[
                p.ColumnSchemaCreate(id="image", dtype="file"),  # Image input
                p.ColumnSchemaCreate(id="length", dtype="int"),  # Integer input
                p.ColumnSchemaCreate(id="question", dtype="str"),
                p.ColumnSchemaCreate(
                    id="answer",
                    dtype="str",
                    gen_config=p.LLMGenConfig(
                        model="openai/gpt-4o-mini",  # Leave this out to use a default model
                        system_prompt="You are a concise assistant.",
                        prompt="Image: ${image}\n\nQuestion: ${question}\n\nAnswer the question in ${length} words.",
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=100,
                    ),
                ),
            ],
        )
    )
    print(table)

    # Create a Knowledge Table
    table = jamai.table.create_knowledge_table(
        p.KnowledgeTableSchemaCreate(
            id="knowledge-simple",
            cols=[],
            embedding_model="ellm/BAAI/bge-m3",
        )
    )
    print(table)

    # Create a Chat Table
    table = jamai.table.create_chat_table(
        p.ChatTableSchemaCreate(
            id="chat-simple",
            cols=[
                p.ColumnSchemaCreate(id="User", dtype="str"),
                p.ColumnSchemaCreate(
                    id="AI",
                    dtype="str",
                    gen_config=p.LLMGenConfig(
                        model="openai/gpt-4o-mini",  # Leave this out to use a default model
                        system_prompt="You are a pirate.",
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=100,
                    ),
                ),
            ],
        )
    )
    print(table)


def add_rows(jamai: JamAI):
    text_a = 'Summarize this: "Arrival" is a 2016 science fiction drama film directed by Denis Villeneuve and adapted by Eric Heisserer.'
    text_b = 'Summarize this: "Dune: Part Two is a 2024 epic science fiction film directed by Denis Villeneuve."'
    text_c = "Identify the subject of the image."

    # --- Action Table --- #
    # Streaming
    completion = jamai.table.add_table_rows(
        "action",
        p.RowAddRequest(
            table_id="action-simple",
            data=[dict(length=5, question=text_a)],
            stream=True,
        ),
    )
    for chunk in completion:
        if chunk.output_column_name != "answer":
            continue
        print(chunk.text, end="", flush=True)
    print("")

    # Non-streaming
    completion = jamai.table.add_table_rows(
        "action",
        p.RowAddRequest(
            table_id="action-simple",
            data=[dict(length=5, question=text_b)],
            stream=False,
        ),
    )
    print(completion.rows[0].columns["answer"].text)

    # Streaming (with image input)
    upload_response = jamai.file.upload_file("clients/python/tests/files/jpeg/rabbit.jpeg")
    completion = jamai.table.add_table_rows(
        "action",
        p.RowAddRequest(
            table_id="action-simple",
            data=[dict(image=upload_response.uri, length=5, question=text_c)],
            stream=True,
        ),
    )
    for chunk in completion:
        if chunk.output_column_name != "answer":
            continue
        print(chunk.text, end="", flush=True)
    print("")

    # Non-streaming (with image input)
    completion = jamai.table.add_table_rows(
        "action",
        p.RowAddRequest(
            table_id="action-simple",
            data=[dict(image=upload_response.uri, length=5, question=text_c)],
            stream=False,
        ),
    )
    print(completion.rows[0].columns["answer"].text)

    # --- Chat Table --- #
    # Streaming
    completion = jamai.table.add_table_rows(
        "chat",
        p.RowAddRequest(
            table_id="chat-simple",
            data=[dict(User="Who directed Arrival (2016)?")],
            stream=True,
        ),
    )
    for chunk in completion:
        if chunk.output_column_name != "AI":
            continue
        print(chunk.text, end="", flush=True)
    print("")

    # Non-streaming
    completion = jamai.table.add_table_rows(
        "chat",
        p.RowAddRequest(
            table_id="chat-simple",
            data=[dict(User="Who directed Dune (2024)?")],
            stream=False,
        ),
    )
    print(completion.rows[0].columns["AI"].text)

    # --- Knowledge Table --- #
    # Streaming
    completion = jamai.table.add_table_rows(
        "knowledge",
        p.RowAddRequest(
            table_id="knowledge-simple",
            data=[dict(Title="Arrival (2016)", Text=text_a)],
            stream=True,
        ),
    )
    assert len(list(completion)) == 0

    # Non-streaming
    completion = jamai.table.add_table_rows(
        "knowledge",
        p.RowAddRequest(
            table_id="knowledge-simple",
            data=[dict(Title="Dune (2024)", Text=text_b)],
            stream=False,
        ),
    )
    assert len(completion.rows[0].columns) == 0


def fetch_rows(jamai: JamAI):
    # --- List rows -- #
    # Action
    rows = jamai.table.list_table_rows("action", "action-simple")
    assert len(rows.items) == 4
    # Paginated items
    for row in rows.items:
        print(row["ID"], row["answer"]["value"])

    # Knowledge
    rows = jamai.table.list_table_rows("knowledge", "knowledge-simple")
    assert len(rows.items) == 2
    for row in rows.items:
        print(row["ID"], row["Title"]["value"])
        print(row["Title Embed"]["value"][:3])  # Knowledge Table has embeddings

    # Chat
    rows = jamai.table.list_table_rows("chat", "chat-simple")
    assert len(rows.items) == 2
    for row in rows.items:
        print(row["ID"], row["User"]["value"], row["AI"]["value"])

    # --- Fetch a specific row -- #
    row = jamai.table.get_table_row("chat", "chat-simple", rows.items[0]["ID"])
    print(row["ID"], row["AI"]["value"])

    # --- Filter using a search term -- #
    rows = jamai.table.list_table_rows("action", "action-simple", search_query="Dune")
    assert len(rows.items) == 1
    for row in rows.items:
        print(row["ID"], row["answer"]["value"])


def fetch_columns(jamai: JamAI):
    # --- Only fetch specific columns -- #
    rows = jamai.table.list_table_rows("action", "action-simple", columns=["length"])
    assert len(rows.items) == 4
    for row in rows.items:
        # "ID" and "Updated at" will always be fetched
        print(row["ID"], row["length"]["value"])


def rag(jamai: JamAI):
    from os.path import join
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp_dir:
        file_path = join(tmp_dir, "text.txt")
        with open(file_path, "w") as f:
            f.write("I bought a Mofusand book in 2024.\n\n")
            f.write("I went to Italy in 2018.\n\n")
        response = jamai.table.embed_file(file_path, "knowledge-simple")
        assert response.ok

    # Create an Action Table with RAG
    table = jamai.table.create_action_table(
        p.ActionTableSchemaCreate(
            id="action-rag",
            cols=[
                p.ColumnSchemaCreate(id="question", dtype="str"),
                p.ColumnSchemaCreate(
                    id="answer",
                    dtype="str",
                    gen_config=p.LLMGenConfig(
                        model="openai/gpt-4o-mini",  # Leave this out to use a default model
                        system_prompt="You are a concise assistant.",
                        prompt="${question}",
                        rag_params=p.RAGParams(
                            table_id="knowledge-simple",
                            k=2,
                        ),
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=100,
                    ),
                ),
            ],
        )
    )
    print(table)

    # Ask a question with streaming
    completion = jamai.table.add_table_rows(
        "action",
        p.RowAddRequest(
            table_id="action-rag",
            data=[dict(question="Where did I went in 2018?")],
            stream=True,
        ),
    )
    for chunk in completion:
        if chunk.output_column_name != "answer":
            continue
        if isinstance(chunk, p.GenTableStreamReferences):
            # References that are retrieved from KT
            assert len(chunk.chunks) == 2  # k = 2
            print(chunk.chunks)
        else:
            # LLM generation
            print(chunk.text, end="", flush=True)
    print("")


def fetch_tables(jamai: JamAI):
    # --- List tables -- #
    # Action
    tables = jamai.table.list_tables("action", count_rows=True)
    assert len(tables.items) == 2
    # Paginated items
    for table in tables.items:
        print(f"{table.id=}, {table.num_rows=}")

    # Knowledge
    tables = jamai.table.list_tables("knowledge")
    assert len(tables.items) == 1
    for table in tables.items:
        print(f"{table.id=}, {table.num_rows=}")

    # Chat
    tables = jamai.table.list_tables("chat")
    assert len(tables.items) == 1
    for table in tables.items:
        print(f"{table.id=}, {table.num_rows=}")

    # --- Fetch a specific table -- #
    table = jamai.table.get_table("action", "action-rag")
    print(f"{table.id=}, {table.num_rows=}")


def delete_rows(jamai: JamAI):
    # Delete all rows
    rows = jamai.table.list_table_rows("action", "action-simple")
    response = jamai.table.delete_table_rows(
        "action",
        p.RowDeleteRequest(
            table_id="action-simple",
            row_ids=[row["ID"] for row in rows.items],
        ),
    )
    assert response.ok
    # Assert that the table is empty
    rows = jamai.table.list_table_rows("action", "action-simple")
    assert len(rows.items) == 0


def delete_tables(jamai: JamAI):
    # Delete tables
    response = jamai.table.delete_table("action", "action-simple")
    assert response.ok
    response = jamai.table.delete_table("knowledge", "knowledge-simple")
    assert response.ok
    response = jamai.table.delete_table("chat", "chat-simple")
    assert response.ok
    response = jamai.table.delete_table("action", "action-rag")
    assert response.ok


def delete_all_tables(jamai: JamAI):
    batch_size = 100
    for table_type in ["action", "knowledge", "chat"]:
        offset, total = 0, 1
        while offset < total:
            tables = jamai.table.list_tables(table_type, offset=offset, limit=batch_size)
            assert isinstance(tables.items, list)
            for table in tables.items:
                jamai.table.delete_table(table_type, table.id)
            total = tables.total
            offset += batch_size


def duplicate_tables(jamai: JamAI):
    # By default, both schema (like generation config) and data are included
    table = jamai.table.duplicate_table(
        "action",
        "action-rag",
        "action-rag-copy",
    )
    assert table.id == "action-rag-copy"
    rows = jamai.table.list_table_rows("action", "action-rag-copy")
    assert rows.total > 0

    # We can also duplicate a table without its data
    table = jamai.table.duplicate_table(
        "action",
        "action-rag",
        "action-rag-copy-schema-only",
        include_data=False,
    )
    assert table.id == "action-rag-copy-schema-only"
    rows = jamai.table.list_table_rows("action", "action-rag-copy-schema-only")
    assert rows.total == 0


def main():
    jamai = JamAI()

    delete_all_tables(jamai)
    create_tables(jamai)
    add_rows(jamai)
    fetch_rows(jamai)
    fetch_columns(jamai)
    rag(jamai)
    fetch_tables(jamai)
    duplicate_tables(jamai)
    delete_rows(jamai)
    delete_all_tables(jamai)


if __name__ == "__main__":
    main()
```

## Generative Tables (Advanced)

### Duplicating tables

We can create copies of tables under the same project. By default, the method copies over both table schema and its data, but we can choose to exclude data when duplicating.

```python
# By default, both schema (like generation config) and data are included
table = jamai.table.duplicate_table(
    "action",
    "action-rag",
    "action-rag-copy",
)
assert table.id == "action-rag-copy"
rows = jamai.table.list_table_rows("action", "action-rag-copy")
assert len(rows.total) > 0

# We can also duplicate a table without its data
table = jamai.table.duplicate_table(
    "action",
    "action-rag",
    "action-rag-copy-schema-only",
    include_data=False,
)
assert table.id == "action-rag-copy-schema-only"
rows = jamai.table.list_table_rows("action", "action-rag-copy-schema-only")
assert len(rows.total) == 0
```

### Full script

See "Generative Tables (Basics)" section above.

## Chat Completions

Generate chat completions using various models. Supports streaming and non-streaming modes.

```python
# Streaming
request = p.ChatRequest(
    model="openai/gpt-4o-mini",
    messages=[
        p.ChatEntry.system("You are a concise assistant."),
        p.ChatEntry.user("What is a llama?"),
    ],
    temperature=0.001,
    top_p=0.001,
    max_tokens=10,
    stream=True,
)
completion = jamai.generate_chat_completions(request)
for chunk in completion:
    print(chunk.text, end="", flush=True)
print("")

# Non-streaming
request = p.ChatRequest(
    model="openai/gpt-4o-mini",
    messages=[
        p.ChatEntry.system("You are a concise assistant."),
        p.ChatEntry.user("What is a llama?"),
    ],
    temperature=0.001,
    top_p=0.001,
    max_tokens=10,
    stream=False,
)
completion = jamai.generate_chat_completions(request)
print(completion.text)
```

## Embeddings

Generate embeddings for given input text.

```python
texts = ["What is love?", "What is a llama?"]
embeddings = jamai.generate_embeddings(
    p.EmbeddingRequest(
        model="ellm/BAAI/bge-m3",
        input=texts,
    )
)
# Inspect one of the embeddings
print(embeddings.data[0].embedding[:3])
# Print the text and its embedding
for text, data in zip(texts, embeddings.data):
    print(text, data.embedding[:3])
```

## Model Information

### Get Model Info

Retrieve information about available models.

```python
# Get all model info
models = jamai.model_info()
model = models.data[0]
print(f"Model: {model.id}  Context length: {model.context_length}")
# Model: openai/gpt-4o  Context length: 128000

# Get specific model info
models = jamai.model_info(name="openai/gpt-4o")
print(models.data[0])
# id='openai/gpt-4o' object='model' name='OpenAI GPT-4' context_length=128000 languages=['en', 'cn'] capabilities=['chat'] owned_by='openai'

# Filter based on capability: "chat", "embed", "rerank"
models = jamai.model_info(capabilities=["chat"])
for model in models.data:
    print(model)

models = jamai.model_info(capabilities=["embed"])
for model in models.data:
    print(model)

models = jamai.model_info(capabilities=["rerank"])
for model in models.data:
    print(model)
```

### Get Model IDs / Names

Get a list of available model IDs / names.

```python
# Get all model IDs
model_names = jamai.model_names()
print(model_names)
# ['ellm/meta-llama/Llama-3-8B-Instruct', 'ellm/meta-llama/Llama-3-70B-Instruct', 'openai/gpt-4o-mini', ..., 'cohere/rerank-english-v3.0', 'cohere/rerank-multilingual-v3.0']

# Model IDs with the preferred model at the top if available
model_names = jamai.model_names(prefer="openai/gpt-4o")
print(model_names[0])

# Filter based on capability: "chat", "embed", "rerank"
models = jamai.model_names(capabilities=["chat"])
print(models)

models = jamai.model_names(capabilities=["embed"])
print(models)

models = jamai.model_names(capabilities=["rerank"])
print(models)

```

## Examples

### Streamlit Chat App

Let's try to make a simple chat app using Streamlit.

```python
import streamlit as st

st.title("Simple chat")

try:
    # Create a Chat Table
    jamai.table.create_chat_table(
        p.ChatTableSchemaCreate(
            id="chat-simple",
            cols=[
                p.ColumnSchemaCreate(id="User", dtype="str"),
                p.ColumnSchemaCreate(
                    id="AI",
                    dtype="str",
                    gen_config=p.LLMGenConfig(
                        model="openai/gpt-4o-mini",  # Leave this out to use a default model
                        system_prompt="You are a pirate.",
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=500,
                    ),
                ),
            ],
        )
    )
except RuntimeError:
    # Table already exists
    pass

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

def response_generator(_prompt):
    completion = jamai.table.add_table_rows(
        "chat",
        p.RowAddRequest(
            table_id="chat-simple",
            data=[dict(User=_prompt)],
            stream=True,
        ),
    )
    for chunk in completion:
        if chunk.output_column_name != "AI":
            continue
        yield chunk.text

# Accept user input
if prompt := st.chat_input("What is up?"):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    # Display user message in chat message container
    with st.chat_message("user"):
        st.markdown(prompt)

    # Display assistant response in chat message container
    with st.chat_message("assistant"):
        response = st.write_stream(response_generator(prompt))
    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": response})
```
