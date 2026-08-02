class_name UIFactory
extends RefCounted


static func line_edit(placeholder: String, value: String = "") -> LineEdit:
	var edit := LineEdit.new()
	edit.placeholder_text = placeholder
	edit.text = value
	edit.custom_minimum_size = Vector2(0, 38)
	return edit


static func button(caption: String) -> Button:
	var result := Button.new()
	result.text = caption
	result.custom_minimum_size = Vector2(0, 38)
	return result


static func heading(caption: String, size: int) -> Label:
	var label := Label.new()
	label.text = caption
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", Color("d7c49a"))
	return label


static func panel_style(color: Color) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = color
	style.corner_radius_top_left = 5
	style.corner_radius_top_right = 5
	style.corner_radius_bottom_left = 5
	style.corner_radius_bottom_right = 5
	style.border_width_left = 1
	style.border_width_top = 1
	style.border_width_right = 1
	style.border_width_bottom = 1
	style.border_color = color.lightened(0.12)
	return style


static func texture(path: String) -> Texture2D:
	if path.is_empty() or not ResourceLoader.exists(path):
		return null
	return load(path) as Texture2D
