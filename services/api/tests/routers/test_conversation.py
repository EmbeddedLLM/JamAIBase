from dataclasses import dataclass
from os.path import dirname, join, realpath
from typing import Generator

import pytest

from jamaibase import JamAI
from jamaibase.types import (
    AgentMetaResponse,
    CellCompletionResponse,
    ChatTableSchemaCreate,
    ColumnSchemaCreate,
    ConversationCreateRequest,
    ConversationMetaResponse,
    LLMGenConfig,
    MessageAddRequest,
    MessagesRegenRequest,
    MessageUpdateRequest,
    OkResponse,
    OrganizationCreate,
    OrgMemberRead,
    Page,
    ProjectMemberRead,
    Role,
    TableType,
)
from owl.utils.exceptions import ResourceNotFoundError
from owl.utils.test import (
    ELLM_DESCRIBE_CONFIG,
    ELLM_DESCRIBE_DEPLOYMENT,
    GPT_4O_MINI_CONFIG,
    GPT_4O_MINI_DEPLOYMENT,
    create_deployment,
    create_model_config,
    create_organization,
    create_project,
    create_user,
    get_file_map,
    upload_file,
)

TEST_FILE_DIR = join(dirname(dirname(realpath(__file__))), "files")
FILES = get_file_map(TEST_FILE_DIR)


@dataclass(slots=True)
class ConversationContext:
    """Dataclass to hold context for conversation tests."""

    superuser_id: str
    user_id: str
    org_id: str
    project_id: str
    template_table_id: str
    real_template_table_id: str
    multimodal_template_table_id: str


@pytest.fixture(scope="module")
def setup() -> Generator[ConversationContext, None, None]:
    """
    Fixture to set up the necessary environment for conversation tests.
    """
    with (
        create_user() as superuser,
        create_user({"email": "testuser@example.com", "name": "Test User"}) as user,
        create_organization(
            body=OrganizationCreate(name="Convo Org"),
            user_id=superuser.id,
        ) as superorg,
        create_project(
            dict(name="Convo Project"), user_id=superuser.id, organization_id=superorg.id
        ) as project,
    ):
        assert superuser.id == "0"
        assert superorg.id == "0"
        client = JamAI(user_id=superuser.id)
        membership = client.organizations.join_organization(
            user_id=user.id, organization_id=superorg.id, role=Role.MEMBER
        )
        assert isinstance(membership, OrgMemberRead)
        membership = client.projects.join_project(
            user_id=user.id, project_id=project.id, role=Role.MEMBER
        )
        assert isinstance(membership, ProjectMemberRead)
        client = JamAI(user_id=superuser.id, project_id=project.id)

        with (
            create_model_config(GPT_4O_MINI_CONFIG) as llm_config,
            create_model_config(ELLM_DESCRIBE_CONFIG) as llm_describe_config,
            create_deployment(GPT_4O_MINI_DEPLOYMENT),
            create_deployment(ELLM_DESCRIBE_DEPLOYMENT),
        ):
            # TODO: Don't call these templates since we have actual templates
            # Standard Template
            template_id = "chat-template-v2"
            template_cols = [
                ColumnSchemaCreate(id="User", dtype="str"),
                ColumnSchemaCreate(
                    id="AI",
                    dtype="str",
                    gen_config=LLMGenConfig(model=llm_describe_config.id, multi_turn=True),
                ),
            ]
            client.table.create_chat_table(
                ChatTableSchemaCreate(id=template_id, cols=template_cols)
            )

            # Real Template - for regeneration tests
            real_template_id = "real-chat-template-v2"
            real_template_cols = [
                ColumnSchemaCreate(id="User", dtype="str"),
                ColumnSchemaCreate(
                    id="AI",
                    dtype="str",
                    gen_config=LLMGenConfig(model=llm_config.id, multi_turn=True, temperature=1.0),
                ),
            ]
            client.table.create_chat_table(
                ChatTableSchemaCreate(id=real_template_id, cols=real_template_cols)
            )

            # Multimodal Template
            multimodal_template_id = "multimodal-chat-template-v2"
            multimodal_cols = [
                ColumnSchemaCreate(id="User", dtype="str"),
                ColumnSchemaCreate(id="Photo", dtype="image"),
                ColumnSchemaCreate(id="Audio", dtype="audio"),
                ColumnSchemaCreate(id="Doc", dtype="document"),
                ColumnSchemaCreate(
                    id="AI",
                    dtype="str",
                    gen_config=LLMGenConfig(
                        model=llm_describe_config.id,
                        multi_turn=True,
                        prompt="Photo: ${Photo} \nAudio: ${Audio} \nDocument: ${Doc} \n\n${User}",
                    ),
                ),
            ]
            client.table.create_chat_table(
                ChatTableSchemaCreate(id=multimodal_template_id, cols=multimodal_cols)
            )
            try:
                yield ConversationContext(
                    superuser_id=superuser.id,
                    user_id=user.id,
                    org_id=superorg.id,
                    project_id=project.id,
                    template_table_id=template_id,
                    real_template_table_id=real_template_id,
                    multimodal_template_table_id=multimodal_template_id,
                )
            finally:
                client.table.delete_table(TableType.CHAT, template_id, missing_ok=True)
                client.table.delete_table(TableType.CHAT, real_template_id, missing_ok=True)
                client.table.delete_table(TableType.CHAT, multimodal_template_id, missing_ok=True)


