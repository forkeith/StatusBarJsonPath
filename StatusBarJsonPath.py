import re

import sublime
import sublime_plugin

class CopyJsonPathCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		json_paths = list(get_json_paths(self.view))
		print(json_paths)
		if len(json_paths):
			sublime.set_clipboard( ", ".join(json_paths))
			self.view.window().status_message('Copied json path to clipboard.')
		else:
			self.view.window().status_message('No json path to copy to the clipboard.')

	def is_visible(self):
		return any(self.view.match_selector(region.a, 'source.json') for region in self.view.sel())


class StatusBarJsonPath(sublime_plugin.EventListener):
	KEY_SIZE = "JSONPath"

	def update_json_path(self, view):
		json_paths = list(get_json_paths(view))
		if len(json_paths):
			view.set_status(self.KEY_SIZE, "JSONPath: " + ", ".join(json_paths))
		else:
			view.erase_status(self.KEY_SIZE)

	on_selection_modified_async = update_json_path


def get_json_paths(view: sublime.View):
	change_count_at_beginning = view.change_count()

	for region in view.sel():
		if view.change_count() != change_count_at_beginning:
			# Buffer was changed, we abort our mission.
			break

		pos = region.b
		containing_json_region = view.expand_to_scope(pos, 'source.json')
		if containing_json_region is None:
			continue

		# so we don't cut off in the middle of a json key, we need to find the end of the string we are in
		if view.match_selector(pos, 'meta.mapping.key string'):
			string_region = view.expand_to_scope(pos, 'meta.mapping.key string')
			if string_region is not None:
				pos = string_region.b

		preceding_json_region = sublime.Region(containing_json_region.a, pos)

		jsonpath = json_path_for(view, preceding_json_region)
		if jsonpath:
			yield jsonpath


def build_json_path_stack_frame_for(view: sublime.View, region: sublime.Region):
	stack = []
	expect_key = False

	tokens = iter(tokens_with_text(view, region))

	for token_region, scope, token_text in tokens:
		if token_text == '"':
			string_content, token_count, token_region = read_string_from_token_iterator(tokens)
			if len(stack):
				frame = stack[-1]
				if frame['col_type'] == 'object':
					if expect_key:
						frame['key'] = string_content
						frame['key_complexity'] = token_count
						expect_key = False
					elif token_region and token_region.b < region.b:
						frame.pop('key', None)
		elif token_text == '{':
			stack.append(dict(col_type='object'))
			expect_key = True
		elif token_text == '[':
			stack.append(dict(col_type='array',index=0))
		elif token_text == '}' or token_text == ']':
			stack.pop()
			if len(stack):
				frame = stack[-1]
				if frame['col_type'] == 'object':
					frame.pop('key', None)
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


def tokens_with_text(view: sublime.View, region: sublime.Region):
	text = view.substr(region)
	offset = region.begin()
	for token_region, scope in view.extract_tokens_with_scopes(region):
		token_text = text[token_region.a - offset : token_region.b - offset]
		yield (token_region, scope, token_text)


def path_to_string(path_stack) -> str:
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


def read_string_from_token_iterator(tokens):
	value = ''
	token_count = 0
	prev_token_region = None
	for token_region, scope, token_text in tokens:
		if token_text == '"':
			return (value, token_count, token_region)
		token_count += 1
		value += token_text
		prev_token_region = token_region
	# end of string not reached, just return what we have
	return (value, token_count, prev_token_region)
