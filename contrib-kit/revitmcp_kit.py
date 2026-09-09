# -*- coding: utf-8 -*-
"""Набор разработчика инструментов Revit MCP.

Один файл, четыре команды. Репозиторий сервера для работы не нужен.

    python revitmcp_kit.py new <domain> <tool> [--get]   создать каркас
    python revitmcp_kit.py check                          проверить конвенции
    python revitmcp_kit.py probe                          прогнать на своём Revit
    python revitmcp_kit.py pack                           собрать пакет для сдачи

Только стандартная библиотека: работает на любом python3, включая тот, что
приносит с собой pyRevit (bin\\cengines\\CPY*\\python.exe). Ни uv, ни pytest,
ни интернета.

Проверки конвенций лежат в conventions.py рядом — это точная копия того файла,
по которому сдачу проверяет сопровождающий. Не редактируйте его: расхождение
означает, что «check» скажет «всё хорошо», а приёмка откажет.
"""

import argparse
import io
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    import conventions
except ImportError:
    sys.stderr.write(
        "conventions.py не найден рядом с revitmcp_kit.py.\n"
        "Набор нужно распаковать целиком.\n"
    )
    raise SystemExit(2)

BRIDGE = "http://127.0.0.1:48884/revit_mcp"

IDENT_HINT = "только строчные латинские буквы, цифры и подчёркивание"


# ---------------------------------------------------------------------------
# общее
# ---------------------------------------------------------------------------

def _die(message):
    sys.stderr.write("ОШИБКА: {}\n".format(message))
    raise SystemExit(1)


def _valid_ident(value):
    return bool(value) and value[0].isalpha() and value.replace("_", "").isalnum() \
        and value.lower() == value


def _find_package():
    """Найти каталог пакета в текущей папке (или в ней самой)."""
    candidates = []
    for root in (os.getcwd(),):
        if os.path.isfile(os.path.join(root, "manifest.json")):
            candidates.append(root)
        for name in sorted(os.listdir(root)):
            path = os.path.join(root, name)
            if os.path.isfile(os.path.join(path, "manifest.json")):
                candidates.append(path)
    if not candidates:
        _die("пакет не найден. Сначала: python revitmcp_kit.py new <domain> <tool>")
    if len(candidates) > 1:
        _die("рядом несколько пакетов: {}. Перейдите в нужный каталог."
             .format(", ".join(os.path.basename(c) for c in candidates)))
    return candidates[0]


def _load_manifest(package_dir):
    with io.open(os.path.join(package_dir, "manifest.json"), encoding="utf-8") as h:
        return json.load(h)


def _read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def _sources(package_dir, manifest):
    domain = manifest["domain"]
    route = os.path.join(package_dir, "revit_mcp", domain + ".py")
    tool = os.path.join(package_dir, "tools", domain + "_tools.py")
    for path in (route, tool):
        if not os.path.isfile(path):
            _die("нет файла {}".format(path))
    return domain, route, tool


# ---------------------------------------------------------------------------
# new
# ---------------------------------------------------------------------------

ROUTE_TEMPLATE = u'''# -*- coding: utf-8 -*-
"""
{title} module for Revit MCP.

IronPython 3 внутри процесса Revit, на уровне языка Python 3.4: без f-строк
("{{}}".format(x) вместо них), без async, без pathlib, без современных
аннотаций типов. Код должен быть валиден и как обычный Python 3 — иначе его
нельзя проверить вне Revit. Хелперы импортируются ОТНОСИТЕЛЬНО (from .utils
import ...) — плоский `from utils import ...` не грузится под IronPython 3.
"""

from .utils import get_element_name, get_element_id_value{suppress_import}
from pyrevit import routes, DB
import logging

logger = logging.getLogger(__name__)
{mm_constant}

def register_{domain}_routes(api):
    """Register {domain} routes with the API."""

    @api.route("/{domain}/", methods=["{method}"]){handler_signature}
        """
        TODO опишите, что возвращает маршрут. Это докстринг для разработчика.

        Payload:
        {{
            "example": "value"
        }}
        """
        try:
            if not doc:
                return routes.make_response(
                    data={{"error": "No active Revit document"}}, status=503
                )
{payload_block}
            # ---------------------------------------------------------------
            # TODO ваша логика.
            #
            # ЧИТАЕТЕ? Транзакцию НЕ открывать — читающий маршрут не должен
            # помечать документ изменённым.
            #
            # ПИШЕТЕ? Только такой формой, и suppress_warnings строкой после
            # Start(): без него штатное предупреждение Revit открывает
            # модальное окно и вешает сервер навсегда.
            #
            #     t = DB.Transaction(doc, "{title} via MCP")
            #     t.Start()
            #     suppress_warnings(t)
            #     try:
            #         ...
            #         t.Commit()
            #     except Exception:
            #         if t.HasStarted() and not t.HasEnded():
            #             t.RollBack()
            #         raise
            #
            # Идентификаторы: get_element_id_value(elem) на чтение,
            # make_element_id(value) на создание. Никогда .IntegerValue и
            # никогда DB.ElementId(<int>) — падает на Revit 2027.
            #
            # Имена: get_element_name(elem) — сохраняет кириллицу.
            #
            # Много элементов? Ловите исключение на каждом, считайте пропуски
            # и отдавайте их в ответе. "success" с молча пропущенными
            # элементами — это баг, который здесь уже случался.
            # ---------------------------------------------------------------

            results = []
            skipped = 0

            return routes.make_response(
                data={{
                    "status": "success",
                    "results": results,
                    "skipped": skipped,
                }}
            )

        except Exception as e:
            logger.error("{domain} failed: {{}}".format(str(e)))
            return routes.make_response(data={{"error": str(e)}}, status=500)

    logger.info("{title} routes registered successfully")
'''

