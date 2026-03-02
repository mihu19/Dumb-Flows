import os
import re
import graphviz
import textwrap

# Ensure Graphviz executables are on PATH
os.environ["PATH"] += os.pathsep + r"C:\Program Files\Graphviz\bin"


# ==========================================================
# Utility Functions
# ==========================================================

def find_matching(text, start, open_char, close_char):
    count = 1
    for i in range(start + 1, len(text)):
        if text[i] == open_char:
            count += 1
        elif text[i] == close_char:
            count -= 1
            if count == 0:
                return i
    return -1


def wrap_label(text, width=None):
    if width is None:
        width = LABEL_WRAP_WIDTH
        
    escaped_text = text.replace('\\', '\\\\')
    lines = escaped_text.split('\n')
    wrapped_lines = []
    for line in lines:
        wrapped_lines.extend(textwrap.wrap(line, width))
    
    return "\n".join(wrapped_lines)


def tf_label(text):
    """Formats True/False edge labels using config"""
    if TF_LABEL_BOLD:
        text = f"<B>{text}</B>"

    return f"""<
    <FONT POINT-SIZE="{TF_LABEL_SIZE}" FACE="{TF_LABEL_FONT}" COLOR="{TF_LABEL_COLOR}">
    {text}
    </FONT>
    >"""


# ==========================================================
# Extract C Functions
# ==========================================================

def extract_c_functions(filename):
    with open(filename, "r", encoding="utf-8") as f:
        code = f.read()

    code = re.sub(r'//.*', '', code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)

    pattern = re.compile(
        r'\b[a-zA-Z_][a-zA-Z0-9_\*\s]*\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)\s*\{'
    )

    c_keywords = {
        'if', 'else', 'while', 'for', 'do', 'switch', 'case',
        'return', 'break', 'continue', 'goto', 'sizeof', 'typedef',
        'struct', 'union', 'enum', 'default'
    }

    functions = []

    for match in pattern.finditer(code):
        name = match.group(1)
        if name in c_keywords:
            continue
        start = match.end() - 1
        end = find_matching(code, start, "{", "}")
        if end != -1:
            body = code[start + 1:end]
            functions.append({
                "name": name,
                "body": body,
                "file": filename
            })

    return functions


# ==========================================================
# Parser
# ==========================================================

