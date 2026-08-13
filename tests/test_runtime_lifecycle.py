from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from typing import Any, List


REPO_ROOT = Path(__file__).resolve().parents[1]
BOT_PATH = REPO_ROOT / "bot.py"


def _source() -> str:
    return BOT_PATH.read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    source = _source()
    module = ast.parse(source)
    matches = [
        node
        for node in module.body
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name
    ]
    assert matches, f"Função {name} não encontrada"
    return ast.get_source_segment(source, matches[-1]) or ""


def test_entrypoint_uses_runtime_lifecycle_guard() -> None:
    source = _source()

    assert "asyncio.run(_runtime_lifecycle_entrypoint())" in source
    assert "asyncio.run(main())" not in source


def test_runtime_lifecycle_guard_treats_main_return_as_fatal() -> None:
    function_source = _function_source("_runtime_lifecycle_entrypoint")

    assert "await main()" in function_source
    assert "MAIN LOOP EXITING" in function_source
    assert "raise RuntimeError" in function_source


def test_v127_setup_hook_does_not_run_static_audit_at_discord_startup() -> None:
    function_source = _function_source("_v127_setup_hook")

    assert "audit_file" not in function_source
    assert "ast.parse" not in function_source
    assert "Startup de interações concluído sem auditoria pesada" in function_source


def test_discord_ready_runtime_logs_exist() -> None:
    source = _source()

    assert "async def _runtime_discord_ready_log" in source
    assert "[DISCORD] READY" in source
    assert "[RUNTIME] Bot READY" in source


def test_supervisor_and_heartbeat_runtime_logs_exist() -> None:
    source = _source()
    supervisor_source = _function_source("_v74_supervisionar_discord")
    heartbeat_source = _function_source("_v74_heartbeat")

    assert "[RUNTIME] Inicializando Discord via bot.start(reconnect=True)." in supervisor_source
    assert "await bot.start(DISCORD_TOKEN, reconnect=True)" in supervisor_source
    assert "[RUNTIME] Heartbeat interno" in heartbeat_source
    assert "Supervisor ativo; conectando ao Discord" in source


def test_safe_deferred_interaction_finishes_with_followup() -> None:
    import bot

    class FakeResponse:
        def __init__(self) -> None:
            self.done = False
            self.deferred: List[dict[str, Any]] = []
            self.sent: List[dict[str, Any]] = []

        def is_done(self) -> bool:
            return self.done

        async def defer(self, **kwargs: Any) -> None:
            self.done = True
            self.deferred.append(kwargs)

        async def send_message(self, content: str, **kwargs: Any) -> None:
            self.done = True
            self.sent.append({"content": content, **kwargs})

    class FakeFollowup:
        def __init__(self) -> None:
            self.sent: List[dict[str, Any]] = []

        async def send(self, content: str, **kwargs: Any) -> None:
            self.sent.append({"content": content, **kwargs})

    class FakeInteraction:
        def __init__(self) -> None:
            self.response = FakeResponse()
            self.followup = FakeFollowup()
            self.data = {"custom_id": "dic_v122_tarefa_finalizar"}
            self.id = 123
            self.user = type("User", (), {"id": 456})()
            self.channel = type("Channel", (), {"id": 789})()
            self.guild = type("Guild", (), {"id": 101112})()

    async def scenario() -> FakeInteraction:
        interaction = FakeInteraction()
        ok_defer = await bot._v127_safe_defer(interaction, ephemeral=True, thinking=True, contexto="test")
        ok_send = await bot._v127_safe_send(interaction, "✅ finalizada", ephemeral=True, contexto="test")
        assert ok_defer
        assert ok_send
        return interaction

    interaction = asyncio.run(scenario())

    assert interaction.response.deferred
    assert not interaction.response.sent
    assert interaction.followup.sent
    assert interaction.followup.sent[0]["content"] == "✅ finalizada"