def _create_conversation_and_get_id(
    client: JamAI,
    setup_context: ConversationContext,
    initial_data: dict | None = None,
    check_regen: bool = False,
    multimodal: bool = False,
) -> str:
    """Helper to create a conversation and extract its ID from the streamed metadata."""
    # TODO: This function should just take in table ID instead of the booleans
    if check_regen:
        template_id = setup_context.real_template_table_id
    elif multimodal:
        template_id = setup_context.multimodal_template_table_id
    else:
        template_id = setup_context.template_table_id
    if initial_data is None:
        initial_data = {"User": "First message"}

    create_req = ConversationCreateRequest(agent_id=template_id, data=initial_data)
    response_stream = client.conversations.create_conversation(create_req)
    responses = [r for r in response_stream]

    metadata = responses[0]
    assert isinstance(metadata, ConversationMetaResponse), "Stream did not yield metadata first"
    conv_id = metadata.conversation_id
    assert conv_id is not None, "Metadata event did not contain conversation_id"
    return conv_id


def test_create_conversation(setup: ConversationContext):
    """
    Tests creating a new conversation and that a title is automatically generated.
    - Creates a conversation with a specific user prompt.
    - Verifies the first message is saved correctly.
    - Verifies an AI-generated title is set on the conversation metadata.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    # 1. Create the conversation
    user_prompt = "What is the theory of relativity?"
    conv_id = _create_conversation_and_get_id(client, setup, initial_data={"User": user_prompt})
    assert isinstance(conv_id, str)

    # 2. Verify the conversation was created with the correct message
    conv_details = client.conversations.list_messages(conv_id)
    assert conv_details.total == 1
    assert conv_details.items[0]["User"] == user_prompt

    # 3. Verify that the title was auto-generated and saved
    meta_after_creation = client.conversations.get_conversation(conv_id)
    assert isinstance(meta_after_creation.title, str)
    assert len(meta_after_creation.title) > 0, (
        "Title should have been auto-generated but is empty."
    )
    assert "There is a text with" in meta_after_creation.title


def test_create_conversation_with_provided_title(setup: ConversationContext):
    """
    Tests that providing a title during creation skips automatic generation.
    - Creates a conversation and passes a custom `title` parameter.
    - Verifies the conversation is created successfully.
    - Asserts that the final conversation title matches the one provided.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    # 1. Create the conversation with provided title
    provided_title = "Custom Test Title"
    create_req = ConversationCreateRequest(
        agent_id=setup.template_table_id,
        title=provided_title,
        data={"User": "This message should not be used for a title"},
    )
    response_stream = client.conversations.create_conversation(create_req)
    responses = [r for r in response_stream]
    metadata = responses[0]
    conv_id = metadata.conversation_id
    assert conv_id is not None

    # 2. Verify the conversation was created
    conv_details = client.conversations.list_messages(conv_id)
    assert conv_details.total == 1

    # 3. Verify that the provided title was used
    meta_after_creation = client.conversations.get_conversation(conv_id)
    assert meta_after_creation.title == provided_title


