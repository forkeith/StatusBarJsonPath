import re
import sublime
import sublime_plugin


JSON_KEY_UNQUOTED_REGEX = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_]*$")


class CopyJsonPathCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        json_paths = get_json_path(self.view)
        if len(json_paths):
            sublime.set_clipboard( ", ".join(json_paths))


class StatusBarJsonPath(sublime_plugin.EventListener):
    STATUS_BAR_KEY = "JSONPath"

    def update_json_path(self, view: sublime.View) -> None:
        json_paths = get_json_path(view)
        if len(json_paths):
            # if any(path is None for path in json_paths):
            #     sublime.error_message((view.file_name() or view.name()) + ' has none json path')
            view.set_status(self.STATUS_BAR_KEY, "JSONPath: " + ", ".join(json_paths))
        else:
            view.erase_status(self.STATUS_BAR_KEY)

    on_selection_modified_async = update_json_path


def get_json_path(view: sublime.View) -> list:
    json_paths = []
    tag = view.change_count()

    for region in view.sel():
        if view.change_count() != tag:
            # Buffer was changed, we abort our mission.
            return json_paths
        start = region.begin()
        end = region.end()
        if start != end and view.scope_name(start) != view.scope_name(end): # selection is okay as long as all inside string etc. as opposed to across tokens
            break
        if 'source.json' not in view.scope_name(start):
            break

        for json_region in view.find_by_selector('source.json'):
            if json_region.begin() < start and json_region.end() > start:
                break

        if json_region is None:
            continue

        text = view.substr(json_region)
        jsonpath = json_path_to(text, end - json_region.begin())

        if jsonpath:
            json_paths.append(jsonpath)
    return json_paths


# ported from https://github.com/nidu/vscode-copy-json-path/blob/master/src/jsPathTo.ts
def json_path_to(text: str, offset: int) -> str:
    pos = 0
    stack = []
    is_in_key = False

    while pos < offset:
        start_pos = pos
        if text[pos] == '"':
            pos = pos + 1
            end_quote_pos = find_end_quote(text, pos)
            if len(stack):
                frame = stack[-1]
                if frame['col_type'] == 'object' and is_in_key:
                    frame['key'] = text[pos:end_quote_pos]
                    is_in_key = False
            pos = end_quote_pos + 1
        elif text[pos] == '{':
            stack.append(dict(col_type='object'))
            is_in_key = True
        elif text[pos] == '[':
            stack.append(dict(col_type='array', index=0))
        elif text[pos] == '}' or text[pos] == ']':
            stack.pop()
        elif text[pos] == ',':
            if len(stack):
                frame = stack[-1]
                if frame['col_type'] == 'object':
                    is_in_key = True
                elif frame['col_type'] == 'array':
                    frame['index'] += 1

        if pos == start_pos:
            pos += 1
    return path_to_string(stack)

def path_to_string(path: list) -> str:
    s = '';
    for frame in path:
        if frame['col_type'] == 'object':
            if 'key' in frame:
                if JSON_KEY_UNQUOTED_REGEX.match(frame['key']):
                    if s:
                        s += '.'
                    s += frame['key']
                else:
                    key = frame['key'].replace('"', '\\"')
                    s += '["' + frame['key'] + '"]'
        else:
            s += '[' + str(frame['index']) + ']'
    return s


# def read_string(text: str, pos: int):
#     p = pos + 1
#     i = find_end_quote(text, p)
#     return text[p:i], i + 1


def find_end_quote(text: str, i: int) -> int:
    """If there is no end quote due to the string still being typed etc., return len(text)"""
    while i < len(text):
        if text[i] == '\n': # string is unterminated so according to JSON rules it ends at EOL as strings can't contain newline chars
            return i
        if text[i] == '"':
            bt = i
            # Handle backtracking to find if this quote is escaped (or, if the escape is escaping a slash)
            while 0 <= bt and text[bt] == '\\':
                bt -= 1
            if (i - bt) % 2 == 0:
                break
        i += 1

    return i


# TODO: write tests
