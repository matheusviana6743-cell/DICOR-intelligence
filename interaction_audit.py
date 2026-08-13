from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List


COMMAND_DECORATOR_MARKERS = (
    "bot.command",
    "bot.hybrid_command",
    "bot.tree.command",
    "tree.command",
    "app_commands.command",
    "commands.command",
    "commands.hybrid_command",
)

SELECT_MARKERS = (
    "discord.ui.Select",
    "UserSelect",
    "RoleSelect",
    "ChannelSelect",
    "MentionableSelect",
)

RESPONSE_MARKERS = (
    "response.defer",
    "response.send_message",
    "followup.send",
    "edit_original_response",
)


@dataclass(frozen=True)
class CommandInfo:
    function: str
    line: int
    decorator: str


@dataclass(frozen=True)
class ViewInfo:
    name: str
    line: int
    bases: List[str]
    timeout_none: bool


@dataclass(frozen=True)
class ButtonInfo:
    view: str
    callback: str
    line: int
    label: str
    custom_id: str


@dataclass(frozen=True)
class ModalInfo:
    name: str
    line: int
    bases: List[str]


@dataclass(frozen=True)
class InteractionAudit:
    commands: List[CommandInfo] = field(default_factory=list)
    views: List[ViewInfo] = field(default_factory=list)
    buttons: List[ButtonInfo] = field(default_factory=list)
    modals: List[ModalInfo] = field(default_factory=list)
    selects: List[Dict[str, Any]] = field(default_factory=list)
    custom_ids: List[Dict[str, Any]] = field(default_factory=list)
    add_view_calls: List[Dict[str, Any]] = field(default_factory=list)
    response_calls: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def custom_id_literals(self) -> List[str]:
        literals: List[str] = []
        for item in self.custom_ids:
            value = str(item.get("value") or "")
            if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
                literals.append(value[1:-1])
        return literals

    @property
    def duplicate_custom_id_literals(self) -> Dict[str, int]:
        return {key: count for key, count in Counter(self.custom_id_literals).items() if count > 1}

    @property
    def command_names(self) -> List[str]:
        return [cmd.function for cmd in self.commands]

    @property
    def duplicate_command_functions(self) -> Dict[str, int]:
        return {key: count for key, count in Counter(self.command_names).items() if count > 1}

    @property
    def persistent_views(self) -> List[ViewInfo]:
        return [view for view in self.views if view.timeout_none]

    def summary(self) -> Dict[str, Any]:
        return {
            "commands": len(self.commands),
            "views": len(self.views),
            "persistent_views": len(self.persistent_views),
            "buttons": len(self.buttons),
            "selects": len(self.selects),
            "modals": len(self.modals),
            "custom_ids": len(self.custom_ids),
            "custom_id_literals": len(self.custom_id_literals),
            "custom_id_literal_duplicates": dict(sorted(self.duplicate_custom_id_literals.items())),
            "command_function_duplicates": dict(sorted(self.duplicate_command_functions.items())),
            "add_view_calls": len(self.add_view_calls),
            "response_calls": len(self.response_calls),
        }


def _unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _decorator_text(decorator: ast.AST) -> str:
    if isinstance(decorator, ast.Call):
        return _unparse(decorator.func)
    return _unparse(decorator)


def _call_keywords(call: ast.Call) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for keyword in call.keywords:
        if keyword.arg:
            values[keyword.arg] = _unparse(keyword.value)
    return values


def _class_timeout_none(node: ast.ClassDef) -> bool:
    for item in node.body:
        if not isinstance(item, ast.FunctionDef) or item.name != "__init__":
            continue
        for sub in ast.walk(item):
            if not isinstance(sub, ast.Call):
                continue
            if not _unparse(sub.func).endswith("super().__init__"):
                continue
            for keyword in sub.keywords:
                if keyword.arg == "timeout" and isinstance(keyword.value, ast.Constant) and keyword.value.value is None:
                    return True
    return False


def audit_source(source: str) -> InteractionAudit:
    module = ast.parse(source)
    audit = InteractionAudit()
    commands: List[CommandInfo] = []
    views: List[ViewInfo] = []
    buttons: List[ButtonInfo] = []
    modals: List[ModalInfo] = []
    selects: List[Dict[str, Any]] = []
    custom_ids: List[Dict[str, Any]] = []
    add_view_calls: List[Dict[str, Any]] = []
    response_calls: List[Dict[str, Any]] = []

    for node in ast.walk(module):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                text = _decorator_text(decorator)
                if any(marker in text for marker in COMMAND_DECORATOR_MARKERS):
                    commands.append(CommandInfo(function=node.name, line=node.lineno, decorator=text))

        if isinstance(node, ast.ClassDef):
            bases = [_unparse(base) for base in node.bases]
            is_view = any(base.endswith("View") or ".View" in base for base in bases)
            is_modal = any(base.endswith("Modal") or ".Modal" in base for base in bases)
            if is_view:
                views.append(ViewInfo(name=node.name, line=node.lineno, bases=bases, timeout_none=_class_timeout_none(node)))
            if is_modal:
                modals.append(ModalInfo(name=node.name, line=node.lineno, bases=bases))
            for item in node.body:
                if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for decorator in item.decorator_list:
                    if not isinstance(decorator, ast.Call):
                        continue
                    text = _decorator_text(decorator)
                    if "discord.ui.button" not in text:
                        continue
                    keywords = _call_keywords(decorator)
                    buttons.append(
                        ButtonInfo(
                            view=node.name,
                            callback=item.name,
                            line=item.lineno,
                            label=keywords.get("label", ""),
                            custom_id=keywords.get("custom_id", ""),
                        )
                    )

        if isinstance(node, ast.Call):
            func = _unparse(node.func)
            if func == "bot.add_view" or func.endswith(".bot.add_view"):
                add_view_calls.append({"line": node.lineno, "call": _unparse(node)})
            if any(marker in func for marker in RESPONSE_MARKERS):
                response_calls.append({"line": node.lineno, "call": func})
            if any(marker in func for marker in SELECT_MARKERS) or func.endswith("Select"):
                selects.append({"line": node.lineno, "call": func})
            for keyword in node.keywords:
                if keyword.arg == "custom_id":
                    custom_ids.append({"line": node.lineno, "value": _unparse(keyword.value)})

    audit.commands.extend(commands)
    audit.views.extend(views)
    audit.buttons.extend(buttons)
    audit.modals.extend(modals)
    audit.selects.extend(selects)
    audit.custom_ids.extend(custom_ids)
    audit.add_view_calls.extend(add_view_calls)
    audit.response_calls.extend(response_calls)
    return audit


def audit_file(path: str | Path) -> InteractionAudit:
    return audit_source(Path(path).read_text(encoding="utf-8"))


def critical_custom_ids_ready(audit: InteractionAudit, required_ids: Iterable[str]) -> Dict[str, Any]:
    ids = set(audit.custom_id_literals)
    missing = [custom_id for custom_id in required_ids if custom_id not in ids]
    return {
        "ready": not missing,
        "missing": missing,
        "checked": list(required_ids),
    }