def test_list_conversations(setup: ConversationContext):
    """
    Tests listing conversations, ensuring only child chats are returned.
    - Creates a new conversation.
    - Calls the list endpoint.
    - Verifies the new conversation is in the list.
    - Verifies that parent agents/templates are not in the list.
    - Verifies conversation title search.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    conv_id = _create_conversation_and_get_id(client, setup)
    convos_page = client.conversations.list_conversations()
    assert convos_page.total >= 1
    assert any(c.conversation_id == conv_id for c in convos_page.items)
    # Verify that parent templates are NOT in the list
    assert not any(c.conversation_id == setup.template_table_id for c in convos_page.items)
    assert not any(
        c.conversation_id == setup.multimodal_template_table_id for c in convos_page.items
    )
    conv_id = _create_conversation_and_get_id(client, setup)
    client.conversations.rename_conversation_title(conv_id, "text with [3600] tokens")
    convos_page = client.conversations.list_conversations()
    assert convos_page.total >= 2
    # Verify literal search
    convos_page_search = client.conversations.list_conversations(search_query="[3600] tokens")
    assert convos_page_search.total == 1
    # Verify regex search
    convos_page_search = client.conversations.list_conversations(search_query="[0-9]{4}")
    assert convos_page_search.total == 1
    convos_page_search = client.conversations.list_conversations(search_query="text with")
    assert convos_page_search.total >= 2


def test_list_agents(setup: ConversationContext):
    """
    Tests listing agents, ensuring only parent templates are returned.
    - Creates a new child conversation.
    - Calls the list_agents endpoint.
    - Verifies parent templates are in the list.
    - Verifies the new child conversation is NOT in the list.
    - Verifies agent id search.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    conv_id = _create_conversation_and_get_id(client, setup)
    agents_page = client.conversations.list_agents()
    assert agents_page.total == 3
    # Verify that parent templates ARE in the list
    assert any(c.conversation_id == setup.template_table_id for c in agents_page.items)
    assert any(c.conversation_id == setup.multimodal_template_table_id for c in agents_page.items)
    # Verify that child conversations are NOT in the list
    assert not any(c.conversation_id == conv_id for c in agents_page.items)
    agents_page_search = client.conversations.list_agents(search_query="multimodal-")
    assert agents_page_search.total == 1
    agents_page_search = client.conversations.list_agents(search_query="chat-template-v2")
    assert agents_page_search.total == 3


def test_get_conversation(setup: ConversationContext):
    """
    Tests fetching the metadata for a single, specific conversation.
    - Creates a conversation.
    - Fetches it by its ID.
    - Verifies the returned metadata matches the created conversation.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    conv_id = _create_conversation_and_get_id(client, setup)
    convo_meta = client.conversations.get_conversation(conv_id)
    assert isinstance(convo_meta, ConversationMetaResponse)
    assert convo_meta.conversation_id == conv_id
    assert convo_meta.parent_id == setup.template_table_id
    assert convo_meta.created_by == setup.user_id


def test_get_agent(setup: ConversationContext):
    """
    Tests fetching the metadata for a single, specific agent/template.
    - Fetches a known agent by its ID.
    - Verifies the returned metadata is correct.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    agent_meta = client.conversations.get_agent(setup.template_table_id)
    assert isinstance(agent_meta, AgentMetaResponse)
    assert agent_meta.agent_id == setup.template_table_id
    assert agent_meta.created_by == setup.superuser_id


def test_generate_conversation_title(setup: ConversationContext):
    """
    Tests explicitly generating a title for an existing conversation.
    - Creates a conversation (which gets an auto-generated title).
    - Calls the dedicated `generate_title` endpoint.
    - Verifies the conversation's title is updated to the newly generated one.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    conv_id = _create_conversation_and_get_id(client, setup)
    response = client.conversations.generate_title(conversation_id=conv_id)
    assert isinstance(response, ConversationMetaResponse)
    assert isinstance(response.title, str)
    assert len(response.title) > 0

    updated_table_meta = client.conversations.get_conversation(conv_id)
    assert updated_table_meta.title == response.title


def test_rename_conversation_title(setup: ConversationContext):
    """
    Tests renaming the title of an existing conversation.
    - Creates a conversation.
    - Calls the rename endpoint with a new title.
    - Verifies the conversation metadata reflects the new title.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    conv_id = _create_conversation_and_get_id(client, setup)
    new_title = "renamed-conversation-title"
    table_meta = client.conversations.get_conversation(conv_id)
    assert table_meta.title != new_title, "Title should not match the new title initially"

    rename_response = client.conversations.rename_conversation_title(conv_id, new_title)
    assert isinstance(rename_response, ConversationMetaResponse)
    assert rename_response.title == new_title

    updated_table_meta = client.conversations.get_conversation(conv_id)
    assert updated_table_meta.title == new_title


