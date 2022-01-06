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

from edb.common import ast as ast_visitor

from edb.edgeql import ast as qlast
from edb.edgeql import qltypes
from edb.ir import ast as irast
from edb.pgsql import ast as pgast

from . import clauses
from . import context
from . import dispatch
from . import pathctx
from . import relctx
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
    group_uses = visitor.sightings

    # OK Actually compile now
    query = ctx.stmt

    # Compile a GROUP BY into a subquery, along with all the aggregations
    with ctx.subrel() as groupctx:
        grouprel = groupctx.rel

        # breakpoint()

        # First compile the actual subject
        # subrel *solely* for path id map reasons
        with groupctx.subrel() as subjctx:
            subjctx.path_scope = subjctx.path_scope.new_child()
            # ???
            # MAYBE WE SHOULD SWIZZLE AROUND SUBREL
            subjctx.path_scope[stmt.subject.path_id] = None
            subjctx.expr_exposed = False

            pathctx.put_path_id_map(
                subjctx.rel,
                stmt.group_binding.path_id, stmt.subject.path_id)
            dispatch.visit(stmt.subject, ctx=subjctx)
        # XXX: aspects?
        subj_rvar = relctx.rvar_for_rel(
            subjctx.rel, ctx=groupctx, lateral=True)
        # aspects = pathctx.list_path_aspects(
        #     newctx.rel, element.val.path_id, env=ctx.env)
        # update_mask=False because we are doing this solely to remap
        # elements individually and don't want to affect the mask.
        relctx.include_rvar(
            grouprel, subj_rvar, stmt.group_binding.path_id,
            update_mask=False, ctx=groupctx)
        relctx.include_rvar(
            grouprel, subj_rvar, stmt.subject.path_id,
            update_mask=False, ctx=groupctx)

        # Now we compile the bindings
        groupctx.path_scope = subjctx.path_scope.new_child()
        for _alias, value in stmt.using.items():
            # assert groupctx.path_scope[value.path_id] == ctx.rel
            # groupctx.path_scope[value.path_id] = None  # ???
            dispatch.visit(value, ctx=groupctx)

        for group_use in group_uses:
            if not group_use:
                continue
            with groupctx.subrel() as hoistctx:
                # XXX: do we need the rvars??
                relgen.process_set_as_agg_expr_inner(
                    group_use, hoistctx.rel,
                    aspect='value', wrapper=None, for_group_by=True,
                    ctx=hoistctx)
                pathctx.get_path_value_output(
                    rel=hoistctx.rel, path_id=group_use.path_id, env=ctx.env)
                pathctx.put_path_value_var(
                    grouprel, group_use.path_id, hoistctx.rel, env=ctx.env
                )

        packed = False
        if None in group_uses:
            packed = True
            # OK WE NEED TO DO THE HARD THING
            # XXX: dupe with materialized stuff
            # XXX: Also, when all we do is serialize, we'd like to *just*
            # serialize...
            with context.output_format(ctx, context.OutputFormat.NATIVE), (
                    ctx.new()) as matctx:
                matctx.materializing |= {stmt}  # ...

                # XXX: XXX: this is bullshit and we need to do
                # something like this during IR compilation if at all
                stmt.group_binding.shape = stmt.subject.shape

                mat_qry = relgen.set_as_subquery(
                    stmt.group_binding, as_value=True, ctx=matctx)
                mat_qry = relctx.set_to_array(
                    path_id=stmt.group_binding.path_id,
                    for_group_by=True,
                    query=mat_qry,
                    ctx=matctx)
                if not mat_qry.target_list[0].name:
                    mat_qry.target_list[0].name = ctx.env.aliases.get('v')

                ref = pgast.ColumnRef(
                    name=[mat_qry.target_list[0].name],
                    is_packed_multi=True,
                )
                pathctx.put_path_packed_output(
                    mat_qry, stmt.group_binding.path_id, ref)

                pathctx.put_path_var(
                    grouprel, stmt.group_binding.path_id, mat_qry,
                    aspect='value',
                    flavor='packed', env=ctx.env
                )

        grouprel.group_clause = [
            compile_grouping_el(el, stmt, ctx=groupctx) for el in stmt.by
        ]

    group_rvar = relctx.rvar_for_rel(grouprel, ctx=ctx, lateral=True)
    # ???
    if packed:
        relctx.include_rvar(
            query, group_rvar, path_id=stmt.group_binding.path_id,
            flavor='packed', update_mask=False, pull_namespace=False,
            aspects=('value',),  # maybe?
            ctx=ctx)
    # XXX: mask, aspects??
    else:
        relctx.include_rvar(
            query, group_rvar, stmt.group_binding.path_id,
            aspects=('value',),  # maybe?
            update_mask=False, ctx=ctx)

    # Set up the hoisted aggregates and bindings to be found
    # in the group subquery.
    for group_use in [*group_uses, *stmt.using.values()]:
        if group_use:
            pathctx.put_path_rvar(
                query, group_use.path_id,
                group_rvar, aspect='value', env=ctx.env)

    # Process materialized sets
    clauses.compile_materialized_exprs(query, stmt, ctx=ctx)

    # ... right? It's that simple?
    clauses.compile_output(stmt.result, ctx=ctx)

    # XXX: bindings?

    return query


def compile_group(
        stmt: irast.GroupStmt, *,
        ctx: context.CompilerContextLevel) -> pgast.BaseExpr:
    with ctx.substmt() as sctx:
        return _compile_group(stmt, ctx=sctx, parent_ctx=ctx)