TOOL_TEMPLATE = u'''# -*- coding: utf-8 -*-
"""{title} tools."""

from mcp.server.fastmcp import Context
from .utils import format_response


def register_{domain}_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register {domain} tools with the MCP server."""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def {tool}(
        example: str = None,
        ctx: Context = None,
    ) -> str:
        """TODO одна строка: что делает и когда это вызывать.

        Этот докстринг — контракт для модели. Это единственное, что она видит
        перед вызовом, поэтому пишется для модели, а не для разработчика.

        Scope rules:
          - TODO что происходит, если example не передан.
          - TODO чего инструмент НЕ покрывает.

        TODO форма возврата, обязательно с единицами. Всё наружу — миллиметры.

        Limitations: TODO прямым текстом. Модель не догадается сама и примет
        пустой результат за доказательство отсутствия.

        Args:
            example: TODO что это, с конкретным примером значения,
                например "OST_Walls"
            ctx: MCP context for logging
        """
{call_block}
        return format_response(response)
'''

NOTES_TEMPLATE = u"""# {domain}

## Что делает

TODO одним абзацем.

## Как проверено

- [ ] `python revitmcp_kit.py check` — без замечаний
- [ ] `python revitmcp_kit.py probe` — прогон на живой модели
- Модель, на которой проверяли: TODO
- Версия Revit: TODO

## Что осталось нерешённым

TODO честно: что не проверено, где сомнения. Это читает сопровождающий.
"""


def cmd_new(args):
    for label, value in (("domain", args.domain), ("tool", args.tool)):
        if not _valid_ident(value):
            _die("{} — {}, получено {!r}".format(label, IDENT_HINT, value))

    package_dir = os.path.join(os.getcwd(), args.domain + "-tool")
    if os.path.exists(package_dir):
        _die("{} уже существует".format(package_dir))

    title = args.domain.replace("_", " ").capitalize()
    if args.get:
        handler_signature = "\n    def {}_handler(doc, example=None):".format(args.domain)
        payload_block = (
            "\n            # Параметры запроса приходят именованными аргументами.\n"
            "            example = example if example else None\n"
        )
        call_block = (
            "        params = {}\n"
            "        if example:\n"
            "            params[\"example\"] = example\n\n"
            "        response = await revit_get(\"/%s/\", ctx, params=params)"
            % args.domain
        )
        method = "GET"
        suppress_import = ""
    else:
        handler_signature = "\n    def {}_handler(doc, request):".format(args.domain)
        payload_block = (
            "\n            data = {}\n"
            "            if request and request.data:\n"
            "                data = parse_request_data(request.data)\n"
            "            example = data.get(\"example\")\n"
        )
        call_block = (
            "        data = {\"example\": example}\n"
            "        response = await revit_post(\"/%s/\", data, ctx)" % args.domain
        )
        method = "POST"
        suppress_import = ", make_element_id, parse_request_data, suppress_warnings"

    os.makedirs(os.path.join(package_dir, "revit_mcp"))
    os.makedirs(os.path.join(package_dir, "tools"))

    files = {
        os.path.join("revit_mcp", args.domain + ".py"): ROUTE_TEMPLATE.format(
            title=title, domain=args.domain, method=method,
            handler_signature=handler_signature, payload_block=payload_block,
            suppress_import=suppress_import,
            mm_constant="" if args.no_mm else "\nMM_TO_FEET = 1.0 / 304.8\n",
        ),
        os.path.join("tools", args.domain + "_tools.py"): TOOL_TEMPLATE.format(
            title=title, domain=args.domain, tool=args.tool, call_block=call_block
        ),
        "NOTES.md": NOTES_TEMPLATE.format(domain=args.domain),
        "manifest.json": json.dumps({
            "schema": 1,
            "domain": args.domain,
            "tools": [args.tool],
            "author": args.author or "TODO укажите себя",
            "kind": "read" if args.get else "write",
            "description": "TODO одна строка о назначении",
        }, ensure_ascii=False, indent=2) + "\n",
    }
    for rel, body in files.items():
        with io.open(os.path.join(package_dir, rel), "w",
                     encoding="utf-8", newline="\n") as handle:
            handle.write(body)

    print("Создан пакет: {}".format(package_dir))
    for rel in sorted(files):
        print("  " + rel.replace("\\", "/"))
    print("")
    print("Дальше:")
    print("  1. Заполните TODO. Ваше решение — только алгоритм и докстринг.")
    print("  2. Укажите себя в manifest.json (author).")
    print("  3. python revitmcp_kit.py check")
    print("  4. python revitmcp_kit.py probe   (нужен открытый Revit с моделью)")
    print("  5. python revitmcp_kit.py pack")


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------