def test_delete_conversation(setup: ConversationContext):
    """
    Tests the permanent deletion of a conversation.
    - Creates a conversation.
    - Deletes it.
    - Verifies that fetching the conversation by its ID now raises a ResourceNotFoundError.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    conv_id = _create_conversation_and_get_id(client, setup)
    delete_response = client.conversations.delete_conversation(conv_id)
    assert isinstance(delete_response, OkResponse)
    with pytest.raises(ResourceNotFoundError):
        client.conversations.list_messages(conv_id)


def test_send_message(setup: ConversationContext):
    """
    Tests sending a follow-up message to an existing conversation.
    - Creates a conversation with one message.
    - Sends a second message to the same conversation.
    - Verifies the conversation now contains two messages.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    conv_table_id = _create_conversation_and_get_id(client, setup)
    second_prompt = "And what is the capital of Germany?"
    send_req = MessageAddRequest(
        conversation_id=conv_table_id,
        data={"User": second_prompt},
    )
    stream_gen = client.conversations.send_message(send_req)
    ai_response_chunks = [c for c in stream_gen]
    assert len(ai_response_chunks) > 0, "Send message stream was empty"

    conv_details = client.conversations.list_messages(conv_table_id)
    assert conv_details.total == 2
    assert conv_details.items[1]["User"] == second_prompt
    assert "text with [8] tokens" in conv_details.items[1]["AI"]


def test_list_messages(setup: ConversationContext):
    """
    Tests fetching the full message history of a conversation.
    - Creates a conversation with an initial message.
    - Fetches the message list.
    - Verifies the content of the first message.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    conv_id = _create_conversation_and_get_id(client, setup)
    convo_details = client.conversations.list_messages(conv_id)
    assert isinstance(convo_details, Page)
    assert convo_details.total == 1
    first_turn = convo_details.items[0]
    assert first_turn["User"] == "First message"
    assert "text with [3] tokens" in first_turn["AI"]
    # Threads
    # TODO: Move this to its own test
    response = client.conversations.get_threads(conv_id)
    thread = response.threads["AI"].thread
    assert len(thread) > 2
    assert thread[0].role == "system"
    assert thread[1].role == "user"
    assert thread[1].user_prompt == "First message"
    assert thread[2].role == "assistant"
    assert "text with [3] tokens" in thread[2].content


def test_regen_message(setup: ConversationContext):
    """
    Tests regenerating the last AI response in a conversation.
    - Creates a conversation.
    - Stores the original AI response.
    - Calls the regeneration endpoint.
    - Verifies the new AI response is different from the original.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    conv_id = _create_conversation_and_get_id(
        client, setup, initial_data={"User": "Suggest a movie"}, check_regen=True
    )
    # 1. Get the initial message
    convo_details = client.conversations.list_messages(conv_id)
    assert convo_details.total == 1
    message_row = convo_details.items[0]
    row_id = message_row["ID"]
    original_ai_content = message_row["AI"]
    assert original_ai_content is not None

    # 2. Update the message (Optional)
    new_content = "Suggest a movie before 1950."
    update_req = MessageUpdateRequest(
        conversation_id=conv_id,
        row_id=row_id,
        data={"User": new_content},
    )
    update_response = client.conversations.update_message(update_req)
    assert isinstance(update_response, OkResponse)

    # 3. Regenerate the AI response
    regen_req = MessagesRegenRequest(
        conversation_id=conv_id,
        row_id=row_id,
    )
    stream_gen = client.conversations.regen_message(regen_req)
    responses = list(stream_gen)
    assert len(responses) > 0
    assert all(isinstance(r, CellCompletionResponse) for r in responses)

    # 3. Verify the regeneration
    updated_details = client.conversations.list_messages(conv_id)
    assert updated_details.total == 1
    updated_message_row = updated_details.items[0]
    assert updated_message_row["AI"] != original_ai_content


