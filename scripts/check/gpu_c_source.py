"""Match C code fragments for source-based negative tests.

Whitespace and comments may change during normalization. Identifiers,
operators and complete literals must still match, and every mutation must
declare how many non-overlapping sites it expects to change.
"""

import re


_SPLICE = re.compile(r"\\\r?\n")
_TOKEN = re.compile(
    r"(?P<comment>/\*.*?\*/|//[^\n]*)"
    r'|(?:u8|u|U|L)?"(?:\\.|[^"\\])*"'
    r"|(?:u|U|L)?'(?:\\.|[^'\\])*'"
    r"|[A-Za-z_]\w*"
    r"|(?:0[xX][0-9A-Fa-f]+|[0-9]+)[A-Za-z_0-9.]*"
    r"|>>=|<<=|->|\+\+|--|&&|\|\||==|!=|<=|>=|<<|>>"
    r"|\+=|-=|\*=|/=|%=|&=|\|=|\^=|##|\.\.\.|[^\s]",
    re.DOTALL,
)


def c_tokens(source):
    """Return spelling and offsets, retaining strings as indivisible tokens."""
    logical = source
    offsets = None
    if _SPLICE.search(source):
        parts = []
        offsets = []
        start = 0
        for splice in _SPLICE.finditer(source):
            parts.append(source[start : splice.start()])
            offsets.extend(range(start, splice.start()))
            start = splice.end()
        parts.append(source[start:])
        offsets.extend(range(start, len(source)))
        logical = "".join(parts)
    # C removes line splices before recognizing comments, identifiers or
    # literals. Keep original offsets so a mutation replaces the real bytes.
    return [
        (
            match.group(),
            offsets[match.start()] if offsets is not None else match.start(),
            offsets[match.end() - 1] + 1 if offsets is not None else match.end(),
        )
        for match in _TOKEN.finditer(logical)
        if match.lastgroup != "comment"
    ]


def c_fragment_spans(source, fragment):
    wanted = [token for token, _, _ in c_tokens(fragment)]
    if not wanted:
        raise ValueError("A C mutation needs a nonempty code fragment")
    if wanted[0] == "#":
        raise ValueError(
            "Preprocessor directives require an explicit directive-aware mutation"
        )
    tokens = c_tokens(source)
    length = len(wanted)
    spans = []
    for index in range(len(tokens) - length + 1):
        if tokens[index][0] != wanted[0]:
            continue
        if [token for token, _, _ in tokens[index : index + length]] == wanted:
            span = (tokens[index][1], tokens[index + length - 1][2])
            if spans and span[0] < spans[-1][1]:
                raise ValueError("Overlapping C mutation sites are ambiguous")
            spans.append(span)
    return spans


def replace_c_fragment(source, fragment, replacement, expected=1):
    """Replace exactly the declared number of token-matched code sites."""
    if not isinstance(expected, int) or expected < 1:
        raise ValueError("A C mutation must require at least one site")
    spans = c_fragment_spans(source, fragment)
    if len(spans) != expected:
        raise ValueError(
            f"Expected {expected} C mutation site(s), found {len(spans)}: {fragment!r}"
        )
    # The original first-line indentation stays outside the token span.
    # Do not double it when an older mutation template includes a tab.
    replacement = replacement.lstrip(" \t")
    for start, end in reversed(spans):
        source = source[:start] + replacement + source[end:]
    return source


def extract_c_function(source, name):
    """Extract exactly one top-level function definition, allowing wrapped types.

    Match a complete named parameter list followed by a body; declarations
    and calls are skipped. Token offsets retain the actual product source,
    including comments, strings and indentation inside the function.
    """
    tokens = c_tokens(source)
    definitions = []
    for index, (spelling, begin, _) in enumerate(tokens):
        if spelling != name or index + 1 >= len(tokens) or tokens[index + 1][0] != "(":
            continue
        depth = 0
        closing = None
        for cursor in range(index + 1, len(tokens)):
            token = tokens[cursor][0]
            if token == "(":
                depth += 1
            elif token == ")":
                depth -= 1
                if depth == 0:
                    closing = cursor
                    break
        if (
            closing is None
            or closing + 1 >= len(tokens)
            or tokens[closing + 1][0] != "{"
        ):
            continue
        # A definition name begins a line, possibly after its return type;
        # a nested call cannot start a top-level definition signature.
        start = source.rfind("\n", 0, begin) + 1
        prefix = source[start:begin]
        if any(char in prefix for char in "=;{}()"):
            continue
        if not prefix.strip():
            previous_end = start - 1
            previous_start = source.rfind("\n", 0, previous_end) + 1
            previous = source[previous_start:previous_end]
            if not previous.strip() or any(char in previous for char in ";{}#"):
                raise ValueError(f"Missing return type for C function {name}")
            start = previous_start
        depth = 0
        end = None
        for cursor in range(closing + 1, len(tokens)):
            token = tokens[cursor][0]
            if token == "{":
                depth += 1
            elif token == "}":
                depth -= 1
                if depth == 0:
                    end = tokens[cursor][2]
                    break
        if end is None:
            raise ValueError(f"Unbalanced C function body: {name}")
        definitions.append(source[start:end] + "\n")
    if len(definitions) != 1:
        raise ValueError(f"Expected one definition of {name}, found {len(definitions)}")
    return definitions[0]