def cmd_check(args):
    package_dir = _find_package()
    manifest = _load_manifest(package_dir)
    domain, route_path, tool_path = _sources(package_dir, manifest)

    problems = []
    if not manifest.get("author") or "TODO" in str(manifest.get("author")):
        problems.append("manifest.json: не указан автор")
    if "TODO" in str(manifest.get("description", "")):
        problems.append("manifest.json: не заполнено description")
    for tool in manifest.get("tools", []):
        if not _valid_ident(tool):
            problems.append("имя инструмента {!r} — {}".format(tool, IDENT_HINT))

    violations = conventions.check_package(domain, _read(route_path), _read(tool_path))

    tool_source = _read(tool_path)
    if "TODO" in tool_source:
        problems.append(
            "tools/{}_tools.py: остались TODO в докстринге. Докстринг — контракт "
            "для модели, с TODO инструмент непригоден.".format(domain)
        )

    all_problems = violations + problems
    if not all_problems:
        print("Замечаний нет.")
        print("")
        print("Это значит: конвенции соблюдены. Это НЕ значит, что инструмент")
        print("работает — проверьте на живой модели: revitmcp_kit.py probe")
        return 0

    print("Замечания ({}):".format(len(all_problems)))
    for item in all_problems:
        print("  - {}".format(item))
    print("")
    print("Сдавать пакет с замечаниями бессмысленно: приёмка проверяет тем же")
    print("кодом и откажет.")
    return 1


# ---------------------------------------------------------------------------
# probe
# ---------------------------------------------------------------------------

PROBE_SOURCE = u'''# -*- coding: utf-8 -*-
import json as _json
import binascii as _binascii

_src = _binascii.unhexlify("{hex}").decode("utf-8")


class _FakeRequest(object):
    def __init__(self, data):
        self.data = data


class _FakeAPI(object):
    def __init__(self):
        self.handlers = []

    def route(self, path, methods=None):
        def _decorator(fn):
            self.handlers.append((path, methods, fn))
            return fn
        return _decorator


# Ваш маршрут импортирует хелперы относительно (from .utils import ...), а
# относительный импорт работает только внутри настоящего пакета -- поэтому
# сначала грузим сам revit_mcp (extension root уже на sys.path благодаря
# pyRevit) и исполняем код с __package__, указывающим на него.
import revit_mcp as _revit_mcp_pkg
_ns = {{"__package__": "revit_mcp", "__name__": "revit_mcp._contrib_probe"}}
exec(_src, _ns)

_api = _FakeAPI()
_registrar = None
for _name, _value in _ns.items():
    if _name.startswith("register_") and _name.endswith("_routes"):
        _registrar = _value
        break

if _registrar is None:
    print("PROBE_FAIL: в модуле нет функции register_*_routes")
else:
    _registrar(_api)
    if not _api.handlers:
        print("PROBE_FAIL: регистратор не объявил ни одного @api.route")
    else:
        _path, _methods, _handler = _api.handlers[0]
        print("PROBE_ROUTE: {{}} {{}}".format(_methods, _path))
        _payload = {payload!r}
        if _methods and "GET" in _methods:
            _result = _handler(doc)
        else:
            _result = _handler(doc, _FakeRequest(_payload))
        _data = getattr(_result, "data", _result)
        try:
            print("PROBE_OK: " + _json.dumps(_data, ensure_ascii=False)[:4000])
        except Exception:
            print("PROBE_OK: " + str(_data)[:4000])
'''


