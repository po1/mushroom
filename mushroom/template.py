import functools

import lark

grammar = """
SP: /\s+/
IF: "if"i
ELSE: "else"i
ENDIF: "endif"i
FOR: "for"i
IN: "in"i
ENDFOR: "endfor"i
BEGIN: "{"
END: "}"
CONTENT: /[^{}]+/
NAME: /[a-zA-Z0-9_]+/

dotted_name: NAME ( "." NAME )*

if_: BEGIN IF dotted_name END
else_: BEGIN ELSE END
endif_: BEGIN ENDIF END

for_: BEGIN FOR NAME IN dotted_name END
endfor_: BEGIN ENDFOR END

if_endif: if_ expressions endif_
if_else_endif: if_ expressions else_ expressions endif_
for_endfor: for_ expressions endfor_

var_: BEGIN dotted_name END

template: if_else_endif | if_endif | for_endfor | var_
content: CONTENT

expression: content | template
expressions: expression*

start: expressions

%ignore SP
"""


@functools.cache
def get_parser():
    return lark.Lark(grammar)


class Simplifier(lark.Transformer):
    @classmethod
    @functools.cache
    def get_instance(cls):
        return cls()

    def if_(self, children):
        return lark.Token("if_", children[2])

    def dotted_name(self, children):
        return ".".join(children)

    def else_(self, children):
        return lark.Token("else_", None)

    def endif_(self, children):
        return lark.Token("endif_", None)

    def for_(self, children):
        return lark.Token("for_", [str(children[2]), children[4]])

    def endfor_(self, children):
        return lark.Token("endfor_", None)

    def expression(self, children):
        return children[0]

    def template(self, children):
        return children[0]


class Parser(lark.visitors.Interpreter):
    def __init__(self, ctx=None):
        self.txt = ""
        self.cur_ctx = ctx or {}

    def render(self):
        return self.txt

    def content(self, tree):
        self.txt += tree.children[0]

    def if_endif(self, tree):
        if self.get_var(tree.children[0].value):
            self.visit(tree.children[1])

    def if_else_endif(self, tree):
        if self.get_var(tree.children[0].value):
            self.visit(tree.children[1])
        else:
            self.visit(tree.children[3])

    def for_endfor(self, tree):
        for it in self.get_var(tree.children[0].value[1]):
            self.cur_ctx[tree.children[0].value[0]] = it
            self.visit(tree.children[1])

    def var_(self, tree):
        self.txt += str(self.get_var(tree.children[1]))

    def get_var(self, var):
        val = eval(var, self.cur_ctx)
        if callable(val):
            val = val()
        return val


def parse(template, context=None):
    tree = Simplifier.get_instance().transform(get_parser().parse(template))
    parser = Parser(context)
    parser.visit(tree)
    return parser.render()
