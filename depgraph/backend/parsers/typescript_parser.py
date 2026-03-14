import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from backend.core.models import CodeNode

try:
    import tree_sitter_typescript as tsts
    from tree_sitter import Language, Parser
    TS_LANGUAGE = Language(tsts.language_typescript())
    TSX_LANGUAGE = Language(tsts.language_tsx())
    _TS_AVAILABLE = True
except Exception:
    _TS_AVAILABLE = False


def walk_ast(node):
    yield node
    for child in node.children:
        yield from walk_ast(child)


def get_child_text(node, field_name: str, source: bytes) -> str:
    child = node.child_by_field_name(field_name)
    return source[child.start_byte:child.end_byte].decode('utf-8', errors='replace') if child else ""


def parse_typescript_file(filepath: str) -> CodeNode:
    """Parse a TypeScript/TSX/JS/JSX file and return a CodeNode tree."""
    try:
        with open(filepath, 'rb') as f:
            source = f.read()
    except Exception:
        return None

    is_react = filepath.endswith(('.tsx', '.jsx'))
    language_label = "react" if is_react else "typescript"

    file_node = CodeNode(
        id=filepath,
        type="file",
        language=language_label,
        name=os.path.basename(filepath),
        source_lines=source.decode('utf-8', errors='replace'),
        file=filepath,
        line_start=1,
        line_end=source.count(b'\n') + 1
    )

    if not _TS_AVAILABLE:
        _extract_ts_regex(file_node, source.decode('utf-8', errors='replace'), filepath, is_react)
        return file_node

    lang = TSX_LANGUAGE if is_react else TS_LANGUAGE
    parser = Parser(lang)
    tree = parser.parse(source)

    for node in walk_ast(tree.root_node):
        # Capture interface declarations: interface UserResponse { ... }
        if node.type == "interface_declaration":
            iface_name = get_child_text(node, "name", source)
            iface_node = CodeNode(
                id=f"{filepath}::{iface_name}",
                type="class",
                language="typescript",
                name=iface_name,
                source_lines=source[node.start_byte:node.end_byte].decode('utf-8', errors='replace'),
                file=filepath,
                line_start=node.start_point[0],
                line_end=node.end_point[0],
                parent_id=filepath,
                metadata={"node_kind": "interface"}
            )
            for prop in walk_ast(node):
                if prop.type == "property_signature":
                    prop_name = get_child_text(prop, "name", source)
                    prop_type_node = prop.child_by_field_name("type")
                    prop_type = source[prop_type_node.start_byte:prop_type_node.end_byte].decode(
                        'utf-8', errors='replace') if prop_type_node else ""
                    if prop_name:
                        prop_node = CodeNode(
                            id=f"{filepath}::{iface_name}::{prop_name}",
                            type="variable",
                            language="typescript",
                            name=prop_name,
                            source_lines=source[prop.start_byte:prop.end_byte].decode('utf-8', errors='replace'),
                            file=filepath,
                            line_start=prop.start_point[0],
                            line_end=prop.end_point[0],
                            parent_id=iface_node.id,
                            metadata={"ts_type": prop_type}
                        )
                        iface_node.children.append(prop_node)
            file_node.children.append(iface_node)

        # Capture JSX / React member_expression: user.userEmail, props.value
        if is_react and node.type == "member_expression":
            obj = get_child_text(node, "object", source)
            prop = get_child_text(node, "property", source)
            if obj and prop and not obj.startswith(('React', 'console', 'Object', 'Array', 'Math')):
                access_id = f"{filepath}::jsx::{obj}.{prop}::{node.start_point[0]}"
                access_node = CodeNode(
                    id=access_id,
                    type="variable",
                    language="react",
                    name=f"{obj}.{prop}",
                    source_lines=source[node.start_byte:node.end_byte].decode('utf-8', errors='replace'),
                    file=filepath,
                    line_start=node.start_point[0],
                    line_end=node.end_point[0],
                    parent_id=filepath,
                    metadata={"access_object": obj, "access_property": prop}
                )
                file_node.children.append(access_node)

        # Capture JS/TS classes
        if node.type == "class_declaration":
            class_name = get_child_text(node, "name", source)
            if class_name:
                class_node = CodeNode(
                    id=f"{filepath}::{class_name}",
                    type="class",
                    language="javascript" if not is_react and filepath.endswith('.js') else language_label,
                    name=class_name,
                    source_lines=source[node.start_byte:node.end_byte].decode('utf-8', errors='replace'),
                    file=filepath,
                    line_start=node.start_point[0],
                    line_end=node.end_point[0],
                    parent_id=filepath,
                    metadata={"node_kind": "class"}
                )
                file_node.children.append(class_node)

        # Capture JS/TS functions
        if node.type == "function_declaration":
            func_name = get_child_text(node, "name", source)
            if func_name:
                func_node = CodeNode(
                    id=f"{filepath}::{func_name}",
                    type="function",
                    language="javascript" if not is_react and filepath.endswith('.js') else language_label,
                    name=func_name,
                    source_lines=source[node.start_byte:node.end_byte].decode('utf-8', errors='replace'),
                    file=filepath,
                    line_start=node.start_point[0],
                    line_end=node.end_point[0],
                    parent_id=filepath,
                    metadata={"node_kind": "function"}
                )
                file_node.children.append(func_node)

        # Capture arrow functions assigned to variables
        if node.type == "variable_declarator":
            name_node = node.child_by_field_name("name")
            value_node = node.child_by_field_name("value")
            if name_node and value_node and value_node.type == "arrow_function":
                var_name = source[name_node.start_byte:name_node.end_byte].decode('utf-8', errors='replace')
                func_node = CodeNode(
                    id=f"{filepath}::{var_name}",
                    type="function",
                    language="javascript" if not is_react and filepath.endswith('.js') else language_label,
                    name=var_name,
                    source_lines=source[node.start_byte:node.end_byte].decode('utf-8', errors='replace'),
                    file=filepath,
                    line_start=node.start_point[0],
                    line_end=node.end_point[0],
                    parent_id=filepath,
                    metadata={"node_kind": "arrow_function"}
                )
                file_node.children.append(func_node)

    return file_node