def test_regen_messages(setup: ConversationContext):
    """
    Tests regenerating from an earlier point in a multi-message conversation.
    - Creates a conversation with three messages.
    - Calls regenerate starting from the first message's ID.
    - Verifies that all three AI responses have changed.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    conv_id = _create_conversation_and_get_id(
        client, setup, initial_data={"User": "Suggest a movie"}, check_regen=True
    )
    # 1. Send messages
    send_req = MessageAddRequest(
        conversation_id=conv_id,
        data={"User": "Suggest second movie"},
    )
    list(client.conversations.send_message(send_req))  # consume stream
    send_req = MessageAddRequest(
        conversation_id=conv_id,
        data={"User": "Describe the movies"},
    )
    list(client.conversations.send_message(send_req))  # consume stream

    # 2. Get the conversation details
    convo_details = client.conversations.list_messages(conv_id)
    assert convo_details.total == 3
    first_row = convo_details.items[0]
    second_row = convo_details.items[1]
    third_row = convo_details.items[2]
    assert first_row["User"] == "Suggest a movie"
    assert second_row["User"] == "Suggest second movie"
    assert third_row["User"] == "Describe the movies"

    # 3. Update the message (Optional)
    new_content = "Suggest a movie before 1950."
    update_req = MessageUpdateRequest(
        conversation_id=conv_id,
        row_id=first_row["ID"],
        data={"User": new_content},
    )
    update_response = client.conversations.update_message(update_req)
    assert isinstance(update_response, OkResponse)

    # 4. Regenerate both messages
    regen_req = MessagesRegenRequest(
        conversation_id=conv_id,
        row_id=first_row["ID"],
    )
    stream_gen = client.conversations.regen_message(regen_req)
    responses = list(stream_gen)
    assert len(responses) > 0
    assert all(isinstance(r, CellCompletionResponse) for r in responses)

    # 5. Verify the regeneration
    updated_details = client.conversations.list_messages(conv_id)
    assert updated_details.total == 3
    updated_first_row = updated_details.items[0]
    updated_second_row = updated_details.items[1]
    updated_third_row = updated_details.items[2]
    assert updated_first_row["User"] != first_row["User"]
    assert updated_second_row["User"] == second_row["User"]
    assert updated_third_row["User"] == third_row["User"]
    assert updated_first_row["AI"] != first_row["AI"]
    assert updated_second_row["AI"] != second_row["AI"]
    assert updated_third_row["AI"] != third_row["AI"]


def test_update_message(setup: ConversationContext):
    """
    Tests editing the content of a specific message.
    - Creates a conversation.
    - Updates the 'User' content of the first message.
    - Verifies the change while ensuring the 'AI' content is untouched.
    - Updates the 'AI' content and verifies the change.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    conv_id = _create_conversation_and_get_id(client, setup)
    # 1. Get the initial message to find its row_id
    convo_details = client.conversations.list_messages(conv_id)
    assert convo_details.total == 1
    message_row = convo_details.items[0]
    row_id = message_row["ID"]
    assert message_row["User"] == "First message"

    # 2. Update the message
    new_content = "This is the edited first message."
    update_req = MessageUpdateRequest(
        conversation_id=conv_id,
        row_id=row_id,
        data={"User": new_content},
    )
    update_response = client.conversations.update_message(update_req)
    assert isinstance(update_response, OkResponse)

    # 3. Verify the update
    updated_details = client.conversations.list_messages(conv_id)
    assert updated_details.total == 1
    updated_message_row = updated_details.items[0]
    assert updated_message_row["User"] == new_content
    assert updated_message_row["AI"] == message_row["AI"]  # AI part should be unchanged

    # 2. Update the message
    new_ai_content = "AI Response"
    update_req = MessageUpdateRequest(
        conversation_id=conv_id,
        row_id=row_id,
        data={"AI": new_ai_content},
    )
    update_response = client.conversations.update_message(update_req)
    assert isinstance(update_response, OkResponse)

    # 3. Verify the update
    updated_details = client.conversations.list_messages(conv_id)
    assert updated_details.total == 1
    updated_message_row = updated_details.items[0]
    assert updated_message_row["User"] == new_content
    assert updated_message_row["AI"] == new_ai_content


