import sublime
import sublime_plugin

from typing import Generator, Iterable, Sequence, Tuple

class CopyJsonPathCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    json_paths = list(get_json_paths(self.view))
    if len(json_paths):
      sublime.set_clipboard(", ".join(json_paths))
      self.view.window().status_message('Copied json path to clipboard.')
    else:
      self.view.window().status_message('No json path to copy to the clipboard.')


class StatusBarJsonPath(sublime_plugin.EventListener):
  KEY_JSON_PATH = "JSONPath"

  def update_json_path(self, view: sublime.View):
    json_paths = list(get_json_paths(view))
    if len(json_paths):
      view.set_status(self.KEY_JSON_PATH, "JSONPath: " + ", ".join(json_paths))
    else:
      view.erase_status(self.KEY_JSON_PATH)

  on_selection_modified_async = update_json_path


def is_line_delimited_json(view: sublime.View, json_region: sublime.Region, pos: int):
  filename = view.file_name()
  if filename and filename.endswith('.ndjson'):
    return True

  # # pretend we are in line delimited json at EOF to save time
  # # NOTE: potentially not necessary because the JSON region ends at this point anyway
  # if pos == view.size():
  #   return True

  line_region = view.line(pos)
  if line_region.a < json_region.a:
    return False

  if view.substr(line_region.a) not in ('[', '{'):
    return False

  prev_line_region = view.line(line_region.a - 1)
  if prev_line_region.a < json_region.a:
    return False

  if view.substr(prev_line_region.b - 1) not in (']', '}'):
    return False

  return True


def get_json_paths(view: sublime.View) -> Generator[str, None, None]:
  change_count_at_beginning = view.change_count()

  for region in view.sel():
    if view.change_count() != change_count_at_beginning:
      # Buffer was changed, we abort our mission.
      break

    pos = region.b
    containing_json_region = view.expand_to_scope(pos, 'source.json')
    if containing_json_region is None:
        continue

    if is_line_delimited_json(view, containing_json_region, pos):
      containing_json_region = view.line(pos)
    # TODO: optimize to batch selection regions contained inside the same json region

    # so we don't cut off in the middle of a json key, we need to find the end of the string we are in
    string_region = view.expand_to_scope(pos, 'meta.mapping.key string')
    if string_region is not None:
      pos = string_region.b

    preceding_json_region = sublime.Region(containing_json_region.a, pos)

    jsonpath = json_path_for(view, preceding_json_region)
    if jsonpath:
      yield jsonpath


def build_json_path_stack_frame_for(view: sublime.View, region: sublime.Region) -> Sequence[dict]:
  stack = []
  expect_key = False

  # TODO: track token positions so we can implement "Go to parent" (and "go to previous sibling" but that's more complicated with a stack.)
  #    (unless we just add a 'prev_sibling' key and keep it up to date...)
  # TODO: if we make it possible to get more tokens for the following region, we can implement "go to next sibling"
  #    potentially we would evaluate it lazily, one line at a time
  #    would need the containing json region so we don't go out of bounds
  tokens = iter(tokens_with_text(view, region))

  for token_region, scope, token_text in tokens:
    if token_text == '"':
      string_content, token_count = read_string(tokens)
      if len(stack):
        frame = stack[-1]
        if frame['col_type'] == 'object' and expect_key:
          frame['key'] = string_content
          frame['key_complexity'] = token_count
          expect_key = False
    elif token_text == '{':
      stack.append(dict(col_type='object'))
      expect_key = True
    elif token_text == '[':
      stack.append(dict(col_type='array',index=0))
    elif token_text == '}' or token_text == ']':
      stack.pop()
    elif token_text == ',':
      if len(stack):
        frame = stack[-1]
        if frame['col_type'] == 'object':
          expect_key = True
          frame.pop('key', None)
        elif frame['col_type'] == 'array':
          frame['index'] += 1

  return stack


def json_path_for(view: sublime.View, region: sublime.Region) -> str:
  stack = build_json_path_stack_frame_for(view, region)

  return path_to_string(stack)


def tokens_with_text(view: sublime.View, region: sublime.Region) -> Generator[Tuple[sublime.Region, str, str], None, None]:
  text = view.substr(region)
  offset = region.begin()
  for token_region, scope in view.extract_tokens_with_scopes(region):
    token_text = text[token_region.a - offset : token_region.b - offset]
    yield (token_region, scope, token_text)


def path_to_string(path_stack: Sequence[dict]) -> str:
  constructed_path = '';
  for frame in path_stack:
    if frame['col_type'] == 'object':
      if 'key' in frame:
        if frame['key_complexity'] == 1:
          if constructed_path:
            constructed_path += '.'
          constructed_path += frame['key']
        else:
          key = frame['key'].replace('"', '\\"')
          constructed_path += '["' + frame['key'] + '"]'
    else:
      constructed_path += '[' + str(frame['index']) + ']'
  return '.' + constructed_path


def read_string(tokens: Iterable[Tuple[sublime.Region, str, str]]) -> Tuple[str, int]:
  value = ''
  token_count = 0
  for token_region, scope, token_text in tokens:
    if token_text == '"':
      return (value, token_count)
    token_count += 1
    value += token_text
  # end of string not reached, just return what we have
  return (value, token_count)
