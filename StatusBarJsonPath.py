import re

import sublime
import sublime_plugin


class CopyJsonPathCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    json_paths = get_json_paths(self.view)
    print(json_paths)
    if len(json_paths):
      sublime.set_clipboard( ", ".join(json_paths))


class StatusBarJsonPath(sublime_plugin.EventListener):
  KEY_JSON_PATH = "JSONPath"

  def update_json_path(self, view):
    json_paths = list(get_json_paths(view))
    if len(json_paths):
      view.set_status(self.KEY_JSON_PATH, "JSONPath: " + ", ".join(json_paths))
    else:
      view.erase_status(self.KEY_JSON_PATH)

  on_selection_modified_async = update_json_path


def is_line_delimited_json(view, pos):
  # TODO: get clever and check containing markdown code block region using pos param?
  filename = view.file_name()
  return filename and filename.endswith('.ndjson')


def get_json_paths(view):
  change_count_at_beginning = view.change_count()

  for region in view.sel():
    if view.change_count() != change_count_at_beginning:
      # Buffer was changed, we abort our mission.
      break

    pos = region.b
    if not view.match_selector(pos, 'source.json'):
      break

    # expand region to cover preceding json text
    containing_json_region = view.line(pos) if is_line_delimited_json(view, pos) else get_containing_region(view, 'source.json', pos)
    # so we don't cut off in the middle of a json key, we need to find the end of the string we are in
    if view.match_selector(pos, 'meta.mapping.key string'):
      MAX_SEARCH_LEN = 128
      cutoff = containing_json_region.b - pos
      tokens = tokens_with_text(view, sublime.Region(pos, pos + min(cutoff, MAX_SEARCH_LEN)))
      for token_region, scope, token_text in tokens:
        if token_text == '"' and sublime.score_selector(scope, 'punctuation.definition.string.end') > 0:
          pos = token_region.a
          break

    preceding_json_region = sublime.Region(containing_json_region.a, pos)

    jsonpath = json_path_for(view, preceding_json_region)
    if jsonpath:
      yield jsonpath


def get_containing_region(view, scope_selector, pos):
  for region in view.find_by_selector(scope_selector):
    if region.begin() <= pos and region.end() >= pos:
      return region
    if pos > region.end():
      break
  return None


def json_path_for(view, region):
  stack = []
  expect_key = False

  tokens = iter(tokens_with_text(view, region))

  for token_region, scope, token_text in tokens:
    if token_text == '"':
      s = read_string(tokens)
      if len(stack):
        frame = stack[-1]
        if frame['col_type'] == 'object' and expect_key:
          frame['key'] = s
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

  return path_to_string(stack)


def tokens_with_text(view, region):
  text = view.substr(region)
  offset = region.begin()
  for token_region, scope in view.extract_tokens_with_scopes(region):
    token_text = text[token_region.a - offset : token_region.b - offset]
    yield (token_region, scope, token_text)

NON_QUOTED_KEY_REGEX = r"^[a-zA-Z0-9_][a-zA-Z0-9_]*$"

def path_to_string(path_stack):
  s = '';
  for frame in path_stack:
    if frame['col_type'] == 'object':
      if 'key' in frame:
        if re.match(NON_QUOTED_KEY_REGEX, frame['key']):
          if s:
            s += '.'
          s += frame['key']
        else:
          key = frame['key'].replace('"', '\\"')
          s += '["' + frame['key'] + '"]'
    else:
      s += '[' + str(frame['index']) + ']'
  return s


def read_string(tokens):
  value = ''
  for token_region, scope, token_text in tokens:
    if token_text == '"':
      return value
    value += token_text
  # end of string not reached, just return what we have
  return value