def cmd_probe(args):
    import urllib.request
    import urllib.error

    package_dir = _find_package()
    manifest = _load_manifest(package_dir)
    domain, route_path, _tool_path = _sources(package_dir, manifest)

    source = _read(route_path).replace("\r\n", "\n")
    # Отправляем исходник в hex: в параметре code кириллица искажается на
    # входящем канале, а hex — чистый ASCII. Плюс не нужно ничего экранировать.
    encoded = source.encode("utf-8").hex()

    probe = PROBE_SOURCE.format(hex=encoded, payload=args.payload or "")

    body = json.dumps(
        {"code": probe, "description": "probe {}".format(domain)}
    ).encode("utf-8")
    request = urllib.request.Request(
        BRIDGE + "/execute_code/",
        data=body,
        # Тело — JSON, но объявлено как text/plain намеренно: тело с
        # Content-Type: application/json pyRevit разбирает сам, и под
        # IronPython 3 этот разбор падает ещё до вызова маршрута
        # («the JSON object must be str, not 'bytes'»).
        headers={"Content-Type": "text/plain; charset=utf-8"},
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        _die(
            "мост не отвечает на {} ({}).\n"
            "        Проверьте: Revit открыт, модель открыта, pyRevit Routes\n"
            "        включён. В браузере: {}/status/".format(BRIDGE, exc, BRIDGE)
        )

    output = payload.get("output") or ""
    if payload.get("status") == "error" or payload.get("error"):
        print("Маршрут упал внутри Revit:")
        print("  {}".format(payload.get("error", "неизвестная ошибка")))
        if payload.get("traceback"):
            print("")
            print(payload["traceback"])
        return 1

    print(output.strip() or "(маршрут ничего не напечатал)")
    print("")
    if "PROBE_OK" in output:
        print("Обработчик отработал на живой модели.")
        print("Отметьте это в NOTES.md — сопровождающий на это смотрит.")
        return 0
    print("Прогон не дошёл до результата — смотрите вывод выше.")
    return 1


# ---------------------------------------------------------------------------
# pack
# ---------------------------------------------------------------------------

def cmd_pack(args):
    package_dir = _find_package()
    manifest = _load_manifest(package_dir)
    domain, route_path, tool_path = _sources(package_dir, manifest)

    if cmd_check(args) != 0:
        print("")
        _die("пакет не собран: сначала устраните замечания")

    members = {
        "manifest.json": os.path.join(package_dir, "manifest.json"),
        "revit_mcp/{}.py".format(domain): route_path,
        "tools/{}_tools.py".format(domain): tool_path,
    }
    notes = os.path.join(package_dir, "NOTES.md")
    if os.path.isfile(notes):
        members["NOTES.md"] = notes
    own_test = os.path.join(package_dir, "tests", "test_{}.py".format(domain))
    if os.path.isfile(own_test):
        members["tests/test_{}.py".format(domain)] = own_test

    # skills и дополнительные инструкции: папка необязательная, берём целиком
    skills_dir = os.path.join(package_dir, "skills")
    if os.path.isdir(skills_dir):
        for current, _dirs, files in os.walk(skills_dir):
            for name in files:
                path = os.path.join(current, name)
                rel = os.path.relpath(path, package_dir).replace(os.sep, "/")
                members[rel] = path

    out = os.path.join(os.getcwd(), "{}.zip".format(domain))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for arcname, path in sorted(members.items()):
            archive.write(path, arcname)

    print("")
    print("Собрано: {}".format(out))
    print("")
    print("Положите файл в свою папку приёма на Google Drive")
    print("и отправьте ссылку на эту папку в Google-чате BIM-менеджеру:")
    print("  e.ermolenko@genpro.ru")
    print("")
    print("Ссылку достаточно отправить один раз — дальше складывайте")
    print("следующие пакеты в ту же папку. Подробности: INSTRUCTION.md, шаг 5.2.")
    print("")
    print("Дальше пакет проверяет и добавляет в репозиторий сопровождающий.")
    return 0


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Набор разработчика инструментов Revit MCP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    p_new = sub.add_parser("new", help="создать каркас пакета")
    p_new.add_argument("domain", help="имя домена, например audit")
    p_new.add_argument("tool", help="имя инструмента, например run_model_audit")
    p_new.add_argument("--get", action="store_true",
                       help="читающий инструмент (GET, без транзакции)")
    p_new.add_argument("--no-mm", action="store_true",
                       help="без константы MM_TO_FEET (геометрии нет)")
    p_new.add_argument("--author", help="ваше имя для manifest.json")
    p_new.set_defaults(func=cmd_new)

    p_check = sub.add_parser("check", help="проверить конвенции")
    p_check.set_defaults(func=cmd_check)

    p_probe = sub.add_parser("probe", help="прогнать маршрут на своём Revit")
    p_probe.add_argument("--payload", help="тело запроса JSON для POST-маршрута")
    p_probe.set_defaults(func=cmd_probe)

    p_pack = sub.add_parser("pack", help="собрать пакет для сдачи")
    p_pack.set_defaults(func=cmd_pack)

    args = parser.parse_args()
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
