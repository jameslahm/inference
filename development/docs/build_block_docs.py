from typing import List, Tuple

from inference.enterprise.workflows.entities.steps import OutputDefinition
from inference.enterprise.workflows.execution_engine.compiler.blocks_loader import (
    describe_available_blocks,
)

import re
import os


BLOCK_DOCUMENTATION_FILE = os.path.join(os.getcwd(), 'docs', 'workflows', 'blocks.md')
BLOCK_DOCUMENTATION_DIRECTORY = os.path.join(os.getcwd(), 'docs', 'workflows', 'blocks')
AUTOGENERATED_BLOCKS_LIST_TOKEN = "<!--- AUTOGENERATED_BLOCKS_LIST -->"

USER_CONFIGURATION_HEADER = [
    "| **Name** | **Type** | **Description** | **Parameterizable** |",
    "|:---------|:---------|:----------------|:--------------------|"
]

BLOCK_OUTPUTS_HEADER = [
    "| **Name** | **Kind** | **Description** |",
    "|:---------|:---------|:----------------|"
]

BLOCK_DOCUMENTATION_TEMPLATE = """
# {class_name}

{description}

## User Configuration

{block_inputs}

## Input Bindings

| **Name** | **Kind** | **Description** |
|:---------|:---------|:----------------|

## Output Bindings

{block_outputs}
"""

BLOCK_CARD_TEMPLATE = '<p class="card block-card" data-url="{data_url}" data-name="{data_name}" data-desc="{data_desc}" data-labels="{data_labels}" data-author="{data_authors}"></p>'


def read_lines_from_file(path: str) -> List[str]:
    with open(path) as file:
        return [line.rstrip() for line in file]


def save_lines_to_file(path: str, lines: List[str]) -> None:
    with open(path, "w") as f:
        for line in lines:
            f.write("%s\n" % line)


def search_lines_with_token(lines: List[str], token: str) -> List[int]:
    result = []
    for line_index, line in enumerate(lines):
        if token in line:
            result.append(line_index)
    return result


def camel_to_snake(name: str) -> str:
    name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    name = re.sub('([a-z0-9])([A-Z])', r'\1_\2', name)
    return name.lower()


def block_class_name_to_block_title(name: str) -> str:
    words = re.findall(r'[A-Z](?:[a-z]+|[A-Z]*(?=[A-Z]|$))', name)

    if words[-1] == "Block":
        words.pop()

    return ' '.join(words)


TYPE_MAPPING = {
    "number": "float",
    "integer": "int",
    "boolean": "bool",
    "string": "str",
    "null": "None",
}


def format_inputs(block_definition: dict) -> List[Tuple[str, str, str, bool]]:
    global_result = []
    properties = block_definition['properties']
    for property_name, property_definition in properties.items():
        if property_name == 'type':
            continue
        if property_definition.get("type") in TYPE_MAPPING:
            result = TYPE_MAPPING[property_definition["type"]]
            global_result.append((property_name, result, property_definition.get("description", "not available"), False))
            continue
        if 'items' in property_definition:
            if "reference" in property_definition["items"]:
                continue
            t_name, ref_appears = create_array_typing(property_definition["items"])
            global_result.append((property_name, t_name, property_definition.get("description", "not available", ref_appears)))
            continue
        if 'anyOf' in property_definition or 'oneOf' in property_definition or 'allOf' in property_definition:
            x = property_definition.get('anyOf', []) + \
                property_definition.get('oneOf', []) + \
                property_definition.get('allOf', [])
            primitive_types = [e for e in x if "reference" not in e]
            if len(primitive_types) == 0:
                continue
            ref_appears = len(primitive_types) != len(x)
            result = []
            for t in primitive_types:
                if "$ref" in t:
                    t_name = t["$ref"].split("/")[-1]
                elif t["type"] in TYPE_MAPPING:
                    t_name = TYPE_MAPPING[t["type"]]
                elif t["type"] == "array":
                    t_name, ref_appears_nested = create_array_typing(t)
                    ref_appears = ref_appears or ref_appears_nested
                else:
                    t_name = "unknown"
                result.append(t_name)
            result = set(result)
            if "None" in result:
                high_level_type = "Optional"
                result.remove("None")
            else:
                high_level_type = "Union"
            result_str = ", ".join(list(result))
            if len(primitive_types) > 1:
                result_str = f"{high_level_type}[{result_str}]"
            global_result.append((property_name, result_str, property_definition.get("description", "not available"), ref_appears))
        if 'reference' in property_definition:
            continue
    return global_result


