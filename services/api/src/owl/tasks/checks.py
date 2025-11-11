from loguru import logger

from jamaibase import JamAI
from jamaibase.types import ChatRequest
from owl.configs import ENV_CONFIG, celery_app


@celery_app.task
def test_models():
    client = JamAI(
        api_base=f"http://localhost:{ENV_CONFIG.port}/api",
        user_id="0",
        token=ENV_CONFIG.service_key_plain,
    )
    projects = client.projects.list_projects("0", limit=1).items
    if len(projects) == 0:
        logger.error("No projects found.")
        return
    project = projects[0]
    client = JamAI(
        api_base=f"http://localhost:{ENV_CONFIG.port}/api",
        user_id="0",
        project_id=project.id,
        token=ENV_CONFIG.service_key_plain,
    )

    # Test chat completion
    models = client.model_info(capabilities=["chat"]).data
    status = {model.id: False for model in models}
    for model in models:
        logger.debug(f"------ {model.id} {model.name} ------")
        for stream in [True, False]:
            try:
                response = client.generate_chat_completions(
                    ChatRequest(
                        model=model.id,
                        messages=[{"role": "user", "content": "Hello"}],
                        max_tokens=2,
                        stream=stream,
                    ),
                )
                if stream:
                    for chunk in response:
                        logger.debug(chunk)
                else:
                    logger.debug(response)
            except Exception as e:
                logger.error(f'Model "{model.name}" ({model.id}) failed: {repr(e)}')
        status[model.id] = True
    logger.info(
        f"Chat model test: {sum(status.values()):,d} out of {len(status):,d} models passed."
    )

    # Test embedding
    models = client.model_info(capabilities=["embed"]).data
    status = {model.id: False for model in models}
    for model in models:
        logger.debug(f"------ {model.id} {model.name} ------")
        for text in ["What is a llama?", ["What is a llama?", "What is an alpaca?"]]:
            for encoding in ["float", "base64"]:
                try:
                    response = client.generate_embeddings(
                        dict(model=model.id, input=text, encoding=encoding),
                    )
                    logger.debug(response)
                except Exception as e:
                    logger.error(f'Model "{model.name}" ({model.id}) failed: {repr(e)}')
        status[model.id] = True
    logger.info(
        f"Embedding model test: {sum(status.values()):,d} out of {len(status):,d} models passed."
    )

    # Test rerank
    models = client.model_info(capabilities=["rerank"]).data
    status = {model.id: False for model in models}
    for model in models:
        logger.debug(f"------ {model.id} {model.name} ------")
        try:
            response = client.rerank(
                dict(model=model.id, documents=["Norway", "Sweden"], query="Stockholm"),
            )
            logger.debug(response)
        except Exception as e:
            logger.error(f'Model "{model.name}" ({model.id}) failed: {repr(e)}')
        status[model.id] = True
    logger.info(
        f"Reranking model test: {sum(status.values()):,d} out of {len(status):,d} models passed."
    )
