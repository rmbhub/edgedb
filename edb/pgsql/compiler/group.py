#
# This source file is part of the EdgeDB open source project.
#
# Copyright 2008-present MagicStack Inc. and the EdgeDB authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


from __future__ import annotations

from typing import *

from edb import errors

from edb.common import ast as ast_visitor

from edb.edgeql import ast as qlast
from edb.edgeql import qltypes
from edb.ir import ast as irast
from edb.pgsql import ast as pgast

# from . import clauses
from . import context
from . import dispatch
from . import pathctx
from . import relgen



class FindAggregatingUses(ast_visitor.NodeVisitor):
    """
    XXX: track visibility, and only look at shapes when visible??
    """
    skip_hidden = True
    extra_skips = frozenset(['materialized_sets'])

    def __init__(
        self, target: irast.PathId, to_skip: AbstractSet[irast.PathId]
    ) -> None:
        super().__init__()
        self.target = target
        self.to_skip = to_skip
        self.outer_aggregate: Optional[irast.Set] = None
        self.sightings: Set[Optional[irast.Set]] = set()

    def visit_Stmt(self, stmt: irast.Stmt) -> Any:
        # XXX???
        # Sometimes there is sharing, so we want the official scope
        # for a node to be based on its appearance in the result,
        # not in a subquery.
        # I think it might not actually matter, though.

        # XXX: make sure stuff like
        # WITH X := g.x, (count(X), X)
        # gets flagged
        # SHOULD WE SKIP THE BINDINGS???

        self.visit(stmt.bindings)
        if stmt.iterator_stmt:
            self.visit(stmt.iterator_stmt)
        if isinstance(stmt, irast.MutatingStmt):
            self.visit(stmt.subject)
        self.visit(stmt.result)

        return self.generic_visit(stmt)

    def visit_Set(self, node: irast.Set) -> None:
        if node.path_id in self.to_skip:
            return

        if node.path_id == self.target:
            self.sightings.add(self.outer_aggregate)
            return

        self.visit(node.rptr)
        self.visit(node.shape)

        if isinstance(node.expr, irast.FunctionCall):
            self.process_call(node.expr, node)
        else:
            self.visit(node.expr)
        # if not node.rptr:
        #     self.visit(node.expr)

    def process_call(
            self, node: irast.FunctionCall, ir_set: irast.Set) -> None:
        # It needs to be backed by an actual SQL function and must
        # not return SET OF
        ok = (
            node.typemod != qltypes.TypeModifier.SetOfType
            and node.func_sql_function
        )
        for arg, typemod in zip(node.args, node.params_typemods):
            old = self.outer_aggregate
            if (
                ok
                and old is None
                and typemod == qltypes.TypeModifier.SetOfType
            ):
                self.outer_aggregate = ir_set
            self.visit(arg)
            self.outer_aggregate = old


def compile_grouping_atom(
    el: qlast.GroupingAtom,
    stmt: irast.GroupStmt, *, ctx: context.CompilerContextLevel
) -> pgast.Base:
    if isinstance(el, qlast.GroupingIdentList):
        return pgast.GroupingOperation(
            args=[
                compile_grouping_atom(at, stmt, ctx=ctx) for at in el.elements
            ],
        )

    assert isinstance(el, qlast.ObjectRef)
    alias_set = stmt.using[el.name]
    return pathctx.get_path_var(
        ctx.rel, alias_set.path_id, aspect='value', env=ctx.env)


def compile_grouping_el(
    el: qlast.GroupingElement,
    stmt: irast.GroupStmt, *, ctx: context.CompilerContextLevel
) -> pgast.Base:
    if isinstance(el, qlast.GroupingSets):
        return pgast.GroupingOperation(
            operation='GROUPING SETS',
            args=[compile_grouping_el(sub, stmt, ctx=ctx) for sub in el.sets],
        )
    elif isinstance(el, qlast.GroupingOperation):
        return pgast.GroupingOperation(
            operation=el.oper,
            args=[
                compile_grouping_atom(at, stmt, ctx=ctx) for at in el.elements
            ],
        )
    elif isinstance(el, qlast.GroupingSimple):
        return compile_grouping_atom(el.element, stmt, ctx=ctx)
    raise AssertionError('Unknown GroupingElement')


def _compile_group(
        stmt: irast.GroupStmt, *,
        ctx: context.CompilerContextLevel,
        parent_ctx: context.CompilerContextLevel) -> pgast.BaseExpr:

    # XXX: or should we do this analysis on the IR side???
    visitor = FindAggregatingUses(
        stmt.group_binding.path_id,
        {x.path_id for x in stmt.using.values()},
    )
    visitor.visit(stmt.result)

    print("GOT THIS STUFF", visitor.sightings)
    if None in visitor.sightings:
        raise errors.QueryError("Still need to aggregate group references!")

    # OK Actually compile now
    query = ctx.stmt

    with ctx.new() as newctx:
        dispatch.visit(stmt.subject, ctx=newctx)

    # ???
    for _alias, value in stmt.using.items():
        dispatch.visit(value, ctx=ctx)

    # ????
    # pathctx.put_path_id_map(
    #     query, stmt.group_binding.path_id, stmt.subject.path_id)
    # pathctx.put_path_id_map(
    #     query, stmt.subject.path_id, stmt.group_binding.path_id)

    subj_rvar = pathctx.get_path_rvar(
        query, stmt.subject.path_id, aspect='value', env=ctx.env)

    for aspect in ['source', 'value']:
        pathctx.put_path_rvar(
            query, stmt.group_binding.path_id,
            subj_rvar,
            aspect=aspect,
            env=ctx.env)

    # AAAAAAYYYAYAYAYAYAY
    # stmt.group_binding.expr = irast.SelectStmt(result=stmt.subject)
    # breakpoint()

    # clauses.compile_output(stmt.result, ctx=ctx)

    # XXX?
    out = relgen.set_as_subquery(stmt.result, ctx=ctx)
    name = ctx.env.aliases.get('asdf')
    query.target_list.append(pgast.ResTarget(name=name, val=out))
    result = pgast.ColumnRef(name=[name], nullable=True)
    pathctx._put_path_output_var(
        query, stmt.result.path_id, 'value', result, env=ctx.env)
    # ... wrong, but ok
    pathctx._put_path_output_var(
        query, stmt.result.path_id, 'serialized', result, env=ctx.env)
    # breakpoint()

    query.group_clause = [
        compile_grouping_el(el, stmt, ctx=ctx) for el in stmt.by
    ]

    # XXX: bindings?

    return query

def compile_group(
        stmt: irast.GroupStmt, *,
        ctx: context.CompilerContextLevel) -> pgast.BaseExpr:
    with ctx.substmt() as sctx:
        return _compile_group(stmt, ctx=sctx, parent_ctx=ctx)