def test_conversation_with_image(setup: ConversationContext):
    """
    Tests starting a conversation with a multimodal (image) input.
    - Uploads an image to get a file URI.
    - Creates a conversation using a multimodal agent, passing the image URI.
    - Verifies the AI response correctly identifies the image content.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    photo_uri = upload_file(client, FILES["rabbit.jpeg"]).uri
    initial_data = {"User": "What animal is in this image?", "Photo": photo_uri}
    conv_id = _create_conversation_and_get_id(
        client, setup, initial_data=initial_data, multimodal=True
    )
    messages = client.conversations.list_messages(conv_id)
    assert messages.total == 1
    assert "[image/jpeg], shape [(1200, 1600, 3)]" in messages.items[0]["AI"].lower()


def test_conversation_with_audio(setup: ConversationContext):
    """
    Tests starting a conversation with a multimodal (audio) input.
    - Uploads an audio file to get a file URI.
    - Creates a conversation using a multimodal agent, passing the audio URI.
    - Verifies the AI response indicates successful processing of the audio.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    audio_uri = upload_file(client, FILES["turning-a4-size-magazine.mp3"]).uri
    initial_data = {"User": "What does the audio say?", "Audio": audio_uri}
    conv_id = _create_conversation_and_get_id(
        client, setup, initial_data=initial_data, multimodal=True
    )
    messages = client.conversations.list_messages(conv_id)
    assert messages.total == 1
    assert "[audio/mpeg]" in messages.items[0]["AI"].lower()


def test_conversation_with_document(setup: ConversationContext):
    """
    Tests starting a conversation with a multimodal (document) input.
    - Uploads a document to get a file URI.
    - Creates a conversation using a multimodal agent, passing the document URI.
    - Verifies the AI response correctly processes the document content.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    doc_uri = upload_file(client, FILES["creative-story.md"]).uri
    initial_data = {"User": "Summarize this document in one sentence.", "Doc": doc_uri}
    conv_id = _create_conversation_and_get_id(
        client, setup, initial_data=initial_data, multimodal=True
    )
    messages = client.conversations.list_messages(conv_id)
    assert messages.total == 1
    assert "text with [398] tokens" in messages.items[0]["AI"].lower()


def test_full_lifecycle(setup: ConversationContext):
    """
    Tests the complete sequence of user actions from creation to deletion.
    - Creates a conversation, which auto-generates a title.
    - Sends a follow-up message.
    - Regenerates the last message.
    - Renames the conversation title.
    - Deletes the conversation and verifies it's gone.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    # 1. Create
    conv_id = _create_conversation_and_get_id(
        client, setup, initial_data={"User": "Suggest a movie"}, check_regen=True
    )
    assert client.conversations.list_messages(conv_id).total == 1
    meta = client.conversations.get_conversation(conv_id)
    assert len(meta.title) > 0

    # 2. Send Message
    send_req = MessageAddRequest(
        conversation_id=conv_id,
        data={"User": "Suggest second movie"},
    )
    list(client.conversations.send_message(send_req))  # consume stream
    messages_after_send = client.conversations.list_messages(conv_id)
    assert messages_after_send.total == 2

    # 3. Regenerate Message
    last_message = messages_after_send.items[-1]
    last_row_id = last_message["ID"]
    original_ai_content = last_message["AI"]
    regen_req = MessagesRegenRequest(conversation_id=conv_id, row_id=last_row_id)
    list(client.conversations.regen_message(regen_req))  # consume stream
    messages_after_regen = client.conversations.list_messages(conv_id)
    assert messages_after_regen.total == 2
    regenerated_message = messages_after_regen.items[-1]
    assert regenerated_message["User"] == "Suggest second movie"
    assert regenerated_message["AI"] != original_ai_content

    # 4. Rename
    new_title = "Best Movie Agent"
    client.conversations.rename_conversation_title(conv_id, new_title)
    updated_table_meta = client.conversations.get_conversation(conv_id)
    assert updated_table_meta.title == new_title

    # 5. Delete
    client.conversations.delete_conversation(conv_id)
    with pytest.raises(ResourceNotFoundError):
        client.conversations.list_messages(conv_id)