def _extract_ts_regex(file_node: CodeNode, source: str, filepath: str, is_react: bool):
    """Fallback regex-based TypeScript extraction."""
    import re
    lines = source.split('\n')
    in_iface = None
    iface_node = None
    for i, line in enumerate(lines):
        iface_match = re.match(r'(?:export\s+)?interface\s+(\w+)', line)
        if iface_match:
            in_iface = iface_match.group(1)
            iface_node = CodeNode(
                id=f"{filepath}::{in_iface}",
                type="class",
                language="typescript",
                name=in_iface,
                source_lines=line,
                file=filepath,
                line_start=i,
                line_end=i,
                parent_id=filepath,
                metadata={"node_kind": "interface"}
            )
            file_node.children.append(iface_node)
        if in_iface and iface_node:
            prop_match = re.match(r'\s+(\w+)\s*[?:]', line)
            if prop_match and not line.strip().startswith('//'):
                prop_name = prop_match.group(1)
                if prop_name not in ('export', 'interface', 'type', 'const', 'let'):
                    prop_node = CodeNode(
                        id=f"{filepath}::{in_iface}::{prop_name}",
                        type="variable",
                        language="typescript",
                        name=prop_name,
                        source_lines=line.strip(),
                        file=filepath,
                        line_start=i,
                        line_end=i,
                        parent_id=iface_node.id
                    )
                    iface_node.children.append(prop_node)
        if '}' in line and in_iface:
            in_iface = None
            iface_node = None

        # JS/TS Class Fallback
        class_match = re.match(r'(?:export\s+)?(?:default\s+)?class\s+(\w+)', line)
        if class_match:
            class_name = class_match.group(1)
            class_node = CodeNode(
                id=f"{filepath}::{class_name}",
                type="class",
                language="javascript" if filepath.endswith('.js') else "typescript",
                name=class_name,
                source_lines=line.strip(),
                file=filepath,
                line_start=i,
                line_end=i,
                parent_id=filepath,
                metadata={"node_kind": "class"}
            )
            file_node.children.append(class_node)

        # JS/TS Function Fallback
        func_match = re.match(r'(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)', line)
        if func_match:
            func_name = func_match.group(1)
            func_node = CodeNode(
                id=f"{filepath}::{func_name}",
                type="function",
                language="javascript" if filepath.endswith('.js') else "typescript",
                name=func_name,
                source_lines=line.strip(),
                file=filepath,
                line_start=i,
                line_end=i,
                parent_id=filepath,
                metadata={"node_kind": "function"}
            )
            file_node.children.append(func_node)

        # Arrow Function Fallback
        arrow_match = re.match(r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|\w+)\s*=>', line)
        if arrow_match:
            var_name = arrow_match.group(1)
            func_node = CodeNode(
                id=f"{filepath}::{var_name}",
                type="function",
                language="javascript" if filepath.endswith('.js') else "typescript",
                name=var_name,
                source_lines=line.strip(),
                file=filepath,
                line_start=i,
                line_end=i,
                parent_id=filepath,
                metadata={"node_kind": "arrow_function"}
            )
            file_node.children.append(func_node)

    if is_react:
        for i, line in enumerate(lines):
            for match in re.finditer(r'\b(\w+)\.(\w+)\b', line):
                obj, prop = match.group(1), match.group(2)
                if obj not in ('React', 'console', 'Object', 'Array', 'import') and len(prop) > 2:
                    access_node = CodeNode(
                        id=f"{filepath}::jsx::{obj}.{prop}::{i}",
                        type="variable",
                        language="react",
                        name=f"{obj}.{prop}",
                        source_lines=line.strip(),
                        file=filepath,
                        line_start=i,
                        line_end=i,
                        parent_id=filepath,
                        metadata={"access_object": obj, "access_property": prop}
                    )
                    file_node.children.append(access_node)