def parse_block(code):
    nodes = []
    i = 0

    while i < len(code):

        while i < len(code) and code[i].isspace():
            i += 1
        if i >= len(code):
            break

        if code.startswith("if", i):
            cond_start = code.find("(", i)
            cond_end = find_matching(code, cond_start, "(", ")")
            condition = code[cond_start+1:cond_end].strip()

            body_start = cond_end + 1
            while body_start < len(code) and code[body_start].isspace():
                body_start += 1

            if body_start < len(code) and code[body_start] == "{":
                body_end = find_matching(code, body_start, "{", "}")
                true_body = code[body_start+1:body_end]
                i = body_end + 1
            else:
                semi = code.find(";", body_start)
                true_body = code[body_start:semi]
                i = semi + 1

            root_if = {
                "type": "if",
                "cond": condition,
                "body": parse_block(true_body),
                "else_body": []
            }
            
            current_if = root_if
            
            # Eagerly consume any attached else / else if blocks
            while True:
                lookahead = i
                while lookahead < len(code) and code[lookahead].isspace():
                    lookahead += 1
                
                if lookahead < len(code) and code.startswith("else", lookahead):
                    # Validate it's the actual word 'else'
                    if lookahead + 4 == len(code) or not (code[lookahead+4].isalnum() or code[lookahead+4] == '_'):
                        lookahead += 4
                        while lookahead < len(code) and code[lookahead].isspace():
                            lookahead += 1
                        
                        if lookahead < len(code) and code[lookahead] == "{":
                            else_end = find_matching(code, lookahead, "{", "}")
                            else_body = code[lookahead+1:else_end]
                            current_if["else_body"] = parse_block(else_body)
                            i = else_end + 1
                            break # End of chain
                        elif code.startswith("if", lookahead):
                            # It's an 'else if'
                            cond_start = code.find("(", lookahead)
                            cond_end = find_matching(code, cond_start, "(", ")")
                            condition2 = code[cond_start+1:cond_end].strip()
                            
                            body_start = cond_end + 1
                            while body_start < len(code) and code[body_start].isspace():
                                body_start += 1
                            
                            if body_start < len(code) and code[body_start] == "{":
                                body_end = find_matching(code, body_start, "{", "}")
                                true_body2 = code[body_start+1:body_end]
                                i = body_end + 1
                            else:
                                semi = code.find(";", body_start)
                                true_body2 = code[body_start:semi]
                                i = semi + 1
                            
                            nested_if = {
                                "type": "if",
                                "cond": condition2,
                                "body": parse_block(true_body2),
                                "else_body": []
                            }
                            # Nest the 'else if' inside the current 'if'
                            current_if["else_body"] = [nested_if]
                            current_if = nested_if
                            continue # Loop again to check if this 'else if' has an 'else'
                        else:
                            # Single line statement else
                            semi = code.find(";", lookahead)
                            else_body = code[lookahead:semi]
                            current_if["else_body"] = parse_block(else_body + ";")
                            i = semi + 1
                            break # End of chain
                    else:
                        break # Not a valid 'else' keyword
                else:
                    break # No 'else' found
            
            nodes.append(root_if)
            continue

        if code.startswith("while", i):
            cond_start = code.find("(", i)
            cond_end = find_matching(code, cond_start, "(", ")")
            condition = code[cond_start+1:cond_end].strip()

            body_start = cond_end + 1
            while body_start < len(code) and code[body_start].isspace():
                body_start += 1

            if body_start < len(code) and code[body_start] == "{":
                body_end = find_matching(code, body_start, "{", "}")
                body = code[body_start+1:body_end]
                i = body_end + 1
            else:
                semi = code.find(";", body_start)
                body = code[body_start:semi]
                i = semi + 1

            nodes.append({
                "type": "while",
                "cond": condition,
                "body": parse_block(body)
            })
            continue

        if code.startswith("for", i):
            cond_start = code.find("(", i)
            cond_end = find_matching(code, cond_start, "(", ")")
            header = code[cond_start+1:cond_end]
            parts = header.split(";")

            init = parts[0].strip()
            cond = parts[1].strip()
            inc = parts[2].strip()

            body_start = cond_end + 1
            while body_start < len(code) and code[body_start].isspace():
                body_start += 1

            if body_start < len(code) and code[body_start] == "{":
                body_end = find_matching(code, body_start, "{", "}")
                body = code[body_start+1:body_end]
                i = body_end + 1
            else:
                semi = code.find(";", body_start)
                body = code[body_start:semi]
                i = semi + 1

            nodes.append({
                "type": "for",
                "init": init,
                "cond": cond,
                "inc": inc,
                "body": parse_block(body)
            })
            continue

        semi = code.find(";", i)
        if semi == -1:
            break

        stmt = code[i:semi].strip()
        if stmt:
            # Check if the statement is an I/O operation
            io_pattern = r'\b(printf|scanf|puts|gets|fprintf|fscanf|getchar|putchar|fgets|fputs)\b'
            if re.search(io_pattern, stmt):
                nodes.append({"type": "io", "text": stmt})
            else:
                nodes.append({"type": "stmt", "text": stmt})

        i = semi + 1

    # Optimize consecutive identical normal or io statement block into one
    optimized_nodes = []
    for node in nodes:
        if optimized_nodes and optimized_nodes[-1]["type"] == node["type"] and node["type"] in ["stmt", "io"]:
            optimized_nodes[-1]["text"] += "\n" + node["text"]
        else:
            optimized_nodes.append(node)

    return optimized_nodes


# ==========================================================
# Graph Builder
# ==========================================================

