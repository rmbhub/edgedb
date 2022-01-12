#
# This source file is part of the EdgeDB open source project.
#
# Copyright 2012-present MagicStack Inc. and the EdgeDB authors.
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

import os.path

from edb.testbase import server as tb
from edb.tools import test


class TestEdgeQLGroupInternal(tb.QueryTestCase):
    '''These tests are focused on using the internal GROUP statement.'''

    SCHEMA = os.path.join(os.path.dirname(__file__), 'schemas',
                          'issues.esdl')

    SCHEMA_CARDS = os.path.join(os.path.dirname(__file__), 'schemas',
                                'cards.esdl')

    SETUP = os.path.join(os.path.dirname(__file__), 'schemas',
                         'groups_setup.edgeql')

    @test.xfail('still broken')
    async def test_edgeql_igroup_simple_01(self):
        await self.assert_query_result(
            r'''
                DETACHED GROUP User
                USING _ := User.name
                BY _
                INTO User
                UNION count(User.<owner);
            ''',
            {4, 2},
        )

    async def test_edgeql_igroup_simple_02(self):
        await self.assert_query_result(
            r'''
                DETACHED GROUP Issue := Issue
                # time_estimate is {} on some Issues,
                # but that's a valid grouping
                USING _ := Issue.time_estimate
                BY _
                INTO Issue
                # count using a property
                UNION count(Issue.id);
            ''',
            {3, 1},
        )

    async def test_edgeql_igroup_simple_03(self):
        await self.assert_query_result(
            r'''
                DETACHED GROUP Issue
                USING _ := Issue.time_estimate
                BY _
                INTO Issue
                # count Issue directly
                UNION count(Issue);
            ''',
            {3, 1},
        )

    async def test_edgeql_igroup_simple_04(self):
        await self.assert_query_result(
            r'''
                DETACHED GROUP Issue
                USING _ := Issue.time_estimate
                BY _
                INTO Issue
                # count Issue name, which should be same as counting
                # Issues, since the name property is *1
                UNION count(Issue.name);
            ''',
            {3, 1},
        )

    @test.xfail('still broken')
    async def test_edgeql_igroup_simple_05(self):
        # XXX: The issue here is that we don't do a semi-join

        await self.assert_query_result(
            r'''
                DETACHED GROUP Issue
                USING _ := Issue.time_estimate
                BY _
                INTO Issue
                # count Issue statuses, which is not the same as counting
                # Issues, since multiple Issues can point to the same Status
                UNION count(Issue.status);
            ''',
            {2, 1},
        )

    async def test_edgeql_igroup_simple_06(self):
        await self.assert_query_result(
            r'''
                DETACHED GROUP Issue
                USING _ := Issue.time_estimate
                BY _
                INTO Issue
                # unusual qualifier for 'count', but should be the same as
                # counting the statuses directly
                UNION count(DISTINCT Issue.status.id);
            ''',
            {2, 1},
        )

    async def test_edgeql_igroup_simple_07(self):
        await self.assert_query_result(
            r'''
                WITH MODULE cards
                DETACHED GROUP Card
                USING _ := .cost//2
                BY _
                INTO Card
                UNION count(DISTINCT Card.element);
            ''',
            tb.bag([3, 2, 3]),
        )

    async def test_edgeql_igroup_simple_08(self):
        await self.assert_query_result(
            r'''
            WITH MODULE cards
            DETACHED GROUP Card
            USING _ := .cost//2
            BY _
            INTO Card
            UNION count(array_agg(Card.element));
            ''',
            [1, 1, 1],
        )

    async def test_edgeql_igroup_by_01(self):
        await self.assert_query_result(
            r"""
                SELECT (
                DETACHED GROUP Issue
                USING B :=  Issue.status.name
                BY B
                INTO Issue
                UNION (
                    sum := sum(<int64>Issue.number),
                    status := B,
                )
                ) ORDER BY .status;
            """,
            [
                {
                    'status': 'Closed',
                    'sum': 7,
                },
                {
                    'status': 'Open',
                    'sum': 3,
                }
            ],
        )

    async def test_edgeql_igroup_by_02(self):
        await self.assert_query_result(
            r"""
                SELECT (
                DETACHED GROUP Issue
                USING B :=  Issue.status.name
                BY B
                INTO Issue
                UNION (
                    sum := sum(<int64>Issue.number),
                    status := B,
                )
                )
                FILTER .sum > 5
                ORDER BY .status;
            """,
            [{
                'status': 'Closed',
                'sum': 7,
            }],
        )

    async def test_edgeql_igroup_result_alias_01(self):
        await self.assert_query_result(
            r'''
                SELECT _ := (
                DETACHED GROUP Issue
                USING _ :=  Issue.time_estimate
                BY _
                INTO Issue
                UNION (
                    count := count(Issue.status.id),
                    te := array_agg(DISTINCT Issue.time_estimate > 0),
                )
                ) ORDER BY _.te;
            ''',
            [{'count': 3, 'te': []}, {'count': 1, 'te': [True]}]
        )

        await self.assert_query_result(
            r'''
                SELECT _ := (
                DETACHED GROUP Issue
                USING _ :=  Issue.time_estimate
                BY _
                INTO Issue
                UNION (
                    count := count(Issue.status.id),
                    te := array_agg(DISTINCT Issue.time_estimate > 0),
                )
                ) ORDER BY _.te DESC;
            ''',
            [{'count': 1, 'te': [True]}, {'count': 3, 'te': []}],
        )

    async def test_edgeql_igroup_result_alias_02(self):
        await self.assert_query_result(
            r'''
                SELECT _ := (
                DETACHED GROUP Issue
                USING _ :=  Issue.time_estimate
                BY _
                INTO Issue
                UNION (
                    count := count(Issue.status.id),
                    # confusing, but legal usage of '_' to refer to BY
                    # (this is comparable to SELECT Issue := count(Issue))
                    te := array_agg(_ > 0),
                )) ORDER BY
                    _.te DESC;
            ''',
            [{'count': 1, 'te': [True]}, {'count': 3, 'te': []}],
        )

    async def test_edgeql_igroup_nested_01(self):
        await self.assert_query_result(
            r"""
                SELECT
                    R := (
                        name := User.name,
                        issues := array_agg(
                            (
                                SELECT
                                (DETACHED GROUP
                                   UserIssue := User.<owner[IS Issue]
                                USING B :=  UserIssue.status.name
                                BY B
                                INTO UserIssue
                                UNION (
                                    status := B,
                                    count := count(UserIssue),
                                ))
                                ORDER BY .status
                            )
                        )
                    )
                ORDER BY R.name;
            """,
            [
                {
                    'name': 'Elvis',
                    'issues': [{
                        'status': 'Closed',
                        'count': 1,
                    }, {
                        'status': 'Open',
                        'count': 1,
                    }]
                },
                {
                    'name': 'Yury',
                    'issues': [{
                        'status': 'Closed',
                        'count': 1,
                    }, {
                        'status': 'Open',
                        'count': 1,
                    }]
                },
            ]
        )

    async def test_edgeql_igroup_returning_01(self):
        await self.assert_query_result(
            r'''
                DETACHED GROUP Issue
                USING _ :=  Issue.time_estimate
                BY _
                INTO Issue
                # The issues should be partitioned into 2 sub-sets by
                # Issue.time_estimate (with values {} and 3000). Therefore
                # we expect 2 results combined via UNION.
                UNION 42;
            ''',
            [42, 42],
        )

    async def test_edgeql_igroup_returning_02(self):
        await self.assert_query_result(
            r'''
                SELECT _ := (
                DETACHED GROUP Issue
                USING B := Issue.time_estimate
                BY B
                INTO Issue
                # No reason to restrict the above example to doing a
                # UNION of singletons.
                UNION {42, count(Issue)}
                ) ORDER BY _;
            ''',
            [1, 3, 42, 42],
        )

    @test.xfail('still broken - missing FROM-clause')
    async def test_edgeql_igroup_returning_03(self):
        await self.assert_query_result(
            r'''
                SELECT (
                DETACHED GROUP Issue
                USING B := Issue.status
                BY B
                INTO Issue
                # The result should be a set of status objects,
                # augmented with Issue.numbers corresponding to the
                # status.
                UNION B {
                    name,
                    nums := Issue.number
                }
                ) ORDER BY .name;
            ''',
            [
                {
                    'name': 'Closed',
                    'nums': {'3', '4'},
                },
                {
                    'name': 'Open',
                    'nums': {'1', '2'},
                }
            ],
        )

    async def test_edgeql_igroup_returning_04(self):
        await self.assert_query_result(
            r'''
                SELECT (
                DETACHED GROUP Issue
                USING _ := Issue.status
                BY _
                INTO Issue
                # Identical to the previous example, but expressed
                # slightly differently.
                UNION (
                    SELECT
                        Status {
                            name,
                            nums := Issue.number
                        }
                    # all issues in this subset will have the same
                    # status, so this FILTER is valid, although not
                    # necessarily optimal
                    FILTER Status = Issue.status
                )
                ) ORDER BY .name;
            ''',
            [
                {
                    'name': 'Closed',
                    'nums': {'3', '4'},
                },
                {
                    'name': 'Open',
                    'nums': {'1', '2'},
                }
            ],
        )

    async def test_edgeql_igroup_returning_05(self):
        await self.assert_query_result(
            r'''
                # a trivial group that is actually not doing anything
                # different from a plain SELECT
                WITH MODULE cards
                SELECT _ := (
                DETACHED GROUP Card
                USING _ :=  Card.element
                BY _
                INTO Card
                UNION Card.name
                )
                ORDER BY _;
            ''',
            [
                'Bog monster',
                'Djinn',
                'Dragon',
                'Dwarf',
                'Giant eagle',
                'Giant turtle',
                'Golem',
                'Imp',
                'Sprite',
            ],
        )

    @test.xfail('''
        Gets duplicated once for each group

        But it works if there is no outer SELECT
    ''')
    async def test_edgeql_igroup_returning_06(self):
        await self.assert_query_result(
            r'''
                # a trivial group that is actually not doing anything
                # different from a plain SELECT
                WITH MODULE cards
                SELECT (
                DETACHED GROUP Card
                USING _ :=  Card.element
                BY _
                INTO Card
                UNION Card {name}
                ) ORDER BY
                    .name;
            ''',
            [
                {'name': 'Bog monster'},
                {'name': 'Djinn'},
                {'name': 'Dragon'},
                {'name': 'Dwarf'},
                {'name': 'Giant eagle'},
                {'name': 'Giant turtle'},
                {'name': 'Golem'},
                {'name': 'Imp'},
                {'name': 'Sprite'},
            ],
        )

    @test.xfail('Broken when injecting types - missing FROM clause')
    async def test_edgeql_igroup_returning_07(self):
        self.assertTrue(False)  # ... prevent flakey unexpected successes

        await self.assert_query_result(
            r'''
                # Nominate a leader in each group from among the group.
                #
                # The below is a very long and explicit way of forming a
                # set of "leaders" and associated "members" for each
                # element.
                WITH
                    MODULE cards,
                    C2 := Card,
                    ELEMENTAL := (
                        # group cards into arrays by element
                        DETACHED GROUP Card
                        USING _ :=  Card.element
                        BY _
                        INTO Card
                        UNION array_agg(Card)
                    )
                SELECT _ := (
                    FOR X IN {ELEMENTAL}
                    # for each "elemental" array select a "leader"
                    UNION (
                        # the selection of leader is nested and has its
                        # own application of ORDER BY and LIMIT clauses
                        SELECT Card {
                                element,
                                name,
                                cost,
                                members := (
                                    # just unpacking the elemental cards
                                    # with a particular ordering and
                                    # specific links included in the final
                                    # result
                                    SELECT C2{name, cost}
                                    FILTER contains(X, C2)
                                    ORDER BY C2.cost
                                )
                            }
                        # the leader is selected from among the elemental array
                        FILTER contains(X, Card)
                        # the leader is defined as the one with the
                        # highest cost
                        ORDER BY Card.cost DESC
                        LIMIT 1
                    )
                )
                ORDER BY _.element;
            ''',
            [
                {
                    'cost': 4,
                    'name': 'Djinn',
                    'element': 'Air',
                    'members': [
                        {'cost': 1, 'name': 'Sprite'},
                        {'cost': 2, 'name': 'Giant eagle'},
                        {'cost': 4, 'name': 'Djinn'},
                    ],
                },
                {
                    'cost': 3,
                    'name': 'Golem',
                    'element': 'Earth',
                    'members': [
                        {'cost': 1, 'name': 'Dwarf'},
                        {'cost': 3, 'name': 'Golem'},
                    ],
                },
                {
                    'cost': 5,
                    'name': 'Dragon',
                    'element': 'Fire',
                    'members': [
                        {'cost': 1, 'name': 'Imp'},
                        {'cost': 5, 'name': 'Dragon'},
                    ],
                },
                {
                    'cost': 3,
                    'name': 'Giant turtle',
                    'element': 'Water',
                    'members': [
                        {'cost': 2, 'name': 'Bog monster'},
                        {'cost': 3, 'name': 'Giant turtle'},
                    ],
                }
            ]
        )

    @test.xfail('Broken when injecting types - is not a computed pointer')
    async def test_edgeql_igroup_returning_08(self):
        self.assertTrue(False)  # ... prevent flakey unexpected successes

        await self.assert_query_result(
            r'''
                # Nominate a leader in each group from among the group.
                #
                # Same as previous test, but with all of the shape spec
                # factored out tot he outermost SELECT.
                WITH
                    MODULE cards,
                    ELEMENTAL := (
                        DETACHED GROUP Card
                        USING _ :=  Card.element
                        BY _
                        INTO Card
                        UNION array_agg(Card)
                    )
                SELECT _ := (
                    FOR X IN {ELEMENTAL}
                    UNION (
                        SELECT Card {
                                element,
                                name,
                                cost,
                                members := (
                                    SELECT C2 := DISTINCT array_unpack(X)
                                    ORDER BY C2.cost
                                )
                            }
                        FILTER contains(X, Card)
                        ORDER BY Card.cost DESC
                        LIMIT 1
                    )
                ) {
                    # the entire shape spec of the result is now here
                    element,
                    name,
                    cost,
                    members: {
                        name,
                        cost
                    }
                }
                ORDER BY _.element;
            ''',
            [
                {
                    'cost': 4,
                    'name': 'Djinn',
                    'element': 'Air',
                    'members': [
                        {'cost': 1, 'name': 'Sprite'},
                        {'cost': 2, 'name': 'Giant eagle'},
                        {'cost': 4, 'name': 'Djinn'},
                    ],
                },
                {
                    'cost': 3,
                    'name': 'Golem',
                    'element': 'Earth',
                    'members': [
                        {'cost': 1, 'name': 'Dwarf'},
                        {'cost': 3, 'name': 'Golem'},
                    ],
                },
                {
                    'cost': 5,
                    'name': 'Dragon',
                    'element': 'Fire',
                    'members': [
                        {'cost': 1, 'name': 'Imp'},
                        {'cost': 5, 'name': 'Dragon'},
                    ],
                },
                {
                    'cost': 3,
                    'name': 'Giant turtle',
                    'element': 'Water',
                    'members': [
                        {'cost': 2, 'name': 'Bog monster'},
                        {'cost': 3, 'name': 'Giant turtle'},
                    ],
                }
            ]
        )

    @test.xfail('still broken')
    async def test_edgeql_igroup_returning_09(self):
        # this isn't valid syntax yet
        # how to deal with the order by Grouping?
        await self.assert_query_result(
            r'''
                # Nominate a leader in each group from among the group.
                #
                # Same as previous tests, but refactored to take full
                # advantage of DETACHED GROUP semantics and BY aliasing.
                WITH
                    MODULE cards,
                    C2 := Card
                DETACHED GROUP Card
                USING Element :=
                        # partition cards by element
                        Card.element
                BY Element
                INTO Card
                UNION (
                    # for every partition, compute the "leader"
                    SELECT C2 {
                        element,
                        name,
                        cost,
                        members := (
                            # all members of the particular elemental
                            # partition
                            SELECT Card{name, cost}
                            ORDER BY Card.cost
                        )
                    }
                    # the leader is a member of its elemental group
                    FILTER
                        C2 IN Card
                    # the leader is simply the one with the highest cost
                    ORDER BY
                        C2.cost DESC
                    LIMIT 1
                )
                # Ordering by the expression used to partition the
                # original set. This happens to be unambiguous since we
                # compute a singleton (LIMIT 1) set for each partition.
                ORDER BY Element;
            ''',
            [
                {
                    'cost': 4,
                    'name': 'Djinn',
                    'element': 'Air',
                    'members': [
                        {'cost': 1, 'name': 'Sprite'},
                        {'cost': 2, 'name': 'Giant eagle'},
                        {'cost': 4, 'name': 'Djinn'},
                    ],
                },
                {
                    'cost': 3,
                    'name': 'Golem',
                    'element': 'Earth',
                    'members': [
                        {'cost': 1, 'name': 'Dwarf'},
                        {'cost': 3, 'name': 'Golem'},
                    ],
                },
                {
                    'cost': 5,
                    'name': 'Dragon',
                    'element': 'Fire',
                    'members': [
                        {'cost': 1, 'name': 'Imp'},
                        {'cost': 5, 'name': 'Dragon'},
                    ],
                },
                {
                    'cost': 3,
                    'name': 'Giant turtle',
                    'element': 'Water',
                    'members': [
                        {'cost': 2, 'name': 'Bog monster'},
                        {'cost': 3, 'name': 'Giant turtle'},
                    ],
                }
            ]
        )

    @test.xfail('still broken - no method to generate code for TupleVar')
    async def test_edgeql_igroup_by_tuple_01(self):
        await self.assert_query_result(
            r"""
                SELECT (
                DETACHED GROUP Issue
                USING B := (Issue.status.name, Issue.time_estimate)
                # This tuple will be {} for Issues lacking
                # time_estimate. So effectively we're expecting only 2
                # subsets, grouped by:
                # - {}
                # - ('Open', 3000)
                BY B
                INTO Issue
                UNION (
                    sum := sum(<int64>Issue.number),
                    # don't forget to coalesce the {} or else the whole
                    # tuple will collapse
                    status := B.0 ?? '',
                    time_estimate := B.1 ?? 0
                )
                ) ORDER BY .status;
            """,
            [
                {
                    'status': '', 'sum': 9, 'time_estimate': 0
                },
                {
                    'status': 'Open', 'sum': 1, 'time_estimate': 3000
                }
            ],
        )

    async def test_edgeql_igroup_by_multiple_01(self):
        await self.assert_query_result(
            r"""
                SELECT _ := (
                DETACHED GROUP Issue
                USING
                    Stat := Issue.status.name,
                    Est := Issue.time_estimate
                # Unlike the tuple example, these grouping sets
                # generate more combinations:
                # - 'Closed', {}
                # - 'Open', {}
                # - 'Open', 3000
                BY Stat, Est
                INTO Issue
                UNION (
                    sum := sum(<int64>Issue.number),
                    # Stat is never {}, so coalescing is not needed
                    status := Stat,
                    # only this one needs to be coalesced
                    time_estimate := Est ?? 0
                )) ORDER BY _;

            """,
            [
                {
                    'status': 'Open', 'sum': 1, 'time_estimate': 3000,
                },
                {
                    'status': 'Open', 'sum': 2, 'time_estimate': 0,
                },
                {
                    'status': 'Closed', 'sum': 7, 'time_estimate': 0,
                },
            ],
        )

    async def test_edgeql_igroup_by_multiple_02(self):
        await self.assert_query_result(
            r"""
                SELECT (
                DETACHED GROUP Issue
                USING
                    Stat := Issue.status.name,
                    Est := Issue.time_estimate
                BY Stat, Est
                INTO Issue
                UNION (
                    sum := sum(<int64>Issue.number),
                    status := Stat,
                    time_estimate := Est ?? 0
                )
                # ordering condition derived from the grouping parameters
                ) ORDER BY .status THEN .time_estimate > 0;
            """,
            [
                {
                    'status': 'Closed', 'sum': 7, 'time_estimate': 0
                },
                {
                    'status': 'Open', 'sum': 2, 'time_estimate': 0
                },
                {
                    'status': 'Open', 'sum': 1, 'time_estimate': 3000
                }
            ],
        )

    async def test_edgeql_igroup_by_multiple_03(self):
        await self.assert_query_result(
            r"""
                SELECT (
                DETACHED GROUP Issue
                USING
                    Stat := Issue.status.name,
                    Est := Issue.time_estimate
                BY Stat, Est
                INTO Issue
                UNION (
                    # array_agg with ordering instead of sum
                    numbers := array_agg(
                        <int64>Issue.number ORDER BY Issue.number),
                    status := Stat,
                    time_estimate := Est ?? 0
                )
                ) ORDER BY .status THEN .time_estimate;
            """,
            [
                {
                    'status': 'Closed',
                    'time_estimate': 0,
                    'numbers': [3, 4],
                },
                {
                    'status': 'Open',
                    'time_estimate': 0,
                    'numbers': [2],
                },
                {
                    'status': 'Open',
                    'time_estimate': 3000,
                    'numbers': [1],
                }
            ],
        )

    async def test_edgeql_igroup_by_multiple_04(self):
        # XXX: we are getting an extra null in one of the watchers!!
        await self.assert_query_result(
            r"""
                SELECT (
                DETACHED GROUP Issue
                USING
                    Stat := Issue.status.name,
                    Est := Issue.time_estimate
                BY Stat, Est
                INTO Issue
                UNION (
                    # a couple of array_agg
                    numbers := array_agg(
                        <int64>Issue.number ORDER BY Issue.number),
                    watchers := array_agg(
                        <str>Issue.watchers.name ORDER BY Issue.watchers.name),
                    status := Stat,
                    time_estimate := Est ?? 0
                )
                ) ORDER BY .status THEN .time_estimate;
            """,
            [
                {
                    'status': 'Closed',
                    'time_estimate': 0,
                    'numbers': [3, 4],
                    'watchers': ['Elvis'],
                },
                {
                    'status': 'Open',
                    'time_estimate': 0,
                    'numbers': [2],
                    'watchers': ['Elvis'],
                },
                {
                    'status': 'Open',
                    'time_estimate': 3000,
                    'numbers': [1],
                    'watchers': ['Yury'],
                }
            ],
        )

    @test.xfail('still broken - extra nulls, duplicates')
    async def test_edgeql_igroup_by_multiple_05(self):
        await self.assert_query_result(
            r"""
                SELECT (
                DETACHED GROUP
                    # define a computable in the DETACHED GROUP expr
                    Issue := Issue {
                        less_than_four := <int64>Issue.number < 4
                    }
                USING
                    Stat := Issue.status.name,
                    # group by computable
                    X := Issue.less_than_four
                BY Stat, X
                INTO Issue
                UNION (
                    numbers := array_agg(
                        Issue.number ORDER BY Issue.number),
                    # watchers will sometimes be empty resulting in []
                    watchers := array_agg(
                        Issue.watchers.name ORDER BY Issue.watchers.name),
                    status := Stat,
                    x := X
                )
                ) ORDER BY .status THEN .x;
            """,
            [
                {
                    'status': 'Closed',
                    'numbers': ['4'],
                    'watchers': []
                },
                {
                    'status': 'Closed',
                    'numbers': ['3'],
                    'watchers': ['Elvis']
                },
                {
                    'status': 'Open',
                    'numbers': ['1', '2'],
                    'watchers': ['Elvis', 'Yury']
                }
            ],
        )

    async def test_edgeql_igroup_by_multiple_06(self):
        await self.assert_query_result(
            r"""
                SELECT (
                DETACHED GROUP Issue
                USING
                    Stat := Issue.status.name,
                    # group by some non-trivial expression
                    X := <int64>Issue.number < 4
                BY Stat, X
                INTO Issue
                UNION (
                    numbers := array_agg(
                        <int64>Issue.number ORDER BY Issue.number),
                    watchers := count(DISTINCT Issue.watchers),
                    status := Stat,
                    cnt := count(DISTINCT Issue),
                )) ORDER BY
                    # used a mixture of different aliases in ORDER BY
                    .status
                    THEN .watchers
                    # should work because count evaluates to a singleton
                    THEN .cnt;
            """,
            [
                {
                    'status': 'Closed',
                    'numbers': [4],
                    'watchers': 0
                },
                {
                    'status': 'Closed',
                    'numbers': [3],
                    'watchers': 1
                },
                {
                    'status': 'Open',
                    'numbers': [1, 2],
                    'watchers': 2
                }
            ],
        )

    async def test_edgeql_igroup_by_multiple_07a(self):
        # XXX: add a version that deletes the x
        await self.assert_query_result(
            r"""
                WITH MODULE cards
                SELECT (
                DETACHED GROUP C := Card
                USING x := C.cost
                BY x
                INTO C
                UNION (
                    array_agg(C.name ORDER BY C.name),
                    # At this point C is a subset of Card. So the below
                    # expression should be the size of the subset in
                    # percent.
                    100 * count(C) // count(Card),
                    x,
                )) ORDER BY .2;
            """,
            [
                [['Dwarf', 'Imp', 'Sprite'], 33, int],
                [['Bog monster', 'Giant eagle'], 22, int],
                [['Giant turtle', 'Golem'], 22, int],
                [['Djinn'], 11, int],
                [['Dragon'], 11, int]
            ]
        )

    @test.xfail('still broken - test may be wrong?')
    async def test_edgeql_igroup_linkproperty_simple_01(self):
        # XXX: I think this is wrong, right? Can't group by B??
        await self.assert_query_result(
            r"""
                # group by link property
                WITH MODULE cards
                SELECT _ := (
                DETACHED GROUP Card
                USING B := Card.<deck[IS User]@count
                BY B
                INTO Card
                UNION (
                    cards := array_agg(
                        DISTINCT Card.name ORDER BY Card.name),
                    count := B,
                )) ORDER BY _.count;
            """,
            [
                {
                    'cards': ['Bog monster', 'Djinn', 'Dragon', 'Giant eagle',
                              'Giant turtle', 'Golem'],
                    'count': 1
                },
                {
                    'cards': ['Dragon', 'Giant turtle', 'Golem', 'Imp'],
                    'count': 2
                },
                {
                    'cards': ['Bog monster', 'Dwarf', 'Giant eagle',
                              'Giant turtle', 'Golem'],
                    'count': 3
                },
                {
                    'cards': ['Dwarf', 'Sprite'],
                    'count': 4
                },
            ],
        )

    @test.xfail('still broken')
    async def test_edgeql_igroup_linkproperty_simple_02(self):
        await self.assert_query_result(
            r"""
                # use link property inside a group aggregate
                WITH MODULE cards
                SELECT _ := (
                DETACHED GROUP Card
                USING El :=
                        Card.element
                BY El
                INTO Card
                UNION (
                    cards := array_agg(
                        DISTINCT Card.name ORDER BY Card.name),
                    element := El,
                    count := sum(Card.<deck[IS User]@count),
                )) ORDER BY _.count;
            """,
            [
                {
                    'element': 'Fire',
                    'cards': ['Dragon', 'Imp'],
                    'count': 5,
                },
                {
                    'element': 'Earth',
                    'cards': ['Dwarf', 'Golem'],
                    'count': 13,
                },
                {
                    'element': 'Air',
                    'cards': ['Djinn', 'Giant eagle', 'Sprite'],
                    'count': 14,
                },
                {
                    'element': 'Water',
                    'cards': ['Bog monster', 'Giant turtle'],
                    'count': 19,
                },
            ]
        )

    @test.xfail('still broken - not a singleton, maybe')
    async def test_edgeql_igroup_linkproperty_simple_03(self):
        await self.assert_query_result(
            r"""
                # group by link property
                WITH MODULE cards
                SELECT _ := (
                DETACHED GROUP User
                # get the nickname that this user from Alice (if any)
                USING B := (
                    SELECT User.<friends[IS User]@nickname
                    FILTER User.<friends[IS User].name = 'Alice'
                )
                BY B
                INTO F
                UNION (
                    nickname := B,
                    # the tuple without nickname will be missing from the
                    # final result
                    name := array_agg(F.name)
                )) ORDER BY _.nickname;
            """,
            [
                {'name': ['Carol'], 'nickname': 'Firefighter'},
                {'name': ['Dave'], 'nickname': 'Grumpy'},
                {'name': ['Bob'], 'nickname': 'Swampy'},
            ]
        )

    @test.xfail('still broken - ... linkprops')
    async def test_edgeql_igroup_linkproperty_nested_01(self):
        await self.assert_query_result(
            r"""
                WITH MODULE cards
                SELECT User {
                    name,
                    # total card count across the deck
                    total := sum(User.deck@count),
                    # group each deck by elements, adding up the counts
                    elements := (
                        WITH
                            # need an intermediate representation of
                            # user's deck to be able to associate the
                            # count link property with the specific
                            U := User {
                                deck: {
                                    count := User.deck@count
                                }
                            }
                        # grouping the cards now
                        SELECT _ := (
                        DETACHED GROUP U.deck
                        USING B :=  U.deck.element
                        BY B
                        INTO D
                        UNION (
                            name := B,
                            count := sum(D.count),
                        ))
                        ORDER BY _.name
                    )
                } ORDER BY User.name;
            """,
            [
                {
                    'name': 'Alice',
                    'total': 10,
                    'elements': [
                        {'name': 'Fire', 'count': 4},
                        {'name': 'Water', 'count': 6}
                    ]
                },
                {
                    'name': 'Bob',
                    'total': 12,
                    'elements': [
                        {'name': 'Earth', 'count': 6},
                        {'name': 'Water', 'count': 6}
                    ]
                },
                {
                    'name': 'Carol',
                    'total': 19,
                    'elements': [
                        {'name': 'Air', 'count': 8},
                        {'name': 'Earth', 'count': 6},
                        {'name': 'Water', 'count': 5}
                    ]
                },
                {
                    'name': 'Dave',
                    'total': 10,
                    'elements': [
                        {'name': 'Air', 'count': 6},
                        {'name': 'Earth', 'count': 1},
                        {'name': 'Fire', 'count': 1},
                        {'name': 'Water', 'count': 2}
                    ]
                }
            ]
        )

    @test.xfail('still broken - linkprops')
    async def test_edgeql_igroup_linkproperty_multiple_01(self):
        await self.assert_query_result(
            r"""
                WITH
                    MODULE cards,
                    U := (
                        SELECT User {
                            deck: {
                                count := User.deck@count
                            }
                        } FILTER User.name = 'Dave'
                    )
                SELECT (
                DETACHED GROUP
                    U.deck
                USING
                    El := U.deck.element,
                    Count := U.deck.count
                BY El, Count
                INTO D
                UNION (
                    cards := array_agg(D.name ORDER BY D.name),
                    element := El,
                    count := Count,
                )) ORDER BY .element THEN .count;
            """,
            [
                # compare to test_edgeql_props_basic01
                {
                    'element': 'Air',
                    'count': 1,
                    'cards': ['Djinn', 'Giant eagle'],
                },
                {
                    'element': 'Air',
                    'count': 4,
                    'cards': ['Sprite'],
                },
                {
                    'element': 'Earth',
                    'count': 1,
                    'cards': ['Golem'],
                },
                {
                    'element': 'Fire',
                    'count': 1,
                    'cards': ['Dragon'],
                },
                {
                    'element': 'Water',
                    'count': 1,
                    'cards': ['Bog monster', 'Giant turtle'],
                },
            ]
        )

    @test.xfail('still broken - complains about the ordering cardinality')
    async def test_edgeql_igroup_scalar_01a(self):
        # huh.
        await self.assert_query_result(
            r"""
                WITH
                    I := <int64>Issue.number
                SELECT _r := (
                DETACHED GROUP I
                USING _ :=  I % 2 = 0
                BY _
                INTO I
                UNION (
                    values := array_agg(I ORDER BY I)
                )) ORDER BY _r.values;
            """,
            [
                {'values': [1, 3]},
                {'values': [2, 4]}
            ]
        )

    @test.xfail('still broken - cannot create root rvar for non-object path')
    async def test_edgeql_igroup_scalar_01b(self):
        # huh.
        await self.assert_query_result(
            r"""
                WITH
                    I := <int64>Issue.number
                SELECT _r := (
                DETACHED GROUP I
                USING _ :=  I % 2 = 0
                BY _
                INTO I
                UNION (
                    values := array_agg((SELECT _ := I ORDER BY _))
                )) ORDER BY _r.values;
            """,
            [
                {'values': [1, 3]},
                {'values': [2, 4]}
            ]
        )

    async def test_edgeql_igroup_to_freeobject_01(self):
        await self.assert_query_result(
            r"""
                WITH MODULE cards
                DETACHED GROUP Card { name }
                USING e := .element,
                BY e
                INTO g UNION { z := g };
            """,
            tb.bag([
                {"z": tb.bag(
                    [{"name": "Bog monster"}, {"name": "Giant turtle"}])},
                {"z": tb.bag(
                    [{"name": "Imp"}, {"name": "Dragon"}])},
                {"z": tb.bag([{"name": "Dwarf"}, {"name": "Golem"}])},
                {"z": tb.bag([
                    {"name": "Sprite"},
                    {"name": "Giant eagle"},
                    {"name": "Djinn"},
                ])}
            ])
        )

    async def test_edgeql_igroup_to_freeobject_02(self):
        await self.assert_query_result(
            r"""
                WITH MODULE cards
                SELECT (DETACHED GROUP Card { name }
                USING e := .element,
                BY e
                INTO g UNION { z := g });
            """,
            tb.bag([
                {"z": tb.bag(
                    [{"name": "Bog monster"}, {"name": "Giant turtle"}])},
                {"z": tb.bag(
                    [{"name": "Imp"}, {"name": "Dragon"}])},
                {"z": tb.bag([{"name": "Dwarf"}, {"name": "Golem"}])},
                {"z": tb.bag([
                    {"name": "Sprite"},
                    {"name": "Giant eagle"},
                    {"name": "Djinn"},
                ])}
            ])
        )

    async def test_edgeql_igroup_to_freeobject_03(self):
        await self.assert_query_result(
            r"""
                WITH MODULE cards
                DETACHED GROUP Card { name }
                USING e := .element,
                BY e
                INTO g UNION { n := count(g) };
            """,
            tb.bag([{"n": 2}, {"n": 2}, {"n": 2}, {"n": 3}]),
        )

    async def test_edgeql_igroup_to_freeobject_04(self):
        # XXX: we generate sort of unsatisfactory code here:
        # we materialize .n, and properly into an array?
        await self.assert_query_result(
            r"""
                WITH MODULE cards
                SELECT (DETACHED GROUP Card { name }
                USING e := .element,
                BY e
                INTO g UNION { n := count(g) });
            """,
            tb.bag([{"n": 2}, {"n": 2}, {"n": 2}, {"n": 3}]),
        )

    async def test_edgeql_igroup_filter_01(self):
        await self.assert_query_result(
            r"""
                WITH MODULE cards
                SELECT (DETACHED GROUP Card { name }
                USING e := .element,
                BY e
                INTO g UNION (
                    SELECT { key := {e := e}, z := g } FILTER e != 'Air')
                );
            """,
            tb.bag([
                {
                    "key": {"e": "Water"},
                    "z": tb.bag(
                        [{"name": "Bog monster"}, {"name": "Giant turtle"}])
                },
                {"key": {"e": "Fire"}, "z": tb.bag([
                    {"name": "Imp"}, {"name": "Dragon"}])},
                {"key": {"e": "Earth"}, "z": tb.bag([
                    {"name": "Dwarf"}, {"name": "Golem"}])}
            ])
        )

    @test.xfail('''
        We produce bogus repeated output with 6 duplications of each group,
        including 'Air'.

        I think because 6 = |Card| - |Card.element = 'Air'|??

        We would like to be able to generate this kind of code where we push
        in a FILTER, but we don't *need* to...
    ''')
    async def test_edgeql_igroup_filter_02(self):
        await self.assert_query_result(
            r"""
                WITH MODULE cards
                SELECT (DETACHED GROUP Card { name }
                USING e := .element,
                BY e
                INTO g UNION (
                    SELECT { key := {e := e}, z := g } FILTER .key.e != 'Air')
                );
            """,
            tb.bag([
                {
                    "key": {"e": "Water"},
                    "z": tb.bag(
                        [{"name": "Bog monster"}, {"name": "Giant turtle"}])
                },
                {"key": {"e": "Fire"}, "z": tb.bag([
                    {"name": "Imp"}, {"name": "Dragon"}])},
                {"key": {"e": "Earth"}, "z": tb.bag([
                    {"name": "Dwarf"}, {"name": "Golem"}])}
            ])
        )