def create_array_typing(array_definition: dict) -> Tuple[str, bool]:
    ref_appears = False
    high_level_type = "Set" if array_definition.get("uniqueItems", False) is True else "List"
    if len(array_definition["items"]) == 0:
        return f"{high_level_type}[Any]", ref_appears
    if "type" in array_definition["items"]:
        if "reference" in array_definition["items"]:
            ref_appears = True
        if "$ref" in array_definition["items"]["type"]:
            t_name = array_definition["items"]["type"]["$ref"].split("/")[-1]
        elif array_definition["items"]["type"] in TYPE_MAPPING:
            t_name = TYPE_MAPPING[array_definition["items"]["type"]]
        elif array_definition["items"]["type"] == "array":
            t_name = create_array_typing(array_definition["items"]["type"])
        else:
            t_name = "unknown"
        return f"{high_level_type}[{t_name}]", ref_appears


def format_block_inputs(outputs_manifest: dict) -> str:
    data = format_inputs(outputs_manifest)
    rows = []
    for name, kind, description, ref_appear in data:
        rows.append(f"| `{name}` | `{kind}` | {description}. | {ref_appear} |")

    return '\n'.join(USER_CONFIGURATION_HEADER + rows)


def format_block_outputs(outputs_manifest: List[OutputDefinition]) -> str:
    rows = []

    for output in outputs_manifest:
        if len(output.kind) == 1:
            kind = output.kind[0].name
            description = output.kind[0].description
            rows.append(f"| `{output.name}` | `{kind}` | {description}. |")
        else:
            kind = ', '.join([k.name for k in output.kind])
            description = ' or '.join([f"{k.description} if `{k.name}`" for k in output.kind])
            rows.append(f"| `{output.name}` | `Union[{kind}]` | {description}. |")

    return '\n'.join(BLOCK_OUTPUTS_HEADER + rows)


def get_class_name(fully_qualified_name: str) -> str:
    return fully_qualified_name.split('.')[-1]


def create_directory_if_not_exists(directory_path: str) -> None:
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)


create_directory_if_not_exists(BLOCK_DOCUMENTATION_DIRECTORY)

lines = read_lines_from_file(path=BLOCK_DOCUMENTATION_FILE)
lines_with_token_indexes = search_lines_with_token(
        lines=lines, token=AUTOGENERATED_BLOCKS_LIST_TOKEN)

if len(lines_with_token_indexes) != 2:
    raise Exception(f"Please inject two {AUTOGENERATED_BLOCKS_LIST_TOKEN} "
                    f"tokens to signal start and end of autogenerated table.")

[start_index, end_index] = lines_with_token_indexes

block_card_lines = []

for block in describe_available_blocks().blocks:
    block_class_name = get_class_name(block.fully_qualified_class_name)
    block_type = block.block_manifest['block_type']

    short_description = block.block_manifest.get('short_description', '')
    long_description = block.block_manifest.get('long_description', '')

    documentation_file_name = camel_to_snake(block_class_name) + '.md'
    documentation_file_path = os.path.join(
        BLOCK_DOCUMENTATION_DIRECTORY,
        documentation_file_name
    )
    documentation_content = BLOCK_DOCUMENTATION_TEMPLATE.format(
        class_name=block_class_name,
        description=long_description,
        block_inputs=format_block_inputs(block.block_manifest),
        block_outputs=format_block_outputs(block.outputs_manifest)
    )
    with open(documentation_file_path, 'w') as documentation_file:
        documentation_file.write(documentation_content)

    block_card_line = BLOCK_CARD_TEMPLATE.format(
        data_url=camel_to_snake(block_class_name),
        data_name=block_class_name_to_block_title(block_class_name),
        data_desc=short_description,
        data_labels=block_type.upper(),
        data_authors=''
    )
    block_card_lines.append(block_card_line)

lines = lines[:start_index + 1] + block_card_lines + lines[end_index:]
save_lines_to_file(path=BLOCK_DOCUMENTATION_FILE, lines=lines)