def build_graph(nodes, dot, parent, entry_label=None):

    for i, node in enumerate(nodes):
        
        # Apply the entry label only to the very first node in this sequence
        current_label = entry_label if i == 0 else None

        # =====================================================
        # SIMPLE STATEMENT OR I/O
        # =====================================================
        if node["type"] in ["stmt", "io"]:
            node_id = str(id(node))
            
            # Choose shape based on type
            shape = IO_SHAPE if node["type"] == "io" else BOX_SHAPE
            
            dot.node(node_id, wrap_label(node["text"]), shape=shape)
            
            if parent is not None:
                if current_label:
                    dot.edge(parent, node_id, label=current_label)
                else:
                    dot.edge(parent, node_id)

            parent = node_id

            # Parse lines to check for control flow breaks (return/break/continue)
            lines = [line.strip() for line in node["text"].split('\n')]
            last_stmt = lines[-1] if lines else ""
            if last_stmt.startswith('return') or last_stmt.startswith('break') or last_stmt.startswith('continue'):
                if last_stmt.startswith('return'):
                    dot.edge(node_id, "END")
                parent = None

        # =====================================================
        # IF STATEMENT
        # =====================================================
        elif node["type"] == "if":
            cond_id = str(id(node))
            dot.node(cond_id, wrap_label(node["cond"]), shape=DIAMOND_SHAPE)
            
            if parent is not None:
                if current_label:
                    dot.edge(parent, cond_id, label=current_label)
                else:
                    dot.edge(parent, cond_id)

            merge_id = cond_id + "_merge"
            dot.node(merge_id, "", shape="point")

            # ---- TRUE branch ----
            if node["body"]:
                true_end = build_graph(node["body"], dot, cond_id, entry_label=tf_label("True"))
                if true_end is not None:
                    dot.edge(true_end, merge_id)
            else:
                dot.edge(cond_id, merge_id, label=tf_label("True"))

            # ---- FALSE branch (Handles 'else' blocks) ----
            if "else_body" in node and node["else_body"]:
                false_end = build_graph(node["else_body"], dot, cond_id, entry_label=tf_label("False"))
                if false_end is not None:
                    dot.edge(false_end, merge_id)
            else:
                dot.edge(cond_id, merge_id, label=tf_label("False"))

            parent = merge_id

        # =====================================================
        # WHILE LOOP
        # =====================================================
        elif node["type"] == "while":
            cond_id = str(id(node))
            dot.node(cond_id, wrap_label(node["cond"]), shape=DIAMOND_SHAPE)
            
            if parent is not None:
                if current_label:
                    dot.edge(parent, cond_id, label=current_label)
                else:
                    dot.edge(parent, cond_id)

            # TRUE branch → body
            if node["body"]:
                body_end = build_graph(node["body"], dot, cond_id, entry_label=tf_label("True"))
                # loop back
                if body_end is not None:
                    dot.edge(body_end, cond_id)
            else:
                dot.edge(cond_id, cond_id, label=tf_label("True"))

            # FALSE branch → exit
            exit_id = cond_id + "_exit"
            dot.node(exit_id, "", shape="point")

            dot.edge(cond_id, exit_id, label=tf_label("False"))

            parent = exit_id

        # =====================================================
        # FOR LOOP
        # =====================================================
        elif node["type"] == "for":
            # INIT
            init_id = str(id(node)) + "_init"
            dot.node(init_id, wrap_label(node["init"]), shape=BOX_SHAPE)
            
            if parent is not None:
                if current_label:
                    dot.edge(parent, init_id, label=current_label)
                else:
                    dot.edge(parent, init_id)

            # CONDITION
            cond_id = str(id(node)) + "_cond"
            dot.node(cond_id, wrap_label(node["cond"]), shape=DIAMOND_SHAPE)
            dot.edge(init_id, cond_id)

            # TRUE branch → body
            if node["body"]:
                body_end = build_graph(node["body"], dot, cond_id, entry_label=tf_label("True"))
            else:
                body_end = cond_id

            # INCREMENT
            inc_id = str(id(node)) + "_inc"
            dot.node(inc_id, wrap_label(node["inc"]), shape=BOX_SHAPE)

            if body_end is not None:
                dot.edge(body_end, inc_id)
            dot.edge(inc_id, cond_id)

            # FALSE branch → exit
            exit_id = cond_id + "_exit"
            dot.node(exit_id, "", shape="point")

            dot.edge(cond_id, exit_id, label=tf_label("False"))

            parent = exit_id

    return parent


