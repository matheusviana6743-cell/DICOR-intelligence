from __future__ import annotations

import ast
from pathlib import Path

import interaction_audit


REPO_ROOT = Path(__file__).resolve().parents[1]
BOT_PATH = REPO_ROOT / "bot.py"


def _source() -> str:
    return BOT_PATH.read_text(encoding="utf-8")


def _last_class(module: ast.Module, name: str) -> ast.ClassDef:
    matches = [node for node in module.body if isinstance(node, ast.ClassDef) and node.name == name]
    assert matches, f"Classe {name} não encontrada"
    return matches[-1]


def _async_method(cls: ast.ClassDef, name: str) -> ast.AsyncFunctionDef:
    matches = [node for node in cls.body if isinstance(node, ast.AsyncFunctionDef) and node.name == name]
    assert matches, f"Método async {cls.name}.{name} não encontrado"
    return matches[-1]


def _calls_in_order(node: ast.AST) -> list[str]:
    calls: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            try:
                calls.append(ast.unparse(child.func))
            except Exception:
                calls.append("")
    return calls


def test_static_inventory_counts_are_available() -> None:
    audit = interaction_audit.audit_file(BOT_PATH)
    summary = audit.summary()

    assert summary["commands"] >= 60
    assert summary["views"] >= 140
    assert summary["buttons"] >= 350
    assert summary["modals"] >= 90
    assert summary["custom_ids"] >= 330
    assert summary["add_view_calls"] >= 70


def test_critical_v122_custom_ids_exist() -> None:
    audit = interaction_audit.audit_file(BOT_PATH)
    readiness = interaction_audit.critical_custom_ids_ready(
        audit,
        [
            "dic_v122_tarefa_finalizar",
            "dic_v122_tarefa_concluir",
            "dic_v116_investigacao_continuar",
            "dic_v116_investigacao_concluir",
            "dic_mesa_criar_tarefa_v1",
            "dic_mesa_ver_tarefas_v1",
        ],
    )

    assert readiness["ready"], readiness


def test_final_v122_view_is_persistent_and_has_only_two_task_buttons() -> None:
    module = ast.parse(_source())
    cls = _last_class(module, "V122TarefaGuiadaView")

    init_method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "__init__")
    init_text = ast.unparse(init_method)
    assert "timeout=None" in init_text

    button_methods: list[ast.AsyncFunctionDef] = []
    custom_ids: list[str] = []
    for item in cls.body:
        if not isinstance(item, ast.AsyncFunctionDef):
            continue
        for decorator in item.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if "discord.ui.button" not in ast.unparse(decorator.func):
                continue
            button_methods.append(item)
            for keyword in decorator.keywords:
                if keyword.arg == "custom_id":
                    custom_ids.append(ast.literal_eval(keyword.value))

    assert [method.name for method in button_methods] == ["finalizar", "concluir"]
    assert custom_ids == ["dic_v122_tarefa_finalizar", "dic_v122_tarefa_concluir"]


def test_v122_callbacks_ack_before_context_permission_and_lock() -> None:
    module = ast.parse(_source())
    cls = _last_class(module, "V122TarefaGuiadaView")
    finalizar = _async_method(cls, "finalizar")
    concluir = _async_method(cls, "concluir")

    finalizar_calls = _calls_in_order(finalizar)
    concluir_calls = _calls_in_order(concluir)

    assert "_v127_safe_defer" in finalizar_calls
    assert "_v127_safe_defer" in concluir_calls
    assert finalizar_calls.index("_v127_safe_defer") < finalizar_calls.index("self._contexto_item_seguro")
    assert concluir_calls.index("_v127_safe_defer") < concluir_calls.index("usuario_e_administrador")
    assert concluir_calls.index("_v127_safe_defer") < concluir_calls.index("self._contexto_item_seguro")


def test_global_interaction_error_handlers_are_installed_in_final_layer() -> None:
    source = _source()

    assert "discord.ui.View.on_error = _v127_view_on_error" in source
    assert "bot.tree.on_error = _v127_tree_on_error" in source
    assert "bot.on_command_error = _v127_on_command_error" in source
    assert "bot.setup_hook = _v12_types.MethodType(_v127_setup_hook, bot)" in source