def test_full_lifecycle_with_files(setup: ConversationContext):
    """
    Tests a complete lifecycle using multimodal inputs.
    - Creates a conversation with an image.
    - Sends a follow-up with audio.
    - Updates and regenerates the first (image) message.
    - Sends a final follow-up with a document.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    # 1. Create with image
    photo_uri = upload_file(client, FILES["rabbit.jpeg"]).uri
    initial_data = {"User": "What is this animal?", "Photo": photo_uri}
    conv_id = _create_conversation_and_get_id(client, setup, initial_data, multimodal=True)
    messages = client.conversations.list_messages(conv_id)
    assert messages.total == 1
    response_text = messages.items[0]["AI"].lower()
    assert (
        "[image/jpeg], shape [(1200, 1600, 3)]" in response_text
        and "text with [10] tokens" in response_text
    )
    first_row_id = messages.items[0]["ID"]

    # 2. Send a follow-up with audio
    audio_uri = upload_file(client, FILES["turning-a4-size-magazine.mp3"]).uri
    send_req = MessageAddRequest(
        conversation_id=conv_id,
        data={"User": "What sound is this?", "Audio": audio_uri},
    )
    list(client.conversations.send_message(send_req))
    messages = client.conversations.list_messages(conv_id)
    assert messages.total == 2
    assert "[audio/mpeg]" in messages.items[1]["AI"].lower()

    # 3. Update and Regenerate the first message (the one with the image)
    new_content = "What is this animal? Why is it so popular?"
    update_req = MessageUpdateRequest(
        conversation_id=conv_id,
        row_id=first_row_id,
        data={"User": new_content},
    )
    update_response = client.conversations.update_message(update_req)
    assert isinstance(update_response, OkResponse)
    regen_req = MessagesRegenRequest(conversation_id=conv_id, row_id=first_row_id)
    list(client.conversations.regen_message(regen_req))
    messages_after_regen = client.conversations.list_messages(conv_id)
    assert messages_after_regen.total == 2
    response_text = messages_after_regen.items[0]["AI"].lower()
    assert (
        "[image/jpeg], shape [(1200, 1600, 3)]" in response_text
        and "text with [15] tokens" in response_text
    )

    # 4. Send a follow-up with a document
    doc_uri = upload_file(client, FILES["creative-story.md"]).uri
    send_req = MessageAddRequest(
        conversation_id=conv_id,
        data={"User": "Summarize this document in one sentence.", "Doc": doc_uri},
    )
    list(client.conversations.send_message(send_req))
    messages = client.conversations.list_messages(conv_id)
    assert messages.total == 3
    assert "text with [398] tokens" in messages.items[2]["AI"].lower()


def test_conversation_permissions(setup: ConversationContext):
    """
    Tests that users cannot access conversations they do not own.
    - User1 creates a conversation.
    - User2 (in the same project) tries to access User1's conversation.
    - Asserts that all access attempts by User2 fail with ResourceNotFoundError.
    """
    client1 = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    conv_id1 = _create_conversation_and_get_id(client1, setup)

    with create_user({"email": "user2@example.com", "name": "user2"}) as user2:
        su_client = JamAI(user_id=setup.superuser_id)
        su_client.organizations.join_organization(
            user_id=user2.id, organization_id=setup.org_id, role=Role.GUEST
        )
        su_client.projects.join_project(
            user_id=user2.id, project_id=setup.project_id, role=Role.GUEST
        )
        client2 = JamAI(user_id=user2.id, project_id=setup.project_id)

        assert client2.conversations.list_conversations().total == 0

        with pytest.raises(ResourceNotFoundError):
            client2.conversations.list_messages(conv_id1)


def test_invalid_operations(setup: ConversationContext):
    """
    Tests various invalid API calls to ensure they fail with the correct errors.
    - Tries to get/rename a non-existent conversation.
    - Tries to create a conversation from a non-existent agent template.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    non_existent_id = "non-existent-conversation-id"

    with pytest.raises(ResourceNotFoundError):
        client.conversations.list_messages(non_existent_id)
    with pytest.raises(ResourceNotFoundError):
        client.conversations.rename_conversation_title(non_existent_id, "new-title")

    with pytest.raises(ResourceNotFoundError):
        create_req = ConversationCreateRequest(
            agent_id="non-existent-template",
            data={"User": "test"},
        )
        list(client.conversations.create_conversation(create_req))