# ==========================================================
# Flowchart Generator
# ==========================================================

def generate_flowchart(func):

    dot = graphviz.Digraph(format=OUTPUT_FORMAT)

    size_value = f"{GRAPH_WIDTH},{GRAPH_HEIGHT}"
    if FORCE_GRAPH_SIZE:
        size_value += "!"

    dot.attr(
        rankdir=RANK_DIRECTION,
        splines=SPLINE_STYLE,
        nodesep=NODE_SEPARATION,
        ranksep=RANK_SEPARATION,
        dpi=DPI,
        size=size_value
    )

    dot.attr(
        'node',
        fontsize=FONT_SIZE,
        fontname=FONT_NAME,
        margin=NODE_MARGIN
    )

    dot.node("START", "START", shape=OVAL_SHAPE)
    dot.node("END", "END", shape=OVAL_SHAPE)

    parsed = parse_block(func["body"])
    last = build_graph(parsed, dot, "START")
    if last is not None:
        dot.edge(last, "END")

    filename = f"Flowchart_{func['name']}"
    output = dot.render(filename, cleanup=True)

    print("Saved as:", output)


# ==========================================================
# CONFIGURATION SECTION
# ==========================================================

OUTPUT_FORMAT = "png"
DPI = "600"

RANK_DIRECTION = "TB"
GRAPH_WIDTH = "15"
GRAPH_HEIGHT = "20"
FORCE_GRAPH_SIZE = True

NODE_SEPARATION = "0.2"
RANK_SEPARATION = "0.2"

FONT_NAME = "Helvetica"
FONT_SIZE = "24"

NODE_MARGIN = "0.15,0.1"
BOX_SHAPE = "box"
DIAMOND_SHAPE = "diamond"
OVAL_SHAPE = "oval"
IO_SHAPE = "parallelogram" # Added mapping for I/O

SPLINE_STYLE = "ortho"

LABEL_WRAP_WIDTH = 32

# True/False label customization
TF_LABEL_SIZE = "20"        # Increase this to enlarge True/False
TF_LABEL_FONT = "Helvetica"
TF_LABEL_COLOR = "black"
TF_LABEL_BOLD = True


# ==========================================================
# Selection Parser
# ==========================================================

def parse_selection(raw, count):
    """Parse user input into a list of 0-based indices.
    Supports: * (all), comma-separated (1,3,5), ranges (2-4), or a mix (1,3-5).
    """
    if raw.strip() == "*":
        return list(range(count))

    indices = []
    for part in raw.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            start, end = int(start.strip()), int(end.strip())
            indices.extend(range(start - 1, end))  # convert to 0-based
        else:
            indices.append(int(part) - 1)

    # Filter to valid range and deduplicate while preserving order
    seen = set()
    valid = []
    for idx in indices:
        if 0 <= idx < count and idx not in seen:
            seen.add(idx)
            valid.append(idx)
    return valid


# ==========================================================
# MAIN
# ==========================================================

def main():

    c_files = [f for f in os.listdir('.') if f.endswith(".c")]

    if not c_files:
        print("No C files found.")
        return

    functions = []
    for file in c_files:
        functions.extend(extract_c_functions(file))

    if not functions:
        print("No functions found in C files.")
        return

    print("\nAvailable Functions:")
    for i, f in enumerate(functions):
        print(f"[{i+1}] {f['name']} ({f['file']})")

    raw = input("\nSelect functions (e.g. 1,3,5 or 1-4 or *): ").strip()
    selected = parse_selection(raw, len(functions))

    if not selected:
        print("No valid selection.")
        return

    for idx in selected:
        generate_flowchart(functions[idx])


if __name__ == "__main__":
    main()